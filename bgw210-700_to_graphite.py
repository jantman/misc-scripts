#!/home/jantman/venvs/foo/bin/python
"""
bgw210-700_to_graphite.py
=========================

Script to pull stats from AT&T / Arris BGW210-700 and push them to Graphite.

Tested With
-----------

* AT&T/Arris BGW210-700 (Software 1.5.12 / Hardware 02001C0046004D)

Requirements
------------

- requests
- BeautifulSoup 4

Usage
-----

See ``cm600_to_graphite.py -h``.

License
-------

Copyright 2018 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/bgw210-700_to_graphite.py>

CHANGELOG
---------

2018-09-01 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import logging
import sys
import argparse
import re
import socket
import os
import time
import codecs
from hashlib import md5

try:
    import requests
except ImportError:
    sys.stderr.write(
        "Error importing requests - 'pip install requests'\n"
    )
    raise SystemExit(1)

try:
    from lxml import etree
except ImportError:
    sys.stderr.write(
        "Error importing lxml - 'pip install lxml'\n"
    )
    raise SystemExit(1)

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class GraphiteSender(object):

    NUM_PER_FLUSH = 20
    FLUSH_SLEEP_SEC = 3

    def __init__(self, host, port, prefix, dry_run=False):
        self.host = host
        self.port = port
        self._prefix = prefix
        self._dry_run = dry_run
        self._send_queue = []
        logger.info('Graphite data will send to %s:%s with prefix: %s.',
                    host, port, prefix)

    def _graphite_send(self, send_str):
        """
        Send data to graphite

        :param send_str: data string to send
        :type send_str: str
        """
        if self._dry_run:
            logger.warning('DRY RUN - Would send to graphite:\n%s', send_str)
            return
        logger.debug('Opening socket connection to %s:%s', self.host, self.port)
        sock = socket.create_connection((self.host, self.port), 10)
        logger.debug('Sending data: "%s"', send_str)
        sock.sendall(send_str.encode('utf-8'))
        logger.info('Data sent to Graphite')
        sock.close()

    def _clean_name(self, metric_name):
        """
        Return a graphite-safe metric name.

        :param metric_name: original metric name
        :type metric_name: str
        :return: graphite-safe metric name
        :rtype: str
        """
        metric_name = metric_name.lower()
        newk = re.sub(r'[^\\.A-Za-z0-9_-]', '_', metric_name)
        if newk != metric_name:
            logger.debug('Cleaned metric name from "%s" to "%s"',
                         metric_name, newk)
        return newk

    def send_data(self, data):
        """
        Queue data to send to graphite. Flush at each given interval.

        :param data: list of data dicts.
        :type data: list
        """
        if isinstance(data, type({})):
            data = [data]
        for d in data:
            ts = d.get('ts', int(time.time()))
            for k in sorted(d.keys()):
                if k == 'ts':
                    continue
                self._send_queue.append((
                    '%s.%s' % (self._prefix, self._clean_name(k)),
                    d[k],
                    ts
                ))
        if len(self._send_queue) >= self.NUM_PER_FLUSH:
            self.flush()

    def flush(self):
        """
        Flush data to Graphite
        """
        logger.debug('Flushing Graphite queue...')
        while len(self._send_queue) > 0:
            send_str = ''
            for i in range(0, self.NUM_PER_FLUSH):
                try:
                    tup = self._send_queue.pop(0)
                except IndexError:
                    break
                send_str += "%s %s %d\n" % (tup[0], tup[1], tup[2])
            if send_str == '':
                return
            self._graphite_send(send_str)
            time.sleep(self.FLUSH_SLEEP_SEC)


class BGW210700ToGraphite(object):

    def __init__(self, modem_ip, graphite_host='127.0.0.1', graphite_port=2003,
                 dry_run=False, graphite_prefix='bgw210_700'):
        """
        BGW210-700 to Graphite sender

        :param modem_ip: modem IP address
        :type modem_ip: str
        :param graphite_host: graphite server IP or hostname
        :type graphite_host: str
        :param graphite_port: graphite line receiver port
        :type graphite_port: int
        :param dry_run: whether to actually send metrics or just print them
        :type dry_run: bool
        :param graphite_prefix: graphite metric prefix
        :type graphite_prefix: str
        """
        self.graphite = GraphiteSender(
            graphite_host, graphite_port, graphite_prefix,
            dry_run=dry_run
        )
        self.dry_run = dry_run
        self.modem_ip = modem_ip

    def run(self):
        getter = BGW210700StatsGetter(self.modem_ip)
        stats = getter.get_stats()
        self.graphite.send_data(stats)
        self.graphite.flush()


class BGW210700StatsGetter(object):

    TIME_INTERVAL_RE = re.compile(r'^([0-9]+)([dhms])$')

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
        r = requests.get(url)
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
            'line_state': int(
                1 if data[
                    'Ethernet Statistics Table'
                ]['Current Speed (Mbps)'] == 'Up' else 0
            ),
            'duplex':
                1 if data[
                    'Ethernet Statistics Table'
                ]['Current Duplex'] == 'full' else 0.5
        }

    def _sysinfo(self):
        tree = self._get_page('http://%s/cgi-bin/sysinfo.ha' % self.ip)
        info = self._do_kv_table(tree.xpath('//table')[0])
        parts = [int(x) for x in info['Time Since Last Reboot'].split(':')]
        return {
            'uptime_sec': parts[0] * 86400 + parts[1] * 3600 +
                          parts[2] * 60 + parts[3]
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
        description='Get stats from BGW210-700 modem, push to graphite'
    )
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-P', '--graphite-prefix', action='store', type=str,
                   dest='prefix', default='bgw210_700',
                   help='graphite metric prefix')
    p.add_argument('-H', '--graphite-host', dest='graphite_host', type=str,
                   action='store', default='127.0.0.1',
                   help='graphite IP or hostname')
    p.add_argument('-p', '--graphite-port', dest='graphite_port', type=int,
                   action='store', default=2003,
                   help='graphite line recevier port')
    p.add_argument('-i', '--ip', dest='modem_ip', action='store', type=str,
                   default='192.168.1.254',
                   help='Modem IP address (default: 192.168.1.254')
    args = p.parse_args(argv)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()
    BGW210700ToGraphite(
        args.modem_ip, dry_run=args.dry_run, graphite_prefix=args.prefix,
        graphite_host=args.graphite_host, graphite_port=args.graphite_port
    ).run()
