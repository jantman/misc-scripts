#!/usr/bin/env python
"""
Watts Up Pro Logger
===================

Logs a few status messages from a Watts Up Pro USB data collector to a file.

NOTE: Values will be transformed. I.e. the communication protocol returns
watts in 1/10 W, but we log/output Watts.

Information on the communications protocol came from:
https://www.wattsupmeters.com/secure/downloads/CommunicationsProtocol090824.pdf

WARNING - This script will clear the internal logging memory of the Watts Up.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/watts_up_pro_logger.py>

Requirements
------------

pyserial (`pip install pyserial`)

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>

License
-------

These programs are free software: you can redistribute them and/or modify
them under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your option)
any later version. A copy of the GPL version 3 license can be found in the file
COPYING or at http://www.gnu.org/licenses.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

Credits
-------

The code to actually read from the Watts Up is based on
<https://github.com/kjordahl/Watts-Up--logger>, also licensed
under GPL v3+. My use case was different enough I opted not to
fork and pull request.

CHANGELOG
---------
2016-12-26 Jason Antman <jason@jasonantman.com>:
  - add Graphite support
2016-08-10 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import os
from datetime import datetime
import time
from collections import defaultdict
import socket
import re

import serial  # distribution: pyserial

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class WattsUpReader(object):
    """Read data from the Watts Up Pro"""

    _MODELS = {
        '0': 'Standard',
        '1': 'Pro',
        '2': 'ES',
        '3': 'Ethernet (.net)',
        '4': 'Blind Module'
    }

    def __init__(self, device='/dev/ttyUSB0', interval=1):
        """ init method, run at class creation """
        logger.info('Reading WattsUp Pro from: %s', device)
        self.device = device
        logger.debug('Opening port at 115200 baud')
        self.dev = serial.Serial(device, 115200)
        # get version
        self.query_version()
        self.fields = self.get_fields()
        logger.info('WattsUp response fields: %s', self.fields)
        msg = '#L,W,3,E,,%d;' % interval
        logger.debug('Setting WattsUp to External logging mode at %ds '
                     '(message: %s)', interval, msg)
        self.dev.write(msg)

    def query_version(self):
        """query the WattsUp for its version"""
        msg = '#V,R,0;'
        logger.debug('Querying WattsUp for version (message: %s)')
        self.dev.write(msg)
        verline = None
        while verline is None:
            line = self.dev.readline().strip().strip('\x00').strip(';')
            logger.debug('Got line: %s', line)
            if line.startswith('#v,'):
                verline = line
        (_, _, _, model, memory, hw_major, hw_minor, fw_major, fw_minor,
        fw_timestamp, checksum) = line.split(',')
        logger.info('Connected to WattsUp; Model=%s (%s), Memory=%s, '
                    'HW_Major=%s, HW_Minor=%s, FW_Major=%s, FW_Minor=%s, '
                    'FW_Timestamp=%s', model,
                    self._MODELS.get(model, 'unknown'), memory,
                    hw_major, hw_minor, fw_major, fw_minor, fw_timestamp)

    def get_fields(self):
        """set the WattsUp to log all fields, and return the names of them"""
        msg = '#H,R,0;'
        logger.debug('Getting field header from device (message: %s)', msg)
        self.dev.write(msg)
        headline = None
        while headline is None:
            line = self.dev.readline().strip().strip('\x00').strip(';')
            logger.debug('Got line: %s', line)
            if line.startswith('#h,-,'):
                headline = line
        parts = headline.split(',')
        return parts[3:]

    def read(self, num_samples):
        """
        read and return num_samples of data

        :param num_samples: number of samples of data to read
        :type num_samples: int
        :returns: list of data dicts, each having fields representing the data
          values from the device, plus a 'datetime' field of when the data was
          read.
        :rtype: list
        """
        got_samples = 0
        samples = []
        while got_samples <= num_samples:
            line = self.dev.readline().strip().strip('\x00;\r')
            logger.debug("Got line: %s", line)
            if not line.startswith('#d,-,'):
                continue
            got_samples += 1
            d = self._transform_data_line(line)
            logger.debug('Data for line: %s', d)
            samples.append(d)
        return samples

    def _transform_data_line(self, line):
        """
        Parse a line of reading data, transform the values, return a dict of
        data with human-readable keys, plus timestamp.

        :param line: line of data read from device
        :type line: str
        :return: dict of data
        :rtype: dict
        """
        parts = line.split(',')[3:]
        data = dict(zip(self.fields, parts))
        logger.debug('Raw line data: %s', data)
        result = {'datetime': datetime.now()}
        for k, v in data.items():
            if k == 'W':
                result['watts'] = float(v) / 10.0
            elif k == 'V':
                result['volts'] = float(v)/ 10.0
            elif k == 'A':
                result['amps'] = float(v) / 10.0
            elif k == 'WH':
                result['WH'] = float(v) / 10.0  # watt-hours
            elif k == 'Cost':
                result['cost'] = float(v) / 10.0
            elif k == 'WH/Mo':
                result['WH/Mo'] = int(v)
            elif k == 'Cost/Mo':
                result['Cost/Mo'] = float(v) / 10.0
            elif k == 'Wmax':
                continue
            elif k == 'Vmax':
                continue
            elif k == 'Amax':
                continue
            elif k == 'Wmin':
                continue
            elif k == 'Vmin':
                continue
            elif k == 'Amin':
                continue
            elif k == 'PF':
                result['PowerFactor'] = int(v)
            elif k == 'DC':
                result['DutyCycle'] = int(v)
            elif k == 'PC':
                result['PowerCycle'] = int(v)
            elif k == 'Hz':
                result['Hz'] = float(v) / 10.0
            elif k == 'VA':
                result['VA'] = float(v) / 10.0
            else:
                result[k] = v
        return result


class Logger(object):

    def __init__(self, fpath):
        if fpath is None:
            self.fpath = None
            logger.info('Logging to STDOUT')
        else:
            self.fpath = os.path.abspath(os.path.expanduser(fpath))
            logger.info('Logging to: %s', self.fpath)

    def _write_log_lines(self, header_line, lines):
        """
        Given a list of log lines, write them to either a file or STDOUT,
        based on ``self.fpath``.

        :param header_line: first (header) line
        :type header_line: str
        :param lines: lines to log
        :type lines: list
        """
        if self.fpath is None:
            print(header_line)
            for line in lines:
                print(line)
            return
        write_header = False
        if ((not os.path.exists(self.fpath)) or
                         os.stat(self.fpath).st_size == 0):
            write_header = True
        with open(self.fpath, 'a') as fh:
            if write_header:
                fh.write(header_line + "\n")
            for line in lines:
                fh.write(line + "\n")

    def log_data(self, data):
        """
        Log data to the file specified by ``self.fpath``.

        Add a header to the file if it doesn't exist.

        :param data: list of data dicts
        :type data: list
        """
        header = sorted(data[0].keys())
        # move timestamp to the front
        header.remove('datetime')
        header.insert(0, 'datetime')
        header.insert(1, 'timestamp')
        header_line = ','.join(header)
        lines = []
        for d in data:
            line = []
            for k in header:
                if k == 'datetime':
                    line.append(d[k].strftime('%Y-%m-%dT%H:%M:%S'))
                elif k == 'timestamp':
                    line.append('%d' % time.mktime(d['datetime'].timetuple()))
                else:
                    line.append(str(d[k]))
            lines.append(','.join(line))
        self._write_log_lines(header_line, lines)

    def log_average(self, data):
        """
        Log average of data to the file specified by ``self.fpath``.

        Add a header to the file if it doesn't exist.

        :param data: list of data dicts
        :type data: list
        """
        avgs = defaultdict(list)
        dt = None
        for record in data:
            if dt is None:
                dt = record['datetime']
            for key, val in record.items():
                if key == 'datetime':
                    continue
                avgs[key].append(val)
        result = {}
        for key, values in avgs.items():
            if key.endswith('min'):
                result[key] = min(values)
            elif key.endswith('max'):
                result[key] = max(values)
            else:
                # mean
                result[key] = sum(values) / float(len(values))
        result['datetime'] = dt
        self.log_data([result])


class GraphiteSender(object):

    def __init__(self, host, port):
        self.host = host
        self.port = port
        logger.info('Sending graphite data to %s:%s', host, port)

    def _graphite_send(self, send_str):
        """
        Send data to graphite

        :param send_str: data string to send
        :type send_str: str
        """
        logger.debug('Opening socket connection to %s:%s', self.host, self.port)
        sock = socket.create_connection((self.host, self.port), 10)
        logger.debug('Sending data: "%s"', send_str)
        sock.sendall(send_str)
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
        newk = re.sub(r'[^A-Za-z0-9_-]', '_', metric_name)
        if newk != metric_name:
            logger.debug('Cleaned metric name from "%s" to "%s"',
                         metric_name, newk)
        return newk

    def send_data(self, data):
        """
        Send data to Graphite.

        :param data: list of data dicts
        :type data: list
        """
        send_str = ''
        for d in data:
            ts = time.mktime(d['datetime'].timetuple())
            for k in sorted(d.keys()):
                if k == 'datetime':
                    continue
                send_str += "%s %s %d\n" % (
                    'wattsup.%s' % self._clean_name(k),
                    d[k],
                    ts
                )
        self._graphite_send(send_str)

    def send_average(self, data):
        """
        Send average of data to Graphite.

        :param data: list of data dicts
        :type data: list
        """
        avgs = defaultdict(list)
        dt = None
        for record in data:
            if dt is None:
                dt = record['datetime']
            for key, val in record.items():
                if key == 'datetime':
                    continue
                avgs[key].append(val)
        result = {}
        for key, values in avgs.items():
            if key.endswith('min'):
                result[key] = min(values)
            elif key.endswith('max'):
                result[key] = max(values)
            else:
                # mean
                result[key] = sum(values) / float(len(values))
        result['datetime'] = dt
        self.send_data([result])


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Read and log data from WattsUp Pro')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-d', '--device', dest='device', action='store', type=str,
                   default='/dev/ttyUSB0',
                   help='device representing WattsUp (default: /dev/ttyUSB0)')
    p.add_argument('-n', '--num-samples', dest='num_samples', action='store',
                   type=int, default=3,
                   help='number of samples to read (default 3)')
    p.add_argument('-a', '--average', dest='average', action='store_true',
                   default=False, help='average together read samples (except '
                                       'min and max measurements) and '
                                       'log one reading, rather that logging'
                                       'individual readings')
    p.add_argument('-f', '--file', dest='fname', action='store', type=str,
                   default=None, help='path to file to append CSV logs to. If '
                                      'not specified, logs will print to'
                                      'STDOUT as CSV, with a header')
    p.add_argument('-i', '--interval', dest='interval', action='store',
                   type=int, default=2,
                   help='interval to have WattsUp log data at, in seconds '
                        '(default 1)')
    p.add_argument('-g', '--graphite', dest='graphite', action='store_true',
                   default=False,
                   help='Send metrics to Graphite; use -H|--graphite-host '
                   'and -P|--graphite-port to set host and port if other '
                   'than 127.0.0.1:2003')
    p.add_argument('-H', '--graphite-host', dest='graphite_host',
                   action='store', default='127.0.0.1',
                   help='graphite host (default: 127.0.0.1)')
    p.add_argument('-P', '--graphite-port', dest='graphite_port',
                   action='store', type=int, default=2003,
                   help='graphite plaintext port (default: 2003)')
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

    reader = WattsUpReader(device=args.device, interval=args.interval)
    data = reader.read(args.num_samples)
    logger.debug('Final data: %s', data)
    log = Logger(args.fname)
    if args.average:
        log.log_average(data)
    else:
        log.log_data(data)
    if args.graphite:
        g = GraphiteSender(args.graphite_host, args.graphite_port)
        if args.average:
            g.send_average(data)
        else:
            g.send_data(data)
