#!/usr/bin/env python3
"""
bgw210-700_prom_collector.py
=============================

Prometheus collector script to pull stats from AT&T / Arris BGW210-700 and
expose them as Prometheus metrics.

Tested With
-----------

* AT&T/Arris BGW210-700 (Software 1.5.12 / Hardware 02001C0046004D)

Requirements
------------

- requests
- lxml
- prometheus-client

Usage
-----

Run as a standalone HTTP server:
    python3 bgw210-700_prom_collector.py --port 8000 --ip 192.168.1.254

Then scrape metrics from http://localhost:8000/metrics

License
-------

Copyright 2025 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/bgw210-700_prom_collector.py>

CHANGELOG
---------

2025-05-29 Jason Antman <jason@jasonantman.com>:
  - initial version of script based on bgw210-700_to_graphite.py
"""

import logging
import sys
import argparse
import re
import time
from urllib.parse import urlparse

import requests
from lxml import etree
from prometheus_client import start_http_server, Gauge, Counter, REGISTRY
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class BGW210700Collector:
    """
    Prometheus collector for BGW210-700 modem metrics
    """

    def __init__(self, modem_ip):
        """
        Initialize the collector

        :param modem_ip: modem IP address
        :type modem_ip: str
        """
        self.modem_ip = modem_ip
        self.stats_getter = BGW210700StatsGetter(modem_ip)

    def collect(self):
        """
        Collect metrics from the modem and yield them
        """
        try:
            stats = self.stats_getter.get_stats()
            
            # Create gauge metrics
            connection_status = GaugeMetricFamily(
                'bgw210_connection_status',
                'Broadband connection status (1=up, 0=down)'
            )
            connection_status.add_metric([], stats.get('connection', 0))
            yield connection_status
            
            uptime_seconds = GaugeMetricFamily(
                'bgw210_uptime_seconds',
                'Time since last reboot in seconds'
            )
            uptime_seconds.add_metric([], stats.get('uptime_sec', 0))
            yield uptime_seconds
            
            line_speed_mbps = GaugeMetricFamily(
                'bgw210_line_speed_mbps',
                'Current line speed in Mbps'
            )
            line_speed_mbps.add_metric([], stats.get('line_speed', 0))
            yield line_speed_mbps
            
            line_state = GaugeMetricFamily(
                'bgw210_line_state',
                'Line state (1=up, 0=down)'
            )
            line_state.add_metric([], stats.get('line_state', 0))
            yield line_state
            
            duplex_status = GaugeMetricFamily(
                'bgw210_duplex_status',
                'Duplex status (1=full, 0.5=half)'
            )
            duplex_status.add_metric([], stats.get('duplex', 0))
            yield duplex_status
            
            # Create counter metrics for IPv4
            ipv4_rx_bytes = CounterMetricFamily(
                'bgw210_ipv4_rx_bytes_total',
                'IPv4 received bytes total'
            )
            ipv4_rx_bytes.add_metric([], stats.get('ipv4.rx_bytes', 0))
            yield ipv4_rx_bytes
            
            ipv4_tx_bytes = CounterMetricFamily(
                'bgw210_ipv4_tx_bytes_total',
                'IPv4 transmitted bytes total'
            )
            ipv4_tx_bytes.add_metric([], stats.get('ipv4.tx_bytes', 0))
            yield ipv4_tx_bytes
            
            ipv4_rx_packets = CounterMetricFamily(
                'bgw210_ipv4_rx_packets_total',
                'IPv4 received packets total'
            )
            ipv4_rx_packets.add_metric([], stats.get('ipv4.rx_packets', 0))
            yield ipv4_rx_packets
            
            ipv4_tx_packets = CounterMetricFamily(
                'bgw210_ipv4_tx_packets_total',
                'IPv4 transmitted packets total'
            )
            ipv4_tx_packets.add_metric([], stats.get('ipv4.tx_packets', 0))
            yield ipv4_tx_packets
            
            ipv4_rx_unicast = CounterMetricFamily(
                'bgw210_ipv4_rx_unicast_total',
                'IPv4 received unicast packets total'
            )
            ipv4_rx_unicast.add_metric([], stats.get('ipv4.rx_unicast', 0))
            yield ipv4_rx_unicast
            
            ipv4_tx_unicast = CounterMetricFamily(
                'bgw210_ipv4_tx_unicast_total',
                'IPv4 transmitted unicast packets total'
            )
            ipv4_tx_unicast.add_metric([], stats.get('ipv4.tx_unicast', 0))
            yield ipv4_tx_unicast
            
            ipv4_rx_multicast = CounterMetricFamily(
                'bgw210_ipv4_rx_multicast_total',
                'IPv4 received multicast packets total'
            )
            ipv4_rx_multicast.add_metric([], stats.get('ipv4.rx_multicast', 0))
            yield ipv4_rx_multicast
            
            ipv4_tx_multicast = CounterMetricFamily(
                'bgw210_ipv4_tx_multicast_total',
                'IPv4 transmitted multicast packets total'
            )
            ipv4_tx_multicast.add_metric([], stats.get('ipv4.tx_multicast', 0))
            yield ipv4_tx_multicast
            
            ipv4_rx_errors = CounterMetricFamily(
                'bgw210_ipv4_rx_errors_total',
                'IPv4 receive errors total'
            )
            ipv4_rx_errors.add_metric([], stats.get('ipv4.rx_errors', 0))
            yield ipv4_rx_errors
            
            ipv4_tx_errors = CounterMetricFamily(
                'bgw210_ipv4_tx_errors_total',
                'IPv4 transmit errors total'
            )
            ipv4_tx_errors.add_metric([], stats.get('ipv4.tx_errors', 0))
            yield ipv4_tx_errors
            
            ipv4_rx_drops = CounterMetricFamily(
                'bgw210_ipv4_rx_drops_total',
                'IPv4 receive drops total'
            )
            ipv4_rx_drops.add_metric([], stats.get('ipv4.rx_drops', 0))
            yield ipv4_rx_drops
            
            ipv4_tx_drops = CounterMetricFamily(
                'bgw210_ipv4_tx_drops_total',
                'IPv4 transmit drops total'
            )
            ipv4_tx_drops.add_metric([], stats.get('ipv4.tx_drops', 0))
            yield ipv4_tx_drops
            
            ipv4_collisions = CounterMetricFamily(
                'bgw210_ipv4_collisions_total',
                'IPv4 collisions total'
            )
            ipv4_collisions.add_metric([], stats.get('ipv4.collisions', 0))
            yield ipv4_collisions
            
            # Create counter metrics for IPv6
            ipv6_tx_packets = CounterMetricFamily(
                'bgw210_ipv6_tx_packets_total',
                'IPv6 transmitted packets total'
            )
            ipv6_tx_packets.add_metric([], stats.get('ipv6.tx_packets', 0))
            yield ipv6_tx_packets
            
            ipv6_tx_errors = CounterMetricFamily(
                'bgw210_ipv6_tx_errors_total',
                'IPv6 transmit errors total'
            )
            ipv6_tx_errors.add_metric([], stats.get('ipv6.tx_errors', 0))
            yield ipv6_tx_errors
            
            ipv6_tx_discards = CounterMetricFamily(
                'bgw210_ipv6_tx_discards_total',
                'IPv6 transmit discards total'
            )
            ipv6_tx_discards.add_metric([], stats.get('ipv6.tx_discards', 0))
            yield ipv6_tx_discards
            
            logger.debug('Successfully collected metrics from modem')
            
        except Exception as e:
            logger.error('Error collecting metrics from modem: %s', e)
            # Yield a connection status metric set to 0 on error
            connection_status = GaugeMetricFamily(
                'bgw210_connection_status',
                'Broadband connection status (1=up, 0=down)'
            )
            connection_status.add_metric([], 0)
            yield connection_status


class BGW210700StatsGetter:
    """
    Class to get statistics from BGW210-700 modem
    """

    def __init__(self, ip):
        """
        :param ip: modem IP address
        :type ip: str
        """
        logger.debug('Initializing BGW210700StatsGetter ip=%s', ip)
        self.ip = ip

    def get_stats(self):
        """
        Get statistics from modem; return a dict

        :return: stats
        :rtype: dict
        """
        res = {}
        res.update(self._sysinfo())
        res.update(self._broadband_stats())
        return res

    def _get_page(self, url):
        logger.debug('GET: %s', url)
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        tree = etree.HTML(r.text)
        return tree

    def _do_kv_table(self, table):
        res = {}
        for tr in table.iter('tr'):
            if len(tr) != 2 or tr[0].tag != 'th' or tr[1].tag != 'td':
                continue
            if tr[1].text is not None:
                res[tr[0].text.strip()] = tr[1].text.strip()
        return res

    def _broadband_stats(self):
        tree = self._get_page(
            'http://%s/cgi-bin/broadbandstatistics.ha' % self.ip
        )
        data = {}
        for tbl in tree.iter('table'):
            summary = tbl.get('summary', None)
            if summary is None:
                continue
            data[summary] = self._do_kv_table(tbl)
        
        bs = 'Summary of the most important WAN information'
        
        # Parse line state correctly
        line_state_text = data.get('Ethernet Statistics Table', {}).get('Current Status', 'Down')
        line_state = 1 if line_state_text == 'Up' else 0
        
        return {
            'connection': 1 if data[bs]['Broadband Connection'] == 'Up' else 0,
            'ipv6.tx_discards': int(
                data['IPv6 Statistics Table']['Transmit Discards']
            ),
            'ipv6.tx_errors': int(
                data['IPv6 Statistics Table']['Transmit Errors']
            ),
            'ipv6.tx_packets': int(
                data['IPv6 Statistics Table']['Transmit Packets']
            ),
            'ipv4.rx_drops': int(
                data['Ethernet IPv4 Statistics Table']['Receive Drops']
            ),
            'ipv4.tx_drops': int(
                data['Ethernet IPv4 Statistics Table']['Transmit Drops']
            ),
            'ipv4.rx_unicast': int(
                data['Ethernet IPv4 Statistics Table']['Receive Unicast']
            ),
            'ipv4.tx_bytes': int(
                data['Ethernet IPv4 Statistics Table']['Transmit Bytes']
            ),
            'ipv4.rx_errors': int(
                data['Ethernet IPv4 Statistics Table']['Receive Errors']
            ),
            'ipv4.rx_bytes': int(
                data['Ethernet IPv4 Statistics Table']['Receive Bytes']
            ),
            'ipv4.tx_packets': int(
                data['Ethernet IPv4 Statistics Table']['Transmit Packets']
            ),
            'ipv4.rx_packets': int(
                data['Ethernet IPv4 Statistics Table']['Receive Packets']
            ),
            'ipv4.collisions': int(
                data['Ethernet IPv4 Statistics Table']['Collisions']
            ),
            'ipv4.rx_multicast': int(
                data['Ethernet IPv4 Statistics Table']['Receive Multicast']
            ),
            'ipv4.tx_multicast': int(
                data['Ethernet IPv4 Statistics Table']['Transmit Multicast']
            ),
            'ipv4.tx_unicast': int(
                data['Ethernet IPv4 Statistics Table']['Transmit Unicast']
            ),
            'ipv4.tx_errors': int(
                data['Ethernet IPv4 Statistics Table']['Transmit Errors']
            ),
            'line_speed': int(
                data['Ethernet Statistics Table']['Current Speed (Mbps)']
            ),
            'line_state': line_state,
            'duplex': 1 if data[
                'Ethernet Statistics Table'
            ]['Current Duplex'] == 'full' else 0.5
        }

    def _sysinfo(self):
        tree = self._get_page('http://%s/cgi-bin/sysinfo.ha' % self.ip)
        info = self._do_kv_table(tree.xpath('//table')[0])
        return {
            'uptime_sec': int(info['Time Since Last Reboot'])
        }


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
        description='BGW210-700 Prometheus metrics collector'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-p', '--port', dest='port', type=int,
                   action='store', default=8000,
                   help='HTTP server port (default: 8000)')
    p.add_argument('-i', '--ip', dest='modem_ip', action='store', type=str,
                   default='192.168.1.254',
                   help='Modem IP address (default: 192.168.1.254)')
    p.add_argument('--host', dest='host', action='store', type=str,
                   default='0.0.0.0',
                   help='HTTP server bind address (default: 0.0.0.0)')
    args = p.parse_args(argv)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    elif args.verbose > 0:
        set_log_info()

    # Create and register the collector
    collector = BGW210700Collector(args.modem_ip)
    REGISTRY.register(collector)

    # Start the HTTP server
    logger.info('Starting HTTP server on %s:%d', args.host, args.port)
    start_http_server(args.port, addr=args.host)
    
    logger.info('Metrics available at http://%s:%d/metrics', args.host, args.port)
    
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        sys.exit(0)