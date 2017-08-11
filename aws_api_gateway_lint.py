#!/usr/bin/env python
"""
aws_api_gateway_lint.py
=======================

Script using boto3 to attempt to identify unused or idle API Gateways.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/aws_api_gateway_lint.py>

Requirements
------------

* boto3
* texttable

``pip install boto3 texttable``

License
-------

Copyright 2017 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG
---------

2017-08-11 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import boto3
from datetime import datetime, tzinfo, timedelta
from texttable import Texttable
import locale
import json
from tzlocal import get_localzone

__author__ = 'jason@jasonantman.com'
__src_url__ = 'https://github.com/jantman/misc-scripts/blob/master' \
              '/aws_api_gateway_lint.py'

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

# suppress boto3 internal logging below WARNING level
boto3_log = logging.getLogger("boto3")
boto3_log.setLevel(logging.WARNING)
boto3_log.propagate = True

# suppress botocore internal logging below WARNING level
botocore_log = logging.getLogger("botocore")
botocore_log.setLevel(logging.WARNING)
botocore_log.propagate = True

ZERO = timedelta(0)

class UTC(tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO

utc = UTC()
locale.setlocale(locale.LC_ALL, 'en_US.UTF8')
CW_NUM_DAYS = 14
NOW = datetime.now(tz=get_localzone())


class APIGatewayLinter(object):
    """Identify potentially unused API Gateways"""

    def __init__(self):
        logger.debug('Connecting to AWS APIs')
        self._api = boto3.client('apigateway')
        self._cw = boto3.resource('cloudwatch')
        logger.debug('Connected.')

    def run(self, format='console'):
        apis = self._get_apis()
        logger.info('Found %d ReST APIs', len(apis))
        logger.debug('APIs: %s', apis)
        for api in apis.keys():
            apis[api]['cw_count'] = self._get_cloudwatch(api)
        if format == 'console':
            self._output_console(apis)
        elif format == 'json':
            self._output_json(apis)
        elif format == 'html':
            self._output_html(apis)
        else:
            raise RuntimeError('Unknown output format: %s', format)

    def _get_apis(self):
        apis = {}
        logger.debug('Querying for REST APIs')
        paginator = self._api.get_paginator('get_rest_apis')
        for r in paginator.paginate():
            for api in r['items']:
                apis[api['name']] = api
        logger.debug('Got %d REST APIs', len(apis))
        for api in apis.keys():
            logger.debug('Querying deployments for API %s', apis[api]['id'])
            paginator = self._api.get_paginator('get_deployments')
            last_depl = datetime(1970, 1, 1, 0, 0, 0, tzinfo=utc)
            last_depl_id = None
            for r in paginator.paginate(restApiId=apis[api]['id']):
                for depl in r['items']:
                    if depl['createdDate'] > last_depl:
                        last_depl = depl['createdDate']
                        last_depl_id = depl['id']
            logger.debug('REST API %s last deployment: %s at %s',
                         apis[api]['id'], last_depl_id, last_depl)
            if last_depl_id is None:
                apis[api]['last_deployment_time'] = None
            else:
                apis[api]['last_deployment_time'] = last_depl
        return apis

    def _get_cloudwatch(self, api_name):
        logger.debug(
            'Querying CloudWatch Count metric for API name "%s"', api_name
        )
        metric = self._cw.Metric('AWS/ApiGateway', 'Count')
        try:
            stats = metric.get_statistics(
                Dimensions=[
                    {
                        'Name': 'ApiName',
                        'Value': api_name
                    }
                ],
                StartTime=(datetime.now() - timedelta(days=CW_NUM_DAYS)),
                EndTime=datetime.now(),
                Period=86400,  # 1 day
                Statistics=['Sum']
            )
            logger.debug('Datapoints: %s', stats['Datapoints'])
        except Exception as ex:
            logger.warning('Error getting Count statistics for API %s',
                           api_name, exc_info=True)
            return 0
        res = sum(
            [x['Sum'] for x in stats['Datapoints']]
        )
        logger.debug('API %s sum of requests in last %d days: %s',
                     api_name, CW_NUM_DAYS, res)
        return res

    def _output_console(self, apis):
        print('API Gateway Usage Summary')
        t = Texttable()
        rows = [[
            'Name',
            'ID',
            'Created',
            'Last Deployment',
            'Calls Last %d Days' % CW_NUM_DAYS,
            'Description'
        ]]
        for k in sorted(apis.keys(), key=lambda s: s.lower()):
            rows.append([
                k,
                apis[k]['id'],
                apis[k]['createdDate'],
                apis[k].get('last_deployment_time', None),
                locale.format('%d', apis[k]['cw_count'], grouping=True),
                apis[k].get('description', '')
            ])
        t.add_rows(rows)
        print(t.draw() + "\n")

    def _output_json(self, apis):
        for k in apis.keys():
            apis[k]['createdDate'] = apis[k][
                'createdDate'].strftime('%Y-%m-%d %H:%M:%S %Z')
            if apis[k].get('last_deployment_time', None) is None:
                continue
            apis[k]['last_deployment_time'] = apis[k][
                'last_deployment_time'].strftime('%Y-%m-%d %H:%M:%S %Z')
        print(json.dumps(apis))

    def _output_html(self, apis):
        s = '<html><head><title>API Gateway Usage</title></head>' + "\n"
        s += '<body><h1>API Gateway Usage</h1>' + "\n"
        s += '<table border="1">' + "\n"
        s += '<tr>'
        s += '<th>Name</th>'
        s += '<th>ID</th>'
        s += '<th>Age</th>'
        s += '<th>Last Deployment Age</th>'
        s += '<th>Calls Last %d Days</th>' % CW_NUM_DAYS
        s += '<th>Description</th>'
        s += '</tr>' + "\n"
        for k in sorted(apis.keys(), key=lambda s: s.lower()):
            s += '<tr>'
            s += '<td>%s</td>' % k
            s += '<td>%s</td>' % apis[k]['id']
            s += '<td>%s</td>' % humantime(apis[k]['createdDate'])
            if apis[k].get('last_deployment_time', None) is None:
                s += '<td>unknown</td>'
            else:
                s += '<td>%s</td>' % humantime(apis[k]['last_deployment_time'])
            s += '<td>%s</td>' % locale.format(
                '%d', apis[k]['cw_count'], grouping=True
            )
            s += '<td>%s</td>' % apis[k].get('description', '&nbsp;')
            s += '</tr>' + "\n"
        s += '</table></body></html>' + "\n"
        print(s)


def humantime(dt):
    diff = NOW - dt
    secs = diff.total_seconds()
    if secs > 31536000:
        return '%s years' % round(secs / 31536000, 1)
    if secs > 2592000:
        return '%s months' % round(secs / 2592000, 1)
    if secs > 86400:
        return '%s days' % round(secs / 86400, 1)
    return '< 1 day'


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Identify potentially unused API Gateways'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-f', '--format', dest='format', action='store',
                   default='console', choices=['console', 'json', 'html'],
                   help='output format - "console", "html" or "json"')
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

    APIGatewayLinter().run(args.format)
