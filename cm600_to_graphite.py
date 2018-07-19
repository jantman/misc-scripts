#!/home/jantman/venvs/foo/bin/python
"""
cm600_to_graphite.py
===================

Script to pull stats from Netgear CM-600 and push them to Graphite.

Tested With
-----------

* CM600-1AZNAS (Hardware 1.02, Firmware V1.01.14)

Requirements
------------

- requests
- BeautifulSoup 4

Usage
-----

Export your modem username and password as ``MODEM_USER`` and
``MODEM_PASSWORD`` environment variables, respectively. See
``cm600_to_graphite.py -h`` for further information.

License
-------

Copyright 2018 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/cm600_to_graphite.py>

CHANGELOG
---------

2018-07-18 Jason Antman <jason@jasonantman.com>:
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


class CM600ToGraphite(object):

    def __init__(self, modem_ip, modem_user, modem_passwd,
                 graphite_host='127.0.0.1', graphite_port=2003, dry_run=False,
                 graphite_prefix='cm600'):
        """
        CM600 to Graphite sender

        :param modem_ip: modem IP address
        :type modem_ip: str
        :param modem_user: modem login username
        :type modem_user: str
        :param modem_passwd: modem login password
        :type modem_passwd: sre
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
        self.user = modem_user
        self.passwd = modem_passwd

    def run(self):
        getter = CM600StatsGetter(self.modem_ip, self.user, self.passwd)
        stats = getter.get_stats()
        self.graphite.send_data(stats)
        self.graphite.flush()


class CM600StatsGetter(object):

    TIME_INTERVAL_RE = re.compile(r'^([0-9]+)([dhms])$')

    def __init__(self, ip, user, passwd):
        """
        :param ip: modem IP address
        :type ip: str
        :param user: modem login username
        :type user: str
        :param passwd: modem login passwd
        :type passwd: str
        """
        logger.debug('Initializing CM600StatsGetter ip=%s user=%s', ip, user)
        self.ip = ip
        self.username = user
        self.password = passwd
        self.url = 'http://%s/DocsisStatus.asp' % self.ip

    def get_stats(self):
        """
        Get statistics from modem; return a dict

        :return: stats
        :rtype: dict
        """
        r = requests.get(self.url, auth=(self.username, self.password))
        r.raise_for_status()
        tree = etree.HTML(r.text)
        res = {}
        res.update(self._do_ds(tree.xpath('//table[@id="dsTable"]')[0]))
        res.update(self._do_us(tree.xpath('//table[@id="usTable"]')[0]))
        return res

    def _do_table(self, table):
        headers = []
        res = []
        for tr in table.iter('tr'):
            contents = [x.text for x in tr.iter('td')]
            if headers == []:
                headers = [list(x)[0].text for x in tr.iter('td')]
                continue
            res.append(dict(zip(headers, contents)))
        return res

    def _do_ds(self, table):
        table_dict = self._do_table(table)
        res = {}
        for row in table_dict:
            tmp = {
                'lock_status': 0,
                'frequency_hz': int(row['Frequency'].split()[0]),
                'power_dBmV': float(row['Power'].split()[0]),
                'snr_db': float(row['SNR'].split()[0]),
                'correctables': int(row['Correctables']),
                'uncorrectables': int(row['Uncorrectables'])
            }
            if row['Lock Status'] == 'Locked':
                tmp['lock_status'] = 1
            for k, v in tmp.items():
                res['downstream.%s.%s' % (row['Channel'], k)] = v
        return res

    def _do_us(self, table):
        table_dict = self._do_table(table)
        res = {}
        for row in table_dict:
            tmp = {
                'lock_status': 0,
                'symbol_rate': int(row['Symbol Rate'].split()[0]),
                'frequency_hz': int(row['Frequency'].split()[0]),
                'power_dBmV': float(row['Power'].split()[0])
            }
            if row['Lock Status'] == 'Locked':
                tmp['lock_status'] = 1
            for k, v in tmp.items():
                res['upstream.%s.%s' % (row['Channel'], k)] = v
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
        description='Get stats from CM600 modem, push to graphite'
    )
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-P', '--graphite-prefix', action='store', type=str,
                   dest='prefix', default='cm600',
                   help='graphite metric prefix')
    p.add_argument('-H', '--graphite-host', dest='graphite_host', type=str,
                   action='store', default='127.0.0.1',
                   help='graphite IP or hostname')
    p.add_argument('-p', '--graphite-port', dest='graphite_port', type=int,
                   action='store', default=2003,
                   help='graphite line recevier port')
    p.add_argument('-i', '--ip', dest='modem_ip', action='store', type=str,
                   default='192.168.100.1',
                   help='Modem IP address (default: 192.168.100.1')
    args = p.parse_args(argv)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()
    user = os.environ.get('MODEM_USER', None)
    if user is None:
        raise SystemExit('export MODEM_USER env var')
    passwd = os.environ.get('MODEM_PASSWORD', None)
    if passwd is None:
        raise SystemExit('export MODEM_PASSWORD env var')
    CM600ToGraphite(
        args.modem_ip, user, passwd, dry_run=args.dry_run,
        graphite_prefix=args.prefix, graphite_host=args.graphite_host,
        graphite_port=args.graphite_port
    ).run()
