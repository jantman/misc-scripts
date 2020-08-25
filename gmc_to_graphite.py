#!/usr/bin/env python
"""
gmc_to_graphite.py
==================

Script to pull stats from GQ GMC-500+ and push them to Graphite.

Requirements
------------

- pyudev
- git+https://gitlab.com/jantman/gmc.git@jantman-fixes-config
"""

import sys
import argparse
import logging
import socket
import os
import time
import re
from glob import iglob
from pyudev import Context, Devices
from gmc import GMC
from termios import error

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class GMC500ToStatsd(object):

    def __init__(self, statsd_host='127.0.0.1', statsd_port=8125,
                 dry_run=False, metric_prefix='cm600'):
        """
        CM600 to Graphite sender

        :param statsd_host: statsd server IP or hostname
        :type statsd_host: str
        :param statsd_port: statsd line receiver port
        :type graphite_port: int
        :param dry_run: whether to actually send metrics or just print them
        :type dry_run: bool
        :param metric_prefix: metric prefix
        :type metric_prefix: str
        """
        self._statsd_host = statsd_host
        self._statsd_port = statsd_port
        self._metric_prefix = metric_prefix
        self.dry_run = dry_run
        self._gmc = None
        self._init_gmc()

    def _init_gmc(self):
        devname = None
        if devname is None:
            devname = self._find_usb_device()
        if devname is None:
            raise RuntimeError(
                'ERROR: No devname given, and could not determine GMC-500+ '
                'device name using pyudev.'
            )
        logger.info('Using device: %s', devname)
        logger.debug('Connecting to GMC...')
        self._gmc = GMC(config_update={'DEFAULT_PORT': devname})
        logger.debug('Connected.')

    def _statsd_send(self, metrics):
        msg = ''
        for k, v in metrics.items():
            msg += '%s.%s:%d|g\n' % (self._metric_prefix, k, v)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        logger.debug('statsd send: %s', msg.replace("\n", '\\n'))
        sock.sendto(msg.encode('ascii'), (self._statsd_host, self._statsd_port))
        sock.close()

    def run(self):
        while True:
            try:
                cps = self._gmc.cps(numeric=True)
                cpsl = self._gmc.cpsl(numeric=True)
                cpsh = self._gmc.cpsh(numeric=True)
                cpm = self._gmc.cpm(numeric=True)
                cpml = self._gmc.cpml(numeric=True)
                cpmh = self._gmc.cpmh(numeric=True)
                maxcps = self._gmc.max_cps(numeric=True)
                logger.debug('End querying GMC')
                stats = {
                    'cps': cps,
                    'cpsl': cpsl,
                    'cpsh': cpsh,
                    'cpm': cpm,
                    'cpml': cpml,
                    'cpmh': cpmh,
                    'maxcps': maxcps
                }
                self._statsd_send(stats)
            except error:
                self._gmc = None
                self._init_gmc()
            time.sleep(10)

    def _find_usb_device(self):
        gmc_vendor_model_revision = [
            ('1a86', '7523', '0263')
        ]
        logger.debug('Using pyudev to find GMC tty device')
        context = Context()
        for devname in iglob('/dev/ttyUSB*'):
            device = Devices.from_device_file(context, devname)
            if device.properties['ID_BUS'] != 'usb':
                continue
            k = (
                device.properties['ID_VENDOR_ID'],
                device.properties['ID_MODEL_ID'],
                device.properties['ID_REVISION']
            )
            if k in gmc_vendor_model_revision:
                logger.debug('Found GMC-500+ at: %s', devname)
                return devname
        return None


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


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Get stats from GQ GMC-500, push to statsd'
    )
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-P', '--prefix', action='store', type=str,
                   dest='prefix', default='gmc500',
                   help='metric prefix')
    p.add_argument('-H', '--statsd-host', dest='statsd_host', type=str,
                   action='store', default='127.0.0.1',
                   help='statsd IP or hostname')
    p.add_argument('-p', '--statsd-port', dest='statsd_port', type=int,
                   action='store', default=8125,
                   help='statsd port')
    args = p.parse_args(argv)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()
    GMC500ToStatsd(
        dry_run=args.dry_run,
        metric_prefix=args.prefix, statsd_host=args.statsd_host,
        statsd_port=args.statsd_port
    ).run()
