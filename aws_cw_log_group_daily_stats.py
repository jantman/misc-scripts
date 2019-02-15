#!/usr/bin/env python
"""
aws_cw_log_group_daily_stats.py
===============================

Python script using boto3 to query CloudWatch Metrics for the IncomingBytes
and IncomingLogEvents metrics for one or more LogGroups, across all regions.
Retrieves metrics at the 24-hour resolution for N (default 7) days.

License
-------

Copyright 2019 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG
---------

2019-02-15 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import boto3
import json
import io
import csv
from datetime import datetime, timedelta

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

for lname in ['boto3', 'botocore', 'urllib3']:
    _l = logging.getLogger(lname)
    _l.setLevel(logging.WARNING)
    _l.propagate = True


class CwLogGroupChecker(object):

    def __init__(self, num_days=7):
        self._num_days = num_days
        self._end_dt = datetime.now().replace(hour=0, minute=0, second=0)
        self._start_dt = self._end_dt - timedelta(days=num_days)
        logger.info(
            'Querying data for the last %d days (%s to %s)',
            self._num_days, self._start_dt, self._end_dt
        )

    def run(self, log_groups, fmt='csv', regions=[]):
        if len(regions) == 0:
            regions = self.all_region_names
            logger.debug('No regions specified; using all regions: %s', regions)
        logger.info(
            'Checking LogGroup metrics for %d group(s) across %d region(s) '
            '(log_groups=%s regions=%s)',
            len(log_groups), len(regions), log_groups, regions
        )
        res = {}
        for rname in regions:
            res[rname] = self._do_region(log_groups, rname)
        if fmt == 'json':
            print(json.dumps(res, sort_keys=True, indent=4))
            return
        # else CSV
        self._output_csv(res)

    def _output_csv(self, data):
        all_dates = set()
        for rname, rdict in data.items():
            for groupname, groupdict in rdict.items():
                for k in groupdict.keys():
                    all_dates.add(k)
        all_dates = sorted(list(all_dates))
        headers = ['region', 'log_group']
        for d in all_dates:
            headers.append('%s_IncomingBytes' % d)
            headers.append('%s_IncomingLogEvents' % d)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, restval=0)
        writer.writeheader()
        for rname, rdict in data.items():
            for groupname, groupdict in rdict.items():
                tmp = {
                    'region': rname,
                    'log_group': groupname
                }
                for datestr, datedict in groupdict.items():
                    for k, v in datedict.items():
                        tmp['%s_%s' % (datestr, k)] = v
                writer.writerow(tmp)
        print(output.getvalue())

    def _do_region(self, log_groups, rname):
        res = {}
        logger.info('Checking region: %s', rname)
        client = boto3.client('cloudwatch', region_name=rname)
        for gname in log_groups:
            res[gname] = self._do_group(gname, client)
        logger.debug('Finished region %s: %s', rname, res)
        return res

    def _do_group(self, log_group_name, cw_client):
        res = {}
        logger.debug('Checking log group: %s', log_group_name)
        for mname in ['IncomingBytes', 'IncomingLogEvents']:
            logger.debug('Query %s for LogGroupName=%s', mname, log_group_name)
            data = cw_client.get_metric_statistics(
                Namespace='AWS/Logs',
                MetricName=mname,
                Dimensions=[
                    {
                        'Name': 'LogGroupName',
                        'Value': log_group_name
                    }
                ],
                StartTime=self._start_dt,
                EndTime=self._end_dt,
                Period=86400,
                Statistics=['Sum']
            )
            for p in data['Datapoints']:
                ds = p['Timestamp'].strftime('%Y-%m-%d')
                if ds not in res:
                    res[ds] = {}
                res[ds][mname] = p['Sum']
        logger.debug('Done with log group %s', log_group_name)
        return res

    @property
    def all_region_names(self):
        return sorted([
            x['RegionName'] for x in boto3.client(
                'ec2', region_name='us-east-1'
            ).describe_regions()['Regions']
        ])


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='CW Log Group Statistics')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-r', '--region-name', dest='region', action='append',
                   default=[],
                   help='Region name(s) to check; can be specified multiple '
                        'times. If not specified, all regions will be checked')
    p.add_argument('-n', '--num-days', dest='num_days', action='store',
                   type=int, default=7,
                   help='Number of days of metrics to check; default 7')
    p.add_argument('-f', '--format', action='store', type=str, default='csv',
                   choices=['csv', 'json'],
                   help='output format - one of "csv" or "json"; default csv')
    p.add_argument('LogGroupName', type=str, nargs='+',
                   help='Name of log group(s) to check metrics for')
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

    CwLogGroupChecker(args.num_days).run(
        args.LogGroupName, fmt=args.format, regions=args.region
    )
