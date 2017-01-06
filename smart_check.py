#!/usr/bin/env python
"""
smart_check.py
==============

Check SMART status of all attached and SMART-enabled disks via pySMART. Report
on status. Cache status on disk, and exit non-zero if status of any disks
changes.

Requirements
-------------

pySMART (`pip install pySMART`) == 0.3


License
--------

Copyright 2017 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/smart_check.py>

CHANGELOG
----------

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
from platform import node

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)


class SmartChecker(object):

    def __init__(self, cache_path, blacklist=[], graphite_host=None,
                 graphite_port=2003, graphite_prefix=None):
        """ init method, run at class creation """
        self._blacklist = blacklist
        if len(blacklist) > 0:
            logger.info('Ignoring device paths or serials: %s', blacklist)
        self._cache_path = os.path.abspath(os.path.expanduser(cache_path))
        self._cache = self._get_cache()
        self._graphite_host = graphite_host
        self._graphite_port = graphite_port
        self._graphite_prefix = graphite_prefix

    def _get_cache(self):
        logger.debug('Reading state cache from: %s', self._cache_path)
        if not os.path.exists(self._cache_path):
            logger.debug('State cache does not exist.')
            return {}
        with open(self._cache_path, 'r') as fh:
            raw = fh.read()
        cache = json.loads(raw)
        logger.debug('State cache: %s', cache)
        return cache

    def _write_cache(self):
        logger.debug('Writing state cache to: %s', self._cache_path)
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
            self._run_test_if_needed(dev)
            self._send_graphite(dev.name, dev.serial, devinfo[dev.serial])
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
        if len(diffs) == 0:
            logger.info('No differences found for any devices. Exiting.')
            raise SystemExit(0)
        for serial, diff in diffs.iteritems():
            print('Diff for device serial %s:' % serial)
            print("%s\n\n" % diff)
        raise SystemExit(1)

    def _ensure_smart_enabled(self, dev):
        """
        Ensure that SMART and data collection are enabled on the disk.

        :param dev: device to query
        :type dev: pySMART.device.Device
        """
        raise NotImplementedError()

    def _run_test_if_needed(self, dev):
        """
        If a self-test has not been run recently, trigger one. Wait to ensure
        that it starts.

        :param dev: device to query
        :type dev: pySMART.device.Device
        """
        raise NotImplementedError()

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
        raise NotImplementedError()

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
            logger.debug('Graphite disabled; not sending')
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
            logger.debug('Discovered device: %s', dev)
            if not dev.supports_smart:
                logger.warning('Ignoring device that does not support SMART or '
                               'does not have SMART enabled: /dev/%s', dev.name)
                continue
            if '/dev/%s' % dev.name in self._blacklist:
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
        logger.debug('Device %s (/dev/%s) info: %s', dev.serial, dev.model, d)
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
                        'of the following: %HOSTNAME% -> system hostname, '
                        '%DEV% -> device name (e.g. "sdX"), %SERIAL% -> '
                        'device serial (default: ' + default_prefix + ')')
    args = p.parse_args(argv)
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
        graphite_prefix=args.graphite_prefix
    )
    script.run()
