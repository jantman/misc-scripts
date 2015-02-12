#!/usr/bin/env python
"""
quick_cloudtrail - quick search of CloudTrail JSON log files.

This script searches for a given IAM user in CloudTrail logs.
It expects ./*.json to be the logs.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/quick_cloudtrail.py>

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2015-02-12 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import json
import os
import re
from pprint import pprint, pformat

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)


class QuickCloudtrail:
    """ might as well use a class. It'll make things easier later. """

    json_re = re.compile(r'^.+CloudTrail.+\.json$')
    logs = []

    def __init__(self, logger=None, verbose=0):
        """ init method, run at class creation """
        # setup a logger; allow an existing one to be passed in to use
        self.logger = logger
        if logger is None:
            self.logger = logging.getLogger(self.__class__.__name__)
        if verbose > 1:
            self.logger.setLevel(logging.DEBUG)
        elif verbose > 0:
            self.logger.setLevel(logging.INFO)
        files = [ f for f in os.listdir('./') if ( os.path.isfile(f) and self.json_re.match(f) ) ]
        self.logger.info("Found {c} CloudTrail log JSON files".format(c=len(files)))
        for f in files:
            self.logger.debug("Parsing {f}".format(f=f))
            with open(f, 'r') as fh:
                data = json.loads(fh.read())['Records']
                self.logger.debug("Found {c} records in {f}".format(
                    c=len(data),
                    f=f))
                self.logs.extend(data)
        self.logger.info("Parsed {c} records.".format(c=len(self.logs)))

    def search_user(self, user):
        """find all logs relating to the specified IAM user name substring"""
        res = []
        for i in self.logs:
            if 'userIdentity' not in i:
                continue
            if 'userName' not in i['userIdentity']:
                continue
            if user.lower() in i['userIdentity']['userName'].lower():
                res.append(i)
        self.logger.info("Found {c} matches.".format(c=len(res)))
        return res

    def search_request(self, req_id):
        """find all logs for the specified request ID"""
        res = []
        for i in self.logs:
            if 'requestID' not in i:
                continue
            if i['requestID'].lower() == req_id.lower():
                res.append(i)
        self.logger.info("Found {c} matches.".format(c=len(res)))
        return res

    def search_source_ip(self, src_ip):
        """find all logs for the specified source IP"""
        res = []
        for i in self.logs:
            if 'sourceIPAddress' not in i:
                continue
            if i['sourceIPAddress'].lower() == req_id.lower():
                res.append(i)
        self.logger.info("Found {c} matches.".format(c=len(res)))
        return res

    def format_log(self, rec):
        """format a log record as a human-readable string"""
        s = pformat(rec)
        return s

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    pwd = os.getcwd()
    p = argparse.ArgumentParser(description='Sample python script skeleton.')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-d', '--logdir', dest='logdir', action='store', type=str,
                   default=pwd,
                   help='directory containing JSON logs (default ./)')
    p.add_argument('-u', '--iam-user-name', dest='user', action='store', type=str,
                   help='search for IAM user with name containing this string')
    p.add_argument('-r', '--request-id', dest='request', action='store', type=str,
                   help='search for specific request ID')
    p.add_argument('-s', '--source-ip', dest='source_ip', action='store', type=str,
                   help='search for requests from specified source IP')
    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    qt = QuickCloudtrail(verbose=args.verbose)
    if args.user:
        res = qt.search_user(args.user)
    elif args.request:
        res = qt.search_request(args.request)
    elif args.source_ip:
        res = qt.search_source_ip(args.source_ip)
    else:
        sys.stderr.write("ERROR: please specify a search parameter (see --help)\n")
        raise SystemExit(1)

    if len(res) < 1:
        raise SystemExit(0)
    for r in res:
        print(qt.format_log(r))
