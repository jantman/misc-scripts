#!/usr/bin/env python
"""
smart_check.py
==============

Check SMART status of all attached and SMART-enabled disks via pySMART. Report
on status. Cache status on disk, and exit non-zero if status of any disks
changes.

Requirements
-------------

* Python3
* pySMART (`pip install pySMART`) == 1.0

License
--------

Copyright 2017-2020 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/smart_check.py>

CHANGELOG
----------

2020-08-04 Jason Antman <jason@jasonantman.com>:
  - Python3 logging fix
  - Update for pySMART 1.0

2020-04-10 Jason Antman <jason@jasonantman.com>:
  - Fix bug in calculation of whether a self-test is needed.

2018-12-31 Jason Antman <jason@jasonantman.com>:
  - add support for overriding or supplementing list of ignored attributes via
    -i and -I command-line arguments

2017-03-12 Jason Antman <jason@jasonantman.com>:
  - ignore Power_Cycle_Count, Start_Stop_Count, Load_Cycle_Count attributes

2017-01-05 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import os
import json
import socket
import time
from pySMART import DeviceList
from pySMART.utils import smartctl_type
from platform import node
from subprocess import Popen, PIPE
from dictdiffer import diff

FORMAT = "[%(asctime)s %(levelname)s %(filename)s:%(lineno)s - " \
         "%(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger()

IGNORE_ATTRS = [
    'Temperature_Celsius',
    'Power_On_Hours',
    'Power_Cycle_Count',
    'Start_Stop_Count',
    'Load_Cycle_Count'
]


class SmartChecker(object):

    def __init__(self, cache_path, blacklist=[], graphite_host=None,
                 graphite_port=2003, graphite_prefix=None,
                 test_interval=168, ignore_attrs=IGNORE_ATTRS):
        """ init method, run at class creation """
        self._blacklist = blacklist
        if len(blacklist) > 0:
            logger.warning('Ignoring device paths or serials: %s', blacklist)
        self._cache_path = os.path.abspath(os.path.expanduser(cache_path))
        self._cache = self._get_cache()
        self._graphite_host = graphite_host
        self._graphite_port = graphite_port
        self._graphite_prefix = graphite_prefix
        self._test_interval = test_interval
        self._ignore_attrs = ignore_attrs
        logger.info('Ignoring SMART Attributes: %s', ignore_attrs)
        self._errors = []

    def _get_cache(self):
        logger.info('Reading state cache from: %s', self._cache_path)
        if not os.path.exists(self._cache_path):
            logger.debug('State cache does not exist.')
            return {}
        with open(self._cache_path, 'r') as fh:
            raw = fh.read()
        cache = json.loads(raw)
        logger.debug('State cache: %s', cache)
        return cache

    def _write_cache(self):
        logger.info('Writing state cache to: %s', self._cache_path)
        with open(self._cache_path, 'w') as fh:
            fh.write(json.dumps(self._cache))
        logger.debug('State written.')

    def run(self):
        """check devices"""
        devices = self._discover_devices()
        devinfo = {}
        diffs = {}
        for dev in devices:
            logger.info('Checking device /dev/%s (%s)' , dev.name, dev.serial)
            devinfo[dev.serial] = self._info_for_dev(dev)
            self._ensure_smart_enabled(dev)
            if self._dev_needs_test(dev):
                logger.info('Device %s needs short test', dev.name)
                self._run_test(dev)
            #self._send_graphite(dev.name, dev.serial, devinfo[dev.serial])
            if dev.serial not in self._cache:
                logger.warning('Device /dev/%s (%s) not in cache from last '
                               'run of this program; storing current data in '
                               'cache. No change detection will be performed '
                               'until the next run.', dev.name, dev.serial)
                continue
            diff = self._diff_dev(self._cache[dev.serial], devinfo[dev.serial])
            if diff is not None:
                logger.warning('Detected changes in data for /dev/%s (%s)',
                               dev.name, dev.serial)
                diffs[dev.serial] = diff
            if dev.tests is None or len(dev.tests) < 1:
                continue
            if dev.tests[0].status != 'Completed without error':
                self._errors.append('Device /dev/%s (%s) last self-test did '
                                    'not complete without error' % (
                                    dev.name, dev.serial))
        # Make sure we got all the devices
        for serial in self._cache:
            if serial not in devinfo:
                msg = 'Device serial %s was in cache from last run, but not ' \
                      'discovered during this run. Maybe it has been ' \
                      'removed?' % serial
                logger.warning(msg)
                diffs[serial] = msg
        # finally, write cache
        self._cache = devinfo
        self._write_cache()
        if len(diffs) == 0 and len(self._errors) == 0:
            logger.info('No differences found for any devices. Exiting.')
            raise SystemExit(0)
        for serial, diff in diffs.items():
            print('Diff for device serial %s:' % serial)
            print("%s\n" % diff)
        for e in self._errors:
            print(e)
        raise SystemExit(1)

    def _ensure_smart_enabled(self, dev):
        """
        Ensure that SMART offline data collection is enabled on the disk.

        Unfortunately, pySMART does not support this...

        :param dev: device to query
        :type dev: pySMART.device.Device
        """
        cmdline = 'smartctl -d {0} -c /dev/{1}'.format(
            smartctl_type[dev.interface], dev.name
        )
        logger.debug('Checking if offline data collection is enabled for %s '
                     'with command: %s', dev.name, cmdline)
        cmd = Popen(cmdline, shell=True,
            stdout=PIPE, stderr=PIPE)
        _stdout, _stderr = cmd.communicate()
        _stdout = _stdout.decode()
        _stderr = _stderr.decode()
        logger.debug('command STDOUT: %s', _stdout)
        logger.debug('command STDERR: %s', _stderr)
        if 'Auto Offline Data Collection: Enabled' in _stdout:
            logger.info('Offline data collection is enabled on /dev/%s',
                        dev.name)
            return
        if 'Auto Offline Data Collection: Disabled' not in _stdout:
            msg = 'Cannot determine if offline data collection is enabled ' \
                  'or not on /dev/%s (%s)' % (dev.name, dev.serial)
            logger.error(msg)
            self._errors.append(msg)
            return
        cmdline = 'smartctl --offlineauto=on /dev/%s' % dev.name
        logger.warning('Offline data collection is disabled on /dev/%s (%s); '
                       'enabling now with: %s', dev.name, dev.serial, cmdline)
        cmd = Popen(cmdline, shell=True,
                    stdout=PIPE, stderr=PIPE)
        _stdout, _stderr = cmd.communicate()
        _stdout = _stdout.decode()
        _stderr = _stderr.decode()
        logger.debug('command STDOUT: %s', _stdout)
        logger.debug('command STDERR: %s', _stderr)
        if 'SMART Automatic Offline Testing Enabled' in _stdout:
            logger.info('Automatic offline testing enabled on /dev/%s (%s)',
                        dev.name, dev.serial)
            return
        msg = 'Error occurred when enabling Automatic offline testing on ' \
              '/dev/%s (%s) with command "%s": %s%s' % (
            dev.name, dev.serial, cmdline, _stdout, _stderr
        )
        logger.error(msg)
        self._errors.append(msg)

    def _dev_needs_test(self, dev):
        """
        Return whether or not this device needs to have a test run.

        :param dev: device to query
        :type dev: pySMART.device.Device
        :returns: whether or not the device needs to have a test run
        :rtype: bool
        """
        if self._test_interval < 1:
            logger.warning('Short device tests disabled; not checking if '
                           '/dev/%s needs test', dev.name)
            return False
        time_since_last_test = self._dev_time_since_last_test(dev)
        if time_since_last_test is None:
            logger.info('Device /dev/%s (%s) has no self-test log entries',
                        dev.name, dev.serial)
            return True
        logger.info('Device /dev/%s (%s) last test %d hours ago',
                     dev.name, dev.serial, time_since_last_test)
        if time_since_last_test <= self._test_interval:
            logger.info('Not testing device; last test within interval')
            return False
        return True

    def _run_test(self, dev):
        """
        If a self-test has not been run recently, trigger one. Wait for it to
        show up in the device's test log.

        :param dev: device to query
        :type dev: pySMART.device.Device
        """
        if dev._test_running:
            logger.warning('Not running short test on /dev/%s; test already '
                           'running', dev.name)
            return
        last_test = self._dev_time_since_last_test(dev)
        logger.warning('Starting short test on /dev/%s (%s)', dev.name,
                       dev.serial)
        res = dev.run_selftest('short')
        if res == 0:
            logger.info('Test started')
        elif res == 1:
            logger.warning('Previous test already running; test skipped')
            return
        elif res == 2:
            msg = 'Could not start short test on /dev/%s; test type not ' \
                  'supported by device' % dev.name
            logger.error(msg)
            self._errors.append(msg)
            return
        else:
            msg = 'Could not start short test on /dev/%s; unspecified ' \
                  'error (this may be normal on some devices)' % dev.name
        polls = 0
        while polls < 10:
            dev.update()
            if self._dev_time_since_last_test(dev) != last_test:
                logger.info('Success - device log shows new test')
                break
            logger.info('Device does not have any new tests after %d polls; '
                        'sleeping 30 seconds before polling again', polls)
            time.sleep(30)
            polls += 1
        else:
            msg = 'Device /dev/%s short test was triggered, but has not yet ' \
                  'appeared in the device log. Something has probably gone ' \
                  'wrong.' % dev.name
            logger.error(msg)
            self._errors.append(msg)

    def _dev_time_since_last_test(self, dev):
        """
        Return the number of hours since the last self-test of the specified
        device, or None if no test has ever been run.

        Note that per the smartctl(8) man page, for ATA devices, the time in
        self-test logs ("LifeTime(hours)") wraps at 2^16 (65,536) hours. As
        such, for devices for which ``smartctl_type[dev.interface]`` is
        ``ata`` or ``sat``, the test time (LifeTime(hours)") will be adjusted
        for this wraparound based on the device's Power On Hours (Attribute 9)
        value.

        :param dev: device to query
        :type dev: pySMART.device.Device
        :return: time of last device test, in power-on hours
        :rtype: int
        """
        try:
            dev.tests[0].hours
        except Exception:
            # no test reports at all
            return None
        hrs = int(dev.tests[0].hours)
        pwr_hours = self._dev_power_on_hours(dev)
        _type = smartctl_type[dev.interface]
        logger.debug(
            'Device /dev/%s tests[0].hours=%s, power_on_hours=%s, type=%s',
            dev.name, hrs, pwr_hours, _type
        )
        if _type not in ['ata', 'sat']:
            # no wrap-around; just return the value
            logger.debug(
                'Device is not ata or sat; time since last test is %s',
                pwr_hours - hrs
            )
            return pwr_hours - hrs
        if pwr_hours < 65536:
            logger.debug(
                'Power-on hours < 65536; time since last test is %s',
                pwr_hours - hrs
            )
            return pwr_hours - hrs
        if hrs <= pwr_hours:
            logger.debug(
                'Time of last test <= power-on hours;'
                ' time since last test is %s',
                pwr_hours - hrs
            )
            return pwr_hours - hrs
        multiplier = pwr_hours / 65536
        wrap = multiplier * 65536
        logger.info('Device /dev/%s Power On Hours appears to have wrapped '
                    '%d time(s). Adding %d to self-test time (%d); adjusted '
                    'last self-test time: %d', dev.name, multiplier, wrap,
                    hrs, (pwr_hours - (hrs + wrap)))
        hrs += wrap
        return pwr_hours - hrs

    def _dev_power_on_hours(self, dev):
        """
        Given a device, return the value of its #9 Attribute, "Power On Hours".

        :param dev: device to query
        :type dev: pySMART.device.Device
        :return: integer number of power-on hours
        :rtype: int
        """
        for a in dev.attributes:
            if a is None:
                continue
            if a.num == '9':
                logger.debug(
                    'Device %s attribute 9 (Power on Hours): %s',
                    dev.name, a
                )
                return int(a.raw)
        raise RuntimeError("Unable to find attribute 9 for /dev/%s" % dev.name)

    def _diff_dev(self, cached, curr):
        """
        Given two dicts of information/status about a device, one cached from
        the last run of this program and one from the current run, return either
        a formatted string showing the differences between them, or None if
        there are no differences.

        Note that attributes and other indicators which should normally change
        over time are ignored from the diff; this is limited to things which
        may indicate a health problem.

        :param cached: cached data on the device, from the last run
        :type cached: dict
        :param curr: data on the device from the current run
        :type curr: dict
        :return: human-readable diff, or None
        :rtype: :py:obj:`str` or :py:data:`None`
        """
        # remove values we don't want included in the diff
        cached = self._prep_dict_for_diff(cached)
        curr = self._prep_dict_for_diff(curr)
        # do the diff
        s = ''
        for d in diff(cached, curr):
            if d[0] != 'change':
                logger.debug('Ignoring diff: %s', d)
                continue
            k = d[1]
            if isinstance(k, type([])):
                k = ' '.join(['%s' % x for x in k])
            s += "%s changed from %s to %s\n" % (k, d[2][0], d[2][1])
        if s == '':
            return None
        return s

    def _prep_dict_for_diff(self, d):
        """
        Prepare a dict to be diffed.

        :param d: the dict to prepare
        :type d: dict
        :return: the prepped dict
        :rtype: dict
        """
        d.pop('tests', None)
        if 'attributes' in d:
            for attr in self._ignore_attrs:
                d['attributes'].pop(attr, None)
        return d

    def _send_graphite(self, name, serial, info):
        """
        If graphite sending is enabled, send statistics for this device to
        Graphite.

        :param name: device name
        :type name: str
        :param serial: device serial number
        :type serial: str
        :param info: device information dict
        :type info: dict
        """
        if self._graphite_host is None:
            logger.info('Graphite disabled; not sending')
            return
        prefix = self._prefix_for_device(name, serial)
        raise NotImplementedError()

    def _prefix_for_device(self, name, serial):
        """
        Generate a Graphite metric prefix for the given device.

        :param name: device name
        :type name: str
        :param serial: device serial number
        :type serial: str
        :return: graphite metric prefix
        :rtype: str
        """
        hn = node().replace('.', '_')
        pfx = self._graphite_prefix.replace('%HOSTNAME%', hn)
        pfx = pfx.replace('%DEV%', name)
        pfx = pfx.replace('%SERIAL%', serial)
        return pfx

    def _discover_devices(self):
        """
        Discover all non-blacklisted and SMART-capable devices. Return a list
        of the pySMART.device.Device objects.

        :return: list of Device objects
        :rtype: list
        """
        logger.info('Discovering devices...')
        devices = []
        for dev in DeviceList().devices:
            logger.info('Discovered device: %s', dev)
            if not dev.smart_capable:
                logger.warning('Ignoring device that does not support SMART or '
                               'does not have SMART enabled: /dev/%s', dev.name)
                continue
            if (
                '/dev/%s' % dev.name in self._blacklist or
                dev.name in self._blacklist
            ):
                logger.warning('Ignoring blacklisted device: /dev/%s', dev.name)
                continue
            if dev.serial in self._blacklist:
                logger.warning('Ignoring blacklisted device serial: %s',
                               dev.serial)
                continue
            devices.append(dev)
        logger.info('Discovered %d devices', len(devices))
        return devices

    def _info_for_dev(self, dev):
        """
        Return information about this device.

        :param dev: device to query
        :type dev: pySMART.device.Device
        :return: dict of info about device
        :rtype: dict
        """
        d = {
            'serial': dev.serial,
            'model': dev.model,
            'tests': [],
            'attributes': {},
            'assessment': dev.assessment,
            'messages': dev.messages
        }
        if dev.tests is not None:
            for t in dev.tests:
                if t is None:
                    continue
                d['tests'].append(vars(t))
        for a in dev.attributes:
            if a is None:
                continue
            d['attributes'][a.name] = {
                'name': a.name,
                'num': a.num,
                'flags': a.flags,
                'value': a.value,
                'worst': a.worst,
                'thresh': a.thresh,
                'updated': a.updated,
                'when_failed': a.when_failed,
                'raw': a.raw
            }
            if a.num == '9':
                # Power_On_Hours
                if int(a.raw) >= 43800:
                    d['attributes'][a.name]['status'] = 'EXCEEDED LIFETIME'
                elif int(a.raw) >= 39420:
                    d['attributes'][a.name]['status'] = '90% LIFETIME'
                else:
                    d['attributes'][a.name]['status'] = 'OK'
        logger.debug('Device %s (/dev/%s) info: %s', dev.serial, dev.name, d)
        return d


def parse_args(argv):
    """
    parse arguments/options
    """
    p = argparse.ArgumentParser(
        description='Check SMART for all disks, exit non-zero if any changed'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-c', '--cache_path', dest='cache_path', action='store',
                   default='~/.smart_check.json',
                   help='path to JSON state cache')
    p.add_argument('-b', '--blacklist', dest='blacklist', type=str,
                   action='append', default=[],
                   help='Device path or serial to ignore; can be specified '
                        'multiple times.')
    p.add_argument('-i', '--also-ignore', dest='also_ignore', type=str,
                   action='append', default=[],
                   help='Attribute name(s) to ignore in addition to the default'
                        '(%s). Can be specified multiple times. This option is'
                        'overridden by the use of -I/--ignore-attrs'
                        '' % IGNORE_ATTRS)
    p.add_argument('-I', '--ignore-attrs', dest='ignore_attrs', type=str,
                   action='append', default=[],
                   help='Attribute name(s) to ignore. Can be specified multiple'
                        ' times. If this option is specified, it overrides both'
                        ' the -i/--also-ignore option and the default list of '
                        'attributes to ignore (%s).' % IGNORE_ATTRS)
    p.add_argument('-s', '--short-test-interval', dest='test_interval',
                   action='store', type=int, default=168,
                   help='Interval in power-on hours at which a "short" device '
                        'test should be run, if not already run within this '
                        'interval. Set to 0 to disable automatic tests. '
                        'Default: 168 (hours; 7 days)')
    p.add_argument('-g', '--graphite-host', dest='graphite_host', type=str,
                   action='store', default=None,
                   help='Enable sending metrics to this Graphite host')
    p.add_argument('-p', '--graphite-port', dest='graphite_port', type=int,
                   action='store', default=2003,
                   help='plaintext port to send Graphite data on '
                        '(default: 2003)')
    default_prefix = '%HOSTNAME%.smart.%SERIAL%'
    p.add_argument('-P', '--graphite-prefix', dest='graphite_prefix', type=str,
                   action='store', default=default_prefix,
                   help='prefix for Graphite metrics; supports interpolation '
                        'of the following: %%HOSTNAME%% -> system hostname, '
                        '%%DEV%% -> device name (e.g. "sdX"), %%SERIAL%% -> '
                        'device serial (default: ' +
                        default_prefix.replace('%', '%%') + ')')
    args = p.parse_args(argv)
    if args.ignore_attrs == []:
        args.ignore_attrs = IGNORE_ATTRS
        args.ignore_attrs.extend(args.also_ignore)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    # set logging
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    script = SmartChecker(
        args.cache_path, blacklist=args.blacklist,
        graphite_host=args.graphite_host,
        graphite_port=args.graphite_port,
        graphite_prefix=args.graphite_prefix,
        test_interval=args.test_interval,
        ignore_attrs=args.ignore_attrs
    )
    script.run()
