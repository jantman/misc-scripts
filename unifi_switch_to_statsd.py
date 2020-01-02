#!/usr/bin/env python3
"""
unifi_switch_to_statsd.py
=========================

Script to pull per-port stats from a UniFi switch and push them to statsd.

Tested With
-----------

* Ubiquiti UniFi Switch 16

Requirements
------------

- pysnmp (``pip install pysnmp``) - developed against 4.4.12

Usage
-----

See ``unifi_switch_to_statsd.py -h``.

License
-------

Copyright 2020 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/unifi_switch_to_statsd.py>

CHANGELOG
---------

2020-01-01 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import logging
import sys
import argparse
import re
import socket
import time
import json
from typing import Union, Dict, List, Any
from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData, ObjectType,
    ObjectIdentity, nextCmd, Integer32, Gauge32, Integer, Counter32, Counter64
)


FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class StatsdSender:

    def __init__(
        self, host: str, port: int, prefix: str, dry_run: bool = False,
        flush_sleep_sec: float = 0.0, num_per_flush: int = 40
    ):
        self.host: str = host
        self.port: int = port
        self._prefix: str = prefix
        self._dry_run: bool = dry_run
        self._flush_sleep_sec = flush_sleep_sec
        self._num_per_flush = num_per_flush
        self._send_queue: list = []
        logger.info(
            'statsd data will send to %s:%s with prefix: %s.',
            host, port, prefix
        )

    def _statsd_send(self, send_str: str):
        """
        Send data to statsd

        :param send_str: data string to send
        :type send_str: str
        """
        if self._dry_run:
            logger.warning('DRY RUN - Would send to statsd:\n%s', send_str)
            return
        logger.debug('Opening socket connection to %s:%s', self.host, self.port)
        sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((self.host, self.port))
        logger.debug('Sending data: "%s"', send_str)
        sock.sendall(send_str.encode('utf-8'))
        logger.debug('Data sent to statsd')
        sock.close()

    def _clean_name(self, metric_name: str):
        """
        Return a statsd-safe metric name.

        :param metric_name: original metric name
        :type metric_name: str
        :return: statsd-safe metric name
        :rtype: str
        """
        metric_name: str = metric_name.lower()
        newk: str = re.sub(r'[^\\.A-Za-z0-9_-]', '_', metric_name)
        if newk != metric_name:
            logger.debug('Cleaned metric name from "%s" to "%s"',
                         metric_name, newk)
        return newk

    def send_data(self, data: List[str]):
        """
        Queue data to send to statsd. Flush at each given interval.

        Accepts either a list of strings ready to send to statsd, but which will
        be prefixed with ``self._prefix``.

        :param data: list of strings for statsd.
        :type data: list
        """
        s: str = ''
        for s in data:
            self._send_queue.append(f'{self._prefix}.{s}')
        if len(self._send_queue) >= self._num_per_flush:
            self.flush()

    def flush(self):
        """
        Flush data to statsd
        """
        logger.debug('Flushing statsd queue...')
        while len(self._send_queue) > 0:
            send_str: str = ''
            i: int
            for i in range(0, self._num_per_flush):
                try:
                    send_str += f'{self._send_queue.pop(0)}\n'
                except IndexError:
                    break
            if send_str == '':
                return
            self._statsd_send(send_str)
            time.sleep(self._flush_sleep_sec)


class UniFiSwitchToStatsd:

    def __init__(self, switch_ip: str, community: str = 'public',
                 statsd_host: str = '127.0.0.1',
                 statsd_port: int = 8125, dry_run: bool = False,
                 statsd_prefix: str = 'unifi_switch'):
        """
        UniFi switch to statsd sender

        :param switch_ip: switch IP address
        :type switch_ip: str
        :param community: SNMP v1 community string
        :type community: str
        :param statsd_host: statsd server IP or hostname
        :type statsd_host: str
        :param statsd_port: statsd port
        :type statsd_port: int
        :param dry_run: whether to actually send metrics or just print them
        :type dry_run: bool
        :param statsd_prefix: statsd metric prefix
        :type statsd_prefix: str
        """
        self.statsd: StatsdSender = StatsdSender(
            statsd_host, statsd_port, statsd_prefix, dry_run=dry_run
        )
        self.dry_run: bool = dry_run
        self.switch_ip: str = switch_ip
        self.community: str = community
        logger.debug('Will connect to switch at: %s:161', self.switch_ip)
        self.engine: SnmpEngine = SnmpEngine()
        self.cdata: CommunityData = CommunityData(self.community, mpModel=0)
        self.target: UdpTransportTarget = UdpTransportTarget(
            (self.switch_ip, 161)
        )
        self.if_names: dict = {}
        self.if_aliases: dict = {}
        self.if_metric_names: dict = {}

    def run(self, onetime=False, interval=10):
        logger.debug('Getting iterface names and aliases')
        for idx, vals in self.table([
            ObjectType(ObjectIdentity('IF-MIB', 'ifName')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifAlias')),
        ]).items():
            self.if_names[idx] = vals['ifName']
            self.if_aliases[idx] = vals['ifAlias']
            self.if_metric_names[idx] = self._metric_for_if(
                vals['ifName'], vals['ifAlias'], idx
            )
        logger.debug('Set ifNames: %s', self.if_names)
        logger.debug('Set ifAliases: %s', self.if_aliases)
        logger.info('Set if_metric_names: %s', self.if_metric_names)
        while True:
            start = time.time()
            self.do_iteration()
            if onetime:
                break
            duration = time.time() - start
            if duration < interval:
                logger.debug('Sleep %s seconds', interval - duration)
                time.sleep(interval - duration)

    def _metric_for_if(self, name: str, alias: str, idx: int) -> str:
        if alias is not None and alias.strip() != '':
            return self.statsd._clean_name(alias)
        if name is not None and name.strip() != '':
            return self.statsd._clean_name(name)
        return f'{idx}'

    def do_iteration(self):
        stats: dict = self.get_stats()
        logger.debug('Stats: %s', json.dumps(stats, sort_keys=True))
        buf: list = []
        for idx, data in stats.items():
            mname = self.if_metric_names[idx]
            for k, v in data.items():
                buf.append(f'{mname}.{k}:{v}|g')
            self.statsd.send_data(buf)
            buf = []
        self.statsd.flush()

    def get_stats(self) -> dict:
        logger.debug('Getting statistics')
        stats = self.table([
            ObjectType(ObjectIdentity('IF-MIB', 'ifAdminStatus')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifOperStatus')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifInOctets')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifInUcastPkts')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifInNUcastPkts')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifInDiscards')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifInErrors')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifOutOctets')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifOutUcastPkts')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifOutNUcastPkts')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifOutDiscards')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifOutErrors')),
        ])
        for idx, vals in self.table([
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsAlignmentErrors'
            )),
            ObjectType(ObjectIdentity('EtherLike-MIB', 'dot3StatsFCSErrors')),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsSingleCollisionFrames'
            )),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsMultipleCollisionFrames'
            )),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsSQETestErrors'
            )),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsDeferredTransmissions'
            )),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsLateCollisions'
            )),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsExcessiveCollisions'
            )),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsInternalMacTransmitErrors'
            )),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsCarrierSenseErrors'
            )),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsFrameTooLongs'
            )),
            ObjectType(ObjectIdentity(
                'EtherLike-MIB', 'dot3StatsInternalMacReceiveErrors'
            )),
            ObjectType(ObjectIdentity('EtherLike-MIB', 'dot3InPauseFrames')),
            ObjectType(ObjectIdentity('EtherLike-MIB', 'dot3OutPauseFrames')),
        ]).items():
            if idx not in stats:
                stats[idx] = {}
            stats[idx].update(vals)
        for idx, vals in self.table([
            ObjectType(ObjectIdentity('IF-MIB', 'ifInMulticastPkts')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifInBroadcastPkts')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifOutMulticastPkts')),
            ObjectType(ObjectIdentity('IF-MIB', 'ifOutBroadcastPkts')),
        ]).items():
            if idx not in stats:
                stats[idx] = {}
            stats[idx].update(vals)
        return stats

    def _decode_identity(self, oid: ObjectIdentity) -> tuple:
        sym: tuple = oid.getMibSymbol()
        assert len(sym[2]) == 1
        assert sym[2][0].__class__.__name__ == 'InterfaceIndex'
        return sym[0], sym[1], sym[2][0]._value

    def _decode_value(self, val: Any) -> Any:
        # we have to use class names here, since we can't import the actual
        # value classes
        if val.__class__.__name__ == 'DisplayString':
            return val.prettyPrint()
        if (
            isinstance(val, Integer32) or
            isinstance(val, Integer) or
            isinstance(val, Counter32) or
            isinstance(val, Counter64) or
            isinstance(val, Gauge32)
        ):
            return val._value
        if val.__class__.__name__ == 'PhysAddress':
            return val.prettyPrint()
        if val.__class__.__name__ == 'EndOfMibView':
            return None
        raise RuntimeError(
            f'ERROR: No decoder for value: {val} ({type(val)})'
        )

    def table(self, objects: list) -> dict:
        res = {}
        for (
            error_indication, error_status, error_index, var_binds
        ) in nextCmd(
            self.engine, self.cdata, self.target, ContextData(),
            *objects,
            lexicographicMode=False
        ):
            if error_indication:
                logger.error('SNMP GET error_indication: %s', error_indication)
                raise RuntimeError(
                    f'snmp table: error_indication: {error_indication}'
                )
            elif error_status:
                logger.error(
                    'SNMP GET error_status: %s at %s', error_status,
                    error_index and var_binds[int(error_index) - 1][0] or '?'
                )
                loc = error_index and var_binds[int(error_index) - 1][0] or '?'
                raise RuntimeError(
                    f'snmp table: error_status: {error_status} at '
                    f"{loc}"
                )
            for varBind in var_binds:
                _, itemname, idx = self._decode_identity(varBind[0])
                if idx not in res:
                    res[idx] = {}
                res[idx][itemname] = self._decode_value(varBind[1])
        return res


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


def set_log_level_format(level: int, format: str):
    """
    Set logger level and format.

    :param level: logging level; see the :py:mod:`logging` constants.
    :type level: int
    :param format: logging formatter format string
    :type format: str
    """
    formatter: logging.Formatter = logging.Formatter(fmt=format)
    logger.handlers[0].setFormatter(formatter)
    logger.setLevel(level)


def parse_args(argv: list):
    p: argparse.ArgumentParser = argparse.ArgumentParser(
        description='Get stats from a UniFi switch, push to statsd'
    )
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - print metrics instead of sending them")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-P', '--statsd-prefix', action='store', type=str,
                   dest='prefix', default='unifi_switch',
                   help='statsd metric prefix (default: unifi_switch)')
    p.add_argument('-H', '--statsd-host', dest='statsd_host', type=str,
                   action='store', default='127.0.0.1',
                   help='statsd IP or hostname (default: 127.0.0.1)')
    p.add_argument('-p', '--statsd-port', dest='statsd_port', type=int,
                   action='store', default=8125,
                   help='statsd port (default: 8125)')
    p.add_argument('-c', '--community', dest='community', type=str,
                   action='store', default='public',
                   help='community string (default: public)')
    p.add_argument('-o', '--one-time', dest='onetime', action='store_true',
                   default=False, help='Run one iteration and then exit.')
    p.add_argument('-i', '--interval', dest='interval', action='store',
                   type=int, default=10,
                   help='Polling interval in seconds (default: 10)')
    p.add_argument('SWITCH_IP', type=str, action='store', help='Switch IP')
    args = p.parse_args(argv)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()
    UniFiSwitchToStatsd(
        args.SWITCH_IP, community=args.community, dry_run=args.dry_run,
        statsd_prefix=args.prefix, statsd_host=args.statsd_host,
        statsd_port=args.statsd_port
    ).run(onetime=args.onetime, interval=args.interval)
