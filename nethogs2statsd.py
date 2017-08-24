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

Important Note
--------------

There are some GitHub issues open on the nethogs project asserting that the
bandwidth measurements are vastly incorrect; some people say as much as 50%.
This tool is intended mainly to identify the _relative_ differences between
processes ("what's using the most bandwidth?" or "if I want to use less
bandwidth, what should I try to optimize or remove?").

__WARNING:__ Also, right now, nethogs only supports TCP traffic, not UDP.
If you're using a lot of UDP (especially media streaming over UDP), this
won't record it!

Usage
-----

This isn't really usable as-is, it's just an example of how this could be
done. See the top of the source code for a bunch of static configuration of
mine. There's also an example systemd unit for this in the same repo.

Requirements
------------

libnethogs (<https://github.com/raboof/nethogs#libnethogs>), currently
designed for 0.8.5.

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

2017-08-23 jantman:
- initial script
"""

import sys
import ctypes
import signal
import threading
import argparse
import logging
from collections import defaultdict

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

# LIBRARY_NAME has to be exact, although it doesn't need to include the full path.
# The version tagged as 0.8.5 (download link below) builds a library with this name.
# https://github.com/raboof/nethogs/archive/v0.8.5.tar.gz
LIBRARY_NAME = 'libnethogs.so.0.8.5'

# Here are some definitions from libnethogs.h
# https://github.com/raboof/nethogs/blob/master/src/libnethogs.h
# Possible actions are NETHOGS_APP_ACTION_SET & NETHOGS_APP_ACTION_REMOVE
# Action REMOVE is sent when nethogs decides a connection or a process has died. There are two
# timeouts defined, PROCESSTIMEOUT (150 seconds) and CONNTIMEOUT (50 seconds). AFAICT, the latter
# trumps the former so we see a REMOVE action after ~45-50 seconds of inactivity.


class Action(object):
    SET = 1
    REMOVE = 2

    MAP = {SET: 'SET', REMOVE: 'REMOVE'}


class LoopStatus(object):
    """Return codes from nethogsmonitor_loop()"""
    OK = 0
    FAILURE = 1
    NO_DEVICE = 2

    MAP = {OK: 'OK', FAILURE: 'FAILURE', NO_DEVICE: 'NO_DEVICE'}


class NethogsMonitorRecord(ctypes.Structure):
    """
    ctypes version of the struct of the same name from libnethogs.h

    The sent/received KB/sec values are averaged over 5 seconds; see PERIOD
    in nethogs.h.
    https://github.com/raboof/nethogs/blob/master/src/nethogs.h#L43
    sent_bytes and recv_bytes are a running total
    """
    _fields_ = (('record_id', ctypes.c_int),
                ('name', ctypes.c_char_p),
                ('pid', ctypes.c_int),
                ('uid', ctypes.c_uint32),
                ('device_name', ctypes.c_char_p),
                ('sent_bytes', ctypes.c_uint32),
                ('recv_bytes', ctypes.c_uint32),
                ('sent_kbs', ctypes.c_float),
                ('recv_kbs', ctypes.c_float),
                )


CALLBACK_FUNC_TYPE = ctypes.CFUNCTYPE(
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(NethogsMonitorRecord)
)


class HogWatcher(threading.Thread):

    def __init__(self, lib, dev_names=[]):
        """
        Thread to watch and react to nethogs data.

        :param lib: nethogs library instance
        :type lib: ctypes.CDLL
        :param dev_names: list of device names to track
        :type dev_names: list
        """
        threading.Thread.__init__(self)
        self._lib = lib
        self._dev_names = dev_names
        self._send_cache = defaultdict(int)
        self._recv_cache = defaultdict(int)
        logger.debug('Initializing HogWatcher')
        if len(self._dev_names) > 0:
            logger.info('Will only monitor devices: %s', self._dev_names)

    def run(self):
        """
        Create a type for my callback func. The callback func returns void
        (None), and accepts as params an int and a pointer to a
        NethogsMonitorRecord instance. The params and return type of the
        callback function are mandated by nethogsmonitor_loop().
        See libnethogs.h.
        """
        rc = self._lib.nethogsmonitor_loop(CALLBACK_FUNC_TYPE(self._callback))
        if rc != LoopStatus.OK:
            logger.error(
                'nethogsmonitor_loop returned %s', LoopStatus.MAP[rc]
            )
        else:
            logger.warning('exiting monitor loop')

    def _callback(self, action, data):
        if (
            len(self._dev_names) > 0 and
            data.contents.device_name.decode('ascii') not in self._dev_names
        ):
            return
        # Action type is either SET or REMOVE. I have never seen nethogs
        # send an unknown action type, and I don't expect it to do so.
        action_type = Action.MAP.get(action, 'Unknown')
        logger.debug(
            'record_id=%d action=%s name=%s pid=%d uid=%d dev=%s '
            'sent_b=%d recv_b=%d sent_kbps=%s recv_kbps=%s',
            data.contents.record_id, action_type, data.contents.name,
            data.contents.pid, data.contents.uid,
            data.contents.device_name.decode('ascii'),
            data.contents.sent_bytes, data.contents.recv_bytes,
            data.contents.sent_kbs, data.contents.recv_kbs
        )
        rid = data.contents.record_id
        # libnethogs sent and recv counters run forever; we only want to send
        # the difference from the last counter.
        sent_b = self.uint32_diff(
            self._send_cache[rid], data.contents.sent_bytes
        )
        recv_b = self.uint32_diff(
            self._recv_cache[rid], data.contents.recv_bytes
        )
        self._send_cache[rid] = data.contents.sent_bytes
        self._recv_cache[rid] = data.contents.recv_bytes
        if action == Action.SET:
            pass
        elif action == Action.REMOVE:
            del self._send_cache[rid]
            del self._recv_cache[rid]
        else:
            logger.critical('Got unknown Action: %s', action)

    @staticmethod
    def uint32_diff(old, new):
        return 1

def parse_args(argv):
    """
    parse arguments/options
    """
    p = argparse.ArgumentParser(
        description='use libnethogs to send nethogs data to statsd'
    )
    p.add_argument('-H', '--statsd-host', dest='statsd_host', action='store',
                   type=str, default='127.0.0.1',
                   help='statsd host (default: 127.0.0.1)')
    p.add_argument('-P', '--statsd-port', dest='statsd_port', action='store',
                   type=int, default=8125,
                   help='statsd port (default: 8125)')
    p.add_argument('-p', '--prefix', dest='prefix', action='store',
                   type=str, default='nethogs',
                   help='statsd metric prefix')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-d', '--device', dest='devices', action='append',
                   default=[], help='device names to track')
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

    logger.debug('Creating ctypes.CDLL(%s)', LIBRARY_NAME)
    lib = ctypes.CDLL(LIBRARY_NAME)

    def signal_handler(signal, frame):
        logger.error('SIGINT received; requesting exit from monitor loop.')
        lib.nethogsmonitor_breakloop()

    logger.debug('Setting up signal handlers')
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.debug('Creating monitor thread')
    monitor_thread = HogWatcher(lib, args.devices)
    logger.debug('Starting monitor thread')
    monitor_thread.start()

    done = False
    while not done:
        monitor_thread.join(0.3)
        done = not monitor_thread.is_alive()
