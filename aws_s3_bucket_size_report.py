#!/usr/bin/env python
"""
https://github.com/jantman/misc-scripts/blob/master/aws_s3_bucket_size_report.py

Script to report on all S3 buckets in the current account, along with their
size and object count

Requires Python3 and boto3

CHANGELOG
---------

2021-09-21 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
from typing import List, Dict, Any
import boto3
from botocore.exceptions import ClientError
from collections import defaultdict
from datetime import datetime, timedelta
import logging
from humanize import naturalsize
import csv

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

for lname in ['boto3', 'botocore', 'urllib', 'urllib3']:
    # suppress library logging below WARNING level
    log = logging.getLogger(lname)
    log.setLevel(logging.WARNING)
    log.propagate = True


class S3Reporter:

    def run(self):
        result: List[List[Any]] = []
        regions: List[str] = boto3.session.Session().get_available_regions(
            'cloudwatch'
        )
        for rname in regions:
            try:
                result.extend(self._run_region(rname))
            except ClientError as ex:
                logger.exception(
                    'Exception running region %s: %s', rname, ex
                )
        writer = csv.writer(sys.stdout)
        writer.writerow([
            'bucket', 'region', 'number of objects', 'size', 'size_bytes'
        ])
        writer.writerows(sorted(result))

    def _run_region(self, region_name: str) -> List[List[Any]]:
        result: List[List[Any]] = []
        # dict of bucket name to types of storage metrics
        bucket_storage_types: Dict[str, List[str]] = defaultdict(list)
        logger.debug('Connecting to cloudwatch in %s', region_name)
        cw = boto3.client('cloudwatch', region_name=region_name)
        paginator = cw.get_paginator('list_metrics')
        for page in paginator.paginate(
            Namespace='AWS/S3', MetricName="BucketSizeBytes"
        ):
            for m in page['Metrics']:
                dims = {x['Name']: x['Value'] for x in m['Dimensions']}
                bucket_storage_types[dims['BucketName']].append(
                    dims['StorageType']
                )
        # ok, now we've got a dict of all bucket names and their storage types
        logger.info(
            'Found %d buckets in %s: %s', len(bucket_storage_types),
            region_name, list(sorted(bucket_storage_types.keys()))
        )
        for bname in sorted(bucket_storage_types.keys()):
            result.append(self._query_for_bucket(
                cw, bname, region_name, bucket_storage_types[bname]
            ))
        return result

    def _query_for_bucket(
        self, cw, bucket_name: str, region: str, storage_types: List[Any]
    ) -> List[Any]:
        queries = [
            {
                'Id': 'xNumberOfObjects',  # Id must begin with a lower-case
                'MetricStat': {
                    'Metric': {
                        'Namespace': 'AWS/S3',
                        'MetricName': 'NumberOfObjects',
                        'Dimensions': [
                            {
                                'Name': 'StorageType',
                                'Value': 'AllStorageTypes'
                            },
                            {
                                'Name': 'BucketName',
                                'Value': bucket_name
                            }
                        ]
                    },
                    'Period': 86400,
                    'Stat': 'Average'
                },
                'ReturnData': True
            },
        ]
        st: str
        for st in storage_types:
            queries.append({
                'Id': f'x{st}',  # Id must begin with a lower-case letter
                'MetricStat': {
                    'Metric': {
                        'Namespace': 'AWS/S3',
                        'MetricName': 'BucketSizeBytes',
                        'Dimensions': [
                            {
                                'Name': 'StorageType',
                                'Value': st
                            },
                            {
                                'Name': 'BucketName',
                                'Value': bucket_name
                            }
                        ]
                    },
                    'Period': 86400,
                    'Stat': 'Average'
                }
            })
        logger.debug('Run CW metric data queries: %s', queries)
        resp = cw.get_metric_data(
            MetricDataQueries=queries,
            StartTime=datetime.utcnow() - timedelta(days=7),
            EndTime=datetime.utcnow(),
            ScanBy='TimestampDescending'
        )
        num_objects: int = 0
        size_bytes: int = 0
        for d in resp['MetricDataResults']:
            if not d['Values']:
                d['Values'] = [0]
            if d['Id'] == 'xNumberOfObjects':
                num_objects = d['Values'][0]
            else:
                size_bytes += d['Values'][0]
        return [
            bucket_name, region,
            num_objects, naturalsize(size_bytes), size_bytes
        ]


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='S3 bucket size lister')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='verbose output')
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
    if args.verbose:
        set_log_debug()
    else:
        set_log_info()

    S3Reporter().run()
