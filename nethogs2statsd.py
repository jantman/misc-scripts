#!/usr/bin/env python
"""
nethogs2statsd.py
=================

Python3 script using libnethogs from the
[nethogs](https://github.com/raboof/nethogs) project to push per-process
bandwidth usage statistics to statsd. Includes some code that's specific to
my use case.

Based on:
https://github.com/raboof/nethogs/blob/master/contrib/python-wrapper.py
as of 046196ba7b8ffffda49d74c701b0858580e7687b

Important Notes
---------------

1. This relies on features of libnethogs merged to master but not released yet
as of 0.8.5. Until a new release is cut, you will have to build libnethogs
from master yourself.
2. __WARNING:__ Right now, nethogs only supports TCP traffic, not UDP.
If you're using a lot of UDP (especially media streaming over UDP), this
won't record it!

Usage
-----

This isn't really usable as-is, it's just an example of how this could be
done; it includes a lot of things that are specific to my use case.

Requirements
------------

libnethogs (<https://github.com/raboof/nethogs#libnethogs>) greater than 0.8.5.
Right now, until a new release is cut, this means building libnethogs from
master (greater than 7093964413c086f7eee06cbe257f2a579caae209).

Also, [statsd](https://github.com/etsy/statsd) or a statsd-compatible stats
server.

License
-------

Copyright 2017 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/nethogs2statsd.py>

CHANGELOG
---------

2017-08-27 jantman:
- bug fixes

2017-08-28 jantman:
- bug fixes and change statsd metric name

2017-08-27 jantman:
- initial script
"""

import sys
import ctypes
import signal
import threading
import argparse
import logging
import os
from queue import Queue
from collections import defaultdict
import socket
import re
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

#: Name of the libnethogs DLL to load (can be overridden by CLI option).
#: LIBRARY_NAME has to be exact, although it doesn't need to include the full
#: path. The version tagged as 0.8.5 builds a library with this name; It can be
#: downloaded from: https://github.com/raboof/nethogs/archive/v0.8.5.tar.gz
LIBRARY_NAME = 'libnethogs.so.0.8.5'


class Action(object):
    """
    Possible callback actions from libnethogs.h

    See: https://github.com/raboof/nethogs/blob/master/src/libnethogs.h

    Possible actions are NETHOGS_APP_ACTION_SET & NETHOGS_APP_ACTION_REMOVE
    Action REMOVE is sent when nethogs decides a connection or a process has
    died. There are two timeouts defined, PROCESSTIMEOUT (150 seconds) and
    CONNTIMEOUT (50 seconds). AFAICT, the latter trumps the former so we see
    a REMOVE action after ~45-50 seconds of inactivity.
    """

    #: Action value for updating statistics for a Process.
    SET = 1

    #: Action value for removing a timed-out Process.
    REMOVE = 2

    #: Dict mapping action numeric values to string descriptions.
    MAP = {SET: 'SET', REMOVE: 'REMOVE'}


class LoopStatus(object):
    """Return codes from nethogsmonitor_loop()"""

    #: Return code for OK status.
    OK = 0

    #: Return code for failure status.
    FAILURE = 1

    #: Return code for status when no devices were found for capture.
    NO_DEVICE = 2

    #: Dict mapping numeric status values to string descriptions.
    MAP = {OK: 'OK', FAILURE: 'FAILURE', NO_DEVICE: 'NO_DEVICE'}


class NethogsMonitorRecord(ctypes.Structure):
    """
    ctypes version of the struct of the same name from libnethogs.h

    The sent/received KB/sec values are averaged over 5 seconds; see PERIOD
    in nethogs.h. sent_bytes and recv_bytes are a running total.

    See: https://github.com/raboof/nethogs/blob/master/src/nethogs.h
    """
    _fields_ = (
        ('record_id', ctypes.c_int),
        ('name', ctypes.c_char_p),
        ('pid', ctypes.c_int),
        ('uid', ctypes.c_uint32),
        ('device_name', ctypes.c_char_p),
        ('sent_bytes', ctypes.c_uint64),
        ('recv_bytes', ctypes.c_uint64),
        ('sent_kbs', ctypes.c_float),
        ('recv_kbs', ctypes.c_float),
    )

#: ctypes wrapper for the type of the libnethogs callback function
CALLBACK_FUNC_TYPE = ctypes.CFUNCTYPE(
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(NethogsMonitorRecord)
)


def cmdline_list(str):
    ret = []
    buf = ''
    for c in str:
        if ord(c) == 32:
            ret.append(buf)
            buf = ''
        elif ord(c) > 31 or ord(c) == 9:
            buf += c
        else:
            if len(buf) > 0:
                ret.append(buf)
            buf = ''
    return ret


def safename(s):
    return re.sub(r'[^0-9a-zA-Z_-]+', '_', s)


class UpdateHandler(threading.Thread):

    def __init__(self, dataq, statsd_host, statsd_port, prefix):
        """
        Initialize the data handler thread.

        :param dataq: Queue to receive data updates from HogWatcher
        :type dataq: queue.Queue
        :param statsd_host: host to send statsd metrics to
        :type statsd_host: str
        :param statsd_port: port to send statsd metrics on
        :type statsd_port: int
        :param prefix: prefix for statsd metrics
        :type prefix: str
        """
        threading.Thread.__init__(self)
        self._dataq = dataq
        self._statsd_host = statsd_host
        self._statsd_port = statsd_port
        self._prefix = prefix
        if not self._prefix.endswith('.'):
            self._prefix = self._prefix + '.'
        # _rec_cache is (rec_id, pid, uid) => metric name (suffix)
        self._rec_cache = {}

    def run(self):
        """
        Run the thread; handle elements added to queue.
        """
        while True:
            res = self._dataq.get()
            if isinstance(res, KeyboardInterrupt):
                logger.warning(
                    'UpdateHandler thread received KeyboardInterrupt.'
                )
                return
            if res is None:
                continue
            self._handle_result(*res)
            self._dataq.task_done()

    def _handle_result(self, rec_id, action, name, pid,
                       uid, devname, sent_b, recv_b):
        """
        Handle an update (SET or REMOVE) from the libnethogs loop.

        :param rec_id: libnethogs NethogsMonitorRecord record ID
        :type rec_id: int
        :param action: The action type; attribute on Action class.
        :type action: int
        :param name: program/process name, as determined by libnethogs
        :type name: str
        :param pid: PID of process
        :type pid: int
        :param uid: UID that process belongs to
        :type uid: int
        :param devname: network interface name
        :type devname: str
        :param sent_b: bytes sent since last update
        :type sent_b: int
        :param recv_b: bytes received since last update
        :type recv_b: int
        """
        logger.debug(
            'HANDLER: ACTION=%d %d "%s" PID=%d UID=%d dev=%s sent_b=%d '
            'recv_b=%d', action, rec_id, name, pid, uid, devname, sent_b, recv_b
        )
        cache_key = (rec_id, pid, uid)
        suffix = self._rec_cache.get(cache_key, None)
        if suffix is None:
            suffix = self._metric_suffix_for_record(name, pid, uid)
            self._rec_cache[cache_key] = suffix
        self._statsd_send(suffix, devname, sent_b, recv_b)
        if action == Action.REMOVE:
            self._rec_cache.pop(cache_key, None)

    def _metric_suffix_for_record(self, name, pid, uid):
        """
        Given the name, pid and uid of a nethogs monitor record, return the
        appropriate statsd metric suffix for it.

        :param name: program/process name, as determined by libnethogs
        :type name: str
        :param pid: PID of process
        :type pid: int
        :param uid: UID that process belongs to
        :type uid: int
        :return: statsd metric suffix
        :rtype: str
        """
        progname = name.decode('ascii').split(' ')[0]
        if pid == 0:
            return '%d.unknown' % uid
        if '/' in progname:
            progname = progname.split('/')[-1]
        try:
            with open(os.path.join('/proc/%d/cmdline' % pid), 'r') as fh:
                cmdline = cmdline_list(fh.read().strip())
        except Exception:
            cmdline = None
        if progname == 'python':
            progname = self._progname_for_python(progname, cmdline)
        elif progname == 'ssh':
            progname = self._progname_for_ssh(progname, cmdline)
        elif progname.startswith('git-remote-'):
            progname = self._progname_for_git_remote(progname, cmdline)
        elif progname.startswith('terraform-provider'):
            progname = 'terraform-provider'
        mname = '%d.%s' % (uid, safename(progname))
        logger.info(
            'NEW record: progname=%s pid=%s uid=%s name="%s" cmdline="%s"; '
            'metric name: "%s"', progname, pid, uid, name, cmdline, mname
        )
        return mname

    def _progname_for_python(self, progname, cmdline):
        """
        For Python commands, try to find the name of the script that's running.
        If that fails, fall back to the interpreter/executable name.

        :param progname: program name as seen by nethogs (process executable)
        :type progname: str
        :param cmdline: full process command line, from /proc/PID/cmdline
        :type cmdline: str
        :return: how the program should be shown in statsd
        :rtype: str
        """
        if cmdline is None:
            # /proc/PID/cmdline gone by time we tried to read it
            return progname
        if len(cmdline) == 1:
            return cmdline[0].split('/')[-1]
        if cmdline[0].split('/')[-1].startswith('python'):
            cmdline = cmdline[1:]
        for c in cmdline:
            if c.startswith('-'):
                continue
            tmp = 'python-' + c.split('/')[-1]
            if tmp.startswith('python-gmvault_bootstrap'):
                return 'python-gmvault_bootstrap'
            return tmp
        logger.warning('Unknown Python command; progname=%s cmdline=%s',
                       progname, cmdline)
        return progname

    def _progname_for_ssh(self, progname, cmdline):
        """
        For ssh commands, try to find the program that's running through ssh
        (i.e. git, scp, etc.) or else the host the connection is to.

        :param progname: program name as seen by nethogs (process executable)
        :type progname: str
        :param cmdline: full process command line, from /proc/PID/cmdline
        :type cmdline: str
        :return: how the program should be shown in statsd
        :rtype: str
        """
        if 'git-receive-pack' in cmdline:
            for c in cmdline:
                if '@' in c:
                    return 'ssh_git-receive-pack_%s' % c.split('@')[-1]
            logger.warning(
                'Unknown SSH git-receive-pack; progname=%s cmdline=%s',
                progname, cmdline
            )
            return 'ssh_git-receive-pack_unknown'
        if 'git-upload-pack' in cmdline:
            for c in cmdline:
                if '@' in c:
                    return 'ssh_git-upload-pack_%s' % c.split('@')[-1]
            logger.warning(
                'Unknown SSH git-upload-pack; progname=%s cmdline=%s',
                progname, cmdline
            )
            return 'ssh_git-upload-pack_unknown'
        host = 'unknown'
        for c in cmdline[1:]:
            if c.startswith('-'):
                continue
            if '@' in c:
                host = c.split(':')[0]
                break
        if host == 'unknown':
            for c in cmdline[1:]:
                if c.startswith('-'):
                    continue
                host = c
                break
        if 'scp' in cmdline:
            return 'ssh-scp_%s' % host
        logger.warning(
            'Unknown SSH command; progname=%s host=%s cmdline=%s',
            progname, host, cmdline
        )
        return '%s_%s' % (progname, host)

    def _progname_for_git_remote(self, progname, cmdline):
        """
        For git-remote-* helper commands (i.e. git-remote-https), try to
        find the URI of the remote, and return its host. If that fails,
        fall back to the original progname.

        :param progname: program name as seen by nethogs (process executable)
        :type progname: str
        :param cmdline: full process command line, from /proc/PID/cmdline
        :type cmdline: str
        :return: how the program should be shown in statsd
        :rtype: str
        """
        prefix = progname.replace('git-remote-', 'git-')
        for part in reversed(cmdline):
            try:
                p = urlparse(part)
                return '%s_%s' % (prefix, safename(p.netloc))
            except Exception:
                continue
        logger.warning('Unknown git command; progname=%s cmdline=%s',
                       progname, cmdline)
        return progname

    def _statsd_send(self, name, devname, sent_b, recv_b):
        """
        Send a result record to statsd.

        :param name: metric name suffix (after ``self._prefix``)
        :type name: str
        :param devname: network device name
        :type devname: str
        :param sent_b: bytes sent since last update
        :type sent_b: int
        :param recv_b: bytes received since last update
        :type recv_b: int
        """
        dn = safename(devname)
        mpath = '%s%s' % (self._prefix, name)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        msg = '%s.%s.send_b:%d|c\n%s.%s.recv_b:%d|c' % (
            mpath, dn, sent_b, mpath, dn, recv_b
        )
        logger.debug('statsd send: %s', msg.replace("\n", '\\n'))
        sock.sendto(msg.encode('ascii'), (self._statsd_host, self._statsd_port))
        sock.close()


class HogWatcher(threading.Thread):

    def __init__(self, dataq, lib, dev_names=[], filter=None):
        """
        Thread to watch and react to nethogs data updates.

        :param dataq: Queue to pass update results to handler thread
        :type dataq: queue.Queue
        :param lib: nethogs library instance
        :type lib: ctypes.CDLL
        :param dev_names: list of device names to track
        :type dev_names: list
        :param filter: pcap-filter format packet capture filter expression
        :type filter: str
        """
        threading.Thread.__init__(self)
        self._lib = lib
        self._lib.nethogsmonitor_loop.restype = ctypes.c_int
        self._dev_names = dev_names
        self._filter = filter
        self._send_cache = defaultdict(int)
        self._recv_cache = defaultdict(int)
        self._dataq = dataq
        logger.debug('Initializing HogWatcher')
        if len(self._dev_names) > 0:
            logger.info('Will only monitor devices: %s', self._dev_names)

    @property
    def dev_args(self):
        """
        Return the appropriate ctypes arguments for a device name list, to pass
        to libnethogs ``nethogsmonitor_loop_devices``. The return value is a
        2-tuple of devc (``ctypes.c_int``) and devicenames (``ctypes.POINTER``)
        to an array of ``ctypes.c_char``).

        :param devnames: list of device names to monitor
        :type devnames: list
        :return: 2-tuple of devc, devicenames ctypes arguments
        :rtype: tuple
        """
        devc = len(self._dev_names)
        if devc == 0:
            return ctypes.c_int(0), None
        devnames_type = ctypes.c_char_p * devc
        devnames_arg = devnames_type()
        for idx, val in enumerate(self._dev_names):
            devnames_arg[idx] = (val + chr(0)).encode('ascii')
        return ctypes.c_int(devc), ctypes.cast(
            devnames_arg, ctypes.POINTER(ctypes.c_char_p)
        )

    def run(self):
        """
        Create a type for my callback func. The callback func returns void
        (None), and accepts as params an int and a pointer to a
        NethogsMonitorRecord instance. The params and return type of the
        callback function are mandated by nethogsmonitor_loop().
        See libnethogs.h.
        """
        devc, devicenames = self.dev_args
        filter_arg = self._filter
        if filter_arg is not None:
            logger.info('Restricting capture with filter: %s', filter_arg)
            filter_arg = ctypes.c_char_p(filter_arg.encode('ascii'))
        rc = self._lib.nethogsmonitor_loop_devices(
            CALLBACK_FUNC_TYPE(self._callback),
            filter_arg,
            devc,
            devicenames,
            False
        )
        if rc != LoopStatus.OK:
            logger.error(
                'nethogsmonitor_loop returned %s', LoopStatus.MAP[rc]
            )
        else:
            logger.warning('exiting monitor loop')

    def _callback(self, action, data):
        """
        Callback fired when libnethogs loop has a data update.

        :param action: The action type; attribute on Action class.
        :type action: int
        :param data: Updated NethogsMonitorRecord containing latest data
        :type data: NethogsMonitorRecord
        """
        action_name = Action.MAP.get(action, 'Unknown')
        logger.debug(
            'record_id=%d action=%s name=%s pid=%d uid=%d dev=%s '
            'sent_b=%d recv_b=%d sent_kbps=%s recv_kbps=%s',
            data.contents.record_id, action_name, data.contents.name,
            data.contents.pid, data.contents.uid,
            data.contents.device_name.decode('ascii'),
            data.contents.sent_bytes, data.contents.recv_bytes,
            data.contents.sent_kbs, data.contents.recv_kbs
        )
        rid = data.contents.record_id
        # libnethogs sent and recv counters run forever; we only want to send
        # the difference from the last counter.
        self._dataq.put([
            rid,
            action,
            data.contents.name,
            data.contents.pid,
            data.contents.uid,
            data.contents.device_name.decode('ascii'),
            data.contents.sent_bytes - self._send_cache[rid],
            data.contents.recv_bytes - self._recv_cache[rid]
        ])
        self._send_cache[rid] = data.contents.sent_bytes
        self._recv_cache[rid] = data.contents.recv_bytes
        if action == Action.REMOVE:
            del self._send_cache[rid]
            del self._recv_cache[rid]


def parse_args(argv):
    """
    parse arguments/options
    """
    p = argparse.ArgumentParser(
        description='use libnethogs to send nethogs data to statsd'
    )
    p.add_argument('-L', '--library-name', dest='libname', action='store',
                   type=str, default=LIBRARY_NAME,
                   help='Override library name from default of "%s" (for '
                        'testing locally-built modified library)'
                        '' % LIBRARY_NAME)
    p.add_argument('-H', '--statsd-host', dest='statsd_host', action='store',
                   type=str, default='127.0.0.1',
                   help='statsd host (default: 127.0.0.1)')
    p.add_argument('-P', '--statsd-port', dest='statsd_port', action='store',
                   type=int, default=8125,
                   help='statsd port (default: 8125)')
    def_prefix = 'nethogs.%s' % socket.gethostname().replace('.', '_')
    p.add_argument('-p', '--prefix', dest='prefix', action='store',
                   type=str, default=def_prefix,
                   help='statsd metric prefix')
    p.add_argument('-f', '--filter', dest='filter', action='store',
                   type=str, default=None,
                   help='EXPERIMENTAL - pcap packet filter expression to limit '
                        'the capture (see man pcap-filter); This feature may '
                        'be removed or changed in a future release.')
    p.add_argument('-d', '--device', dest='devices', action='append',
                   default=[], help='device names to track')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    args = p.parse_args(argv)
    return args


def set_log_info():
    """set logger level to INFO"""
    set_log_level_format(logging.INFO,
                         '%(asctime)s %(levelname)s:%(name)s:%(message)s')


def set_log_debug():
    """set logger level to DEBUG, and debug-level output format"""
    set_log_level_format(
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(level, format):
    """
    Set logger level and format.

    :param level: logging level; see the :py:mod:`logging` constants.
    :type level: int
    :param format: logging formatter format string
    :type format: str
    """
    formatter = logging.Formatter(fmt=format)
    logger.handlers[0].setFormatter(formatter)
    logger.setLevel(level)

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    elif args.verbose == 1:
        set_log_info()

    logger.debug('Loading DLL: %s', args.libname)
    lib = ctypes.CDLL(args.libname)

    dataq = Queue()

    def signal_handler(signal, frame):
        logger.error('SIGINT received; requesting exit from monitor loop.')
        lib.nethogsmonitor_breakloop()
        dataq.put(KeyboardInterrupt())

    logger.debug('Setting up signal handlers for SIGINT and SIGTERM')
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.debug('Creating handler thread')
    # raise NotImplementedError("Need to figure out how to break out of this")
    handler_thread = UpdateHandler(
        dataq, args.statsd_host, args.statsd_port, args.prefix
    )
    logger.debug('Starting handler thread')
    handler_thread.start()

    logger.debug('Creating monitor thread')
    monitor_thread = HogWatcher(dataq, lib, args.devices, args.filter)
    logger.debug('Starting monitor thread')
    monitor_thread.start()

    done = False
    while not done:
        monitor_thread.join(0.3)
        done = not monitor_thread.is_alive()
        if not handler_thread.is_alive():
            lib.nethogsmonitor_breakloop()
    dataq.put(KeyboardInterrupt())
