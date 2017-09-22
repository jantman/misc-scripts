#!/usr/bin/env python
"""
Script using boto3 to show all Limit Increase support tickets for a
specified service.

Requirements
------------

``pip install boto3 python-dateutil pytz``

CHANGELOG
---------

2017-09-22 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import boto3
from datetime import datetime
from pytz import utc
from dateutil.parser import parse
import re

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger(__name__)

# suppress boto3 internal logging below WARNING level
boto3_log = logging.getLogger("boto3")
boto3_log.setLevel(logging.WARNING)
boto3_log.propagate = True

# suppress botocore internal logging below WARNING level
botocore_log = logging.getLogger("botocore")
botocore_log.setLevel(logging.WARNING)
botocore_log.propagate = True

SERVICE_CODE = 'service-limit-increase'

# dict that maps the AwsLimitChecker service names to the category "name"
# returned by the Support API's DescribeServices action
SERVICE_NAMES = {
    'IAM': 'IAM Groups and Users',
    'S3': 'Simple Storage Service (S3)'
}

REQUEST_SEP_RE = re.compile(r'^-+$')
REQUEST_HEADER_RE = re.compile(r'^Limit increase request (\d+)$')

class LimitIncreaseFinder(object):
    """Find existing support tickets for service limit increases"""

    def __init__(self, dry_run=False):
        """ init method, run at class creation """
        self.support = boto3.client('support', region_name='us-east-1')
        self.category_codes = self.get_category_codes()
        logger.debug("category_codes: %s", self.category_codes)

    def list_categories(self):
        """ just list the categories """
        for catname, catcode in sorted(self.category_codes.items()):
            print('%s (%s)' % (catname, catcode))

    def get_category_codes(self):
        """get the Support case category codes for limit increases; return a
        dict of category code to name"""
        codes = self.support.describe_services(
            serviceCodeList=[SERVICE_CODE], language='en'
        )
        res = {}
        for d in codes['services'][0]['categories']:
            res[d['code']] = d['name']
        return res

    def first_communication_in_case(self, case):
        """parse communications in a case and return the first one"""
        if len(case['recentCommunications']['communications']) == 0:
            raise RuntimeError("ERROR: case %s (%s) has no communications" %
                               (case['displayId'], case['caseId']))
        elif len(case['recentCommunications']['communications']) == 1:
            return case['recentCommunications']['communications'][0]
        oldest_dt = datetime.utcnow().replace(tzinfo=utc)
        oldest_comm = None
        for comm in case['recentCommunications']['communications']:
            dt = parse(comm['timeCreated'])
            if dt < oldest_dt:
                oldest_dt = dt
                oldest_comm = comm
        return oldest_comm

    def limit_requests_in_case(self, case):
        """parse a case and return the limit requests in it"""
        comm = self.first_communication_in_case(case)
        limits = self.parse_limits_from_communication(comm['body'])
        return limits

    def parse_limits_from_communication(self, body):
        """given the body of a communication, parse it and return a list of
        dicts describing the limit increase requests in it"""
        logger.debug("Parsing communication body:\n%s", body)
        lines = body.split("\n")
        requests = []
        tmp = {}
        in_request = False
        for line in lines:
            line = line.strip()
            if line == '':
                continue
            if REQUEST_SEP_RE.match(line):
                # end of request
                logger.debug("End of request: %s", tmp)
                if 'New limit value' not in tmp or 'Service' not in tmp or \
                    'Limit name' not in tmp:
                    logger.error("Error: fields missing from record: %s", body)
                else:
                    requests.append(tmp)
                tmp = {}
                in_request = False
                continue
            if not in_request:
                m = REQUEST_HEADER_RE.match(line)
                if m is None:
                    logger.debug("Not in request but no match for header: %s",
                                 line)
                    continue
                in_request = True
                logger.debug("Beginning to parse limit request %s", m.group(1))
                tmp['request_num'] = int(m.group(1))
            else:
                # in request
                parts = line.split(':', 1)
                if parts[0] == 'New limit value':
                    tmp[parts[0]] = int(parts[1].strip())
                else:
                    tmp[parts[0]] = parts[1].strip()
        return requests

    def show_cases_for_service(self, svc_name, include_resolved=True):
        """
        Print out all cases for the given service name and then return.

        :param svc_name: the service name to search for. This is a key in the
          ``self.category_codes`` dictionary, as returned by
          :py:meth:`~.get_category_codes`
        :type svc_name: str
        """
        if svc_name not in self.category_codes.keys():
            raise RuntimeError(
                "ERROR: '%s' is not a valid support case category code; please "
                "run with '-l' option to list valid category codes." % svc_name
            )
        cases = self.get_cases(
            includeResolvedCases=include_resolved, maxResults=100,
            language='en', includeCommunications=True
        )
        for case in cases:
            if case['serviceCode'] != SERVICE_CODE:
                logger.debug('Skipping case %s (%s) with serviceCode %s',
                             case['displayId'], case['caseId'],
                             case['serviceCode'])
                continue
            if case['categoryCode'] != svc_name:
                logger.debug('Skipping case %s (%s) with categoryCode %s',
                             case['displayId'], case['caseId'],
                             case['categoryCode'])
                continue
            # right service and category; need to parse it and check limits
            try:
                lim_requests = self.limit_requests_in_case(case)
            except RuntimeError:
                lim_requests = []
            logger.debug("Parsing found %d limit request(s) in case %s",
                         len(lim_requests), case['displayId'])
            if len(lim_requests) < 1:
                continue
            self.show_case(case, lim_requests)
        return None

    def show_case(self, case, lim_requests):
        """
        Display (print) a support case
        :param case:
        :param lim_requests:
        :return:
        """
        # case metadata
        print('#' * 60)
        print('Case %s (ID: %s) Severity: %s' % (
            case['displayId'], case['caseId'], case['severityCode']
        ))
        print('Status: %s' % case['status'])
        print('Subject: %s' % case['subject'])
        print('\tCategory: %s  Service: %s' % (case['categoryCode'], case['serviceCode']))
        print('\tSubmitted By %s at %s (cc: %s)' % (
            case['submittedBy'], case['timeCreated'], case['ccEmailAddresses']
        ))
        print("\n")

        # communications
        print("### Communications:\n")
        comms = case['recentCommunications']['communications']
        for comm in sorted(comms, key=lambda k: k['timeCreated']):
            print("=> %s from %s" % (comm['timeCreated'], comm['submittedBy']))
            print(comm['body'] + "\n")
        print("\n")

        # limit requests
        print('### Limit Requests:')
        for lr in lim_requests:
            print('%d) Service: "%s" Limit: "%s" Region: "%s" New Value: %d' % (
                lr['request_num'], lr['Service'], lr['Limit name'],
                lr['Region'], lr['New limit value']
            ))


    def get_cases(self, **kwargs):
        """
        Wrapper around boto3 support.describe_cases to handle pagination. Calls
        `boto3.Support.Client.describe_cases <http://boto3.readthedocs.io/en/
        latest/reference/services/support.html#Support.Client.describe_cases>`_
        with the specified ``kwargs``, and combines results if ``nextToken`` is
        present.

        :param kwargs: kwargs to call ``describe_cases`` with
        :type kwargs: dict
        :return: list of support cases
        :rtype: list
        """
        all_cases = []
        logger.debug('Beginning cases query')
        while True:
            cases = self.support.describe_cases(**kwargs)
            all_cases += cases['cases']
            logger.debug('Got %d cases' % len(cases['cases']))
            if 'nextToken' not in cases:
                logger.debug('Reached end of paginated results')
                break
            logger.debug('Paginating with nextToken=%s', cases['nextToken'])
            kwargs['nextToken'] = cases['nextToken']
        logger.debug('Found a total of %d cases', len(all_cases))
        return all_cases

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(
        description='show AWS limit increase cases for a specific service'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=1,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-l', '--list-categories', dest='list_categories',
                   action='store_true', default=False,
                   help='List limit increase request categories and exit')
    p.add_argument(
        'CATEGORY', action='store', type=str, default=None, nargs='?',
        help='Category (service) name to list cases for'
    )
    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    script = LimitIncreaseFinder()
    if args.list_categories or args.CATEGORY is None:
        script.list_categories()
        raise SystemExit(0)
    script.show_cases_for_service(args.CATEGORY)
