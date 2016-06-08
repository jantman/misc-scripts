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
2016-03-21 Jason Antman <jason@jasonantman.com>:
  - add option to output results as a JSON list

2015-11-10 Jason Antman <jason@jasonantman.com>:
  - add search type for all errors
  - add search types for errorCode and errorMessage

2015-10-08 Jason Antman <jason@jasonantman.com>:
  - clarify some things in help output

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

    def __init__(self, logdir, logger=None, verbose=0):
        """ init method, run at class creation """
        # setup a logger; allow an existing one to be passed in to use
        self.logger = logger
        if logger is None:
            self.logger = logging.getLogger(self.__class__.__name__)
        if verbose > 1:
            self.logger.setLevel(logging.DEBUG)
        elif verbose > 0:
            self.logger.setLevel(logging.INFO)
        self.logdir = logdir
        files = [ f for f in os.listdir(logdir) if ( os.path.isfile(os.path.join(logdir, f)) and self.json_re.match(f) ) ]
        self.logger.info("Found {c} CloudTrail log JSON files in {l}".format(c=len(files), l=logdir))
        for f in files:
            self.logger.debug("Parsing {f}".format(f=f))
            with open(os.path.join(logdir, f), 'r') as fh:
                data = json.loads(fh.read())['Records']
                self.logger.debug("Found {c} records in {f}".format(
                    c=len(data),
                    f=f))
                self.logs.extend(data)
        self.logger.info("Parsed {c} records.".format(c=len(self.logs)))

    def search_user(self, users):
        """find all logs relating to the specified IAM user name substring(s)"""
        res = []
        for i in self.logs:
            if 'userIdentity' not in i:
                continue
            if 'userName' not in i['userIdentity']:
                continue
            for u in users:
                if u.lower() in i['userIdentity']['userName'].lower():
                    res.append(i)
                    break
        return res

    def search_accessKeyId(self, users):
        """find all logs relating to the specified Access Key ID"""
        res = []
        for i in self.logs:
            if 'userIdentity' not in i:
                continue
            if 'accessKeyId' not in i['userIdentity']:
                continue
            for u in users:
                if u.lower().strip() == i['userIdentity'
                ]['accessKeyId'].lower().strip():
                    res.append(i)
                    break
        return res

    def search_request(self, req_ids):
        """find all logs for the specified request ID(s)"""
        res = []
        for i in self.logs:
            if 'requestID' not in i:
                continue
            for rid in req_ids:
                if i['requestID'].lower() == rid.lower():
                    res.append(i)
                    break
        return res

    def search_source_ip(self, src_ips):
        """find all logs for the specified source IP(s)"""
        res = []
        for i in self.logs:
            if 'sourceIPAddress' not in i:
                continue
            for sip in src_ips:
                if i['sourceIPAddress'].lower() == sip.lower():
                    res.append(i)
                    break
        return res

    def search_errors(self, args):
        """find all logs with errorCode or errorMessage; ignore query"""
        res = []
        for i in self.logs:
            if 'errorCode' in i or 'errorMessage' in i:
                res.append(i)
        return res

    def _search_element_substr(self, key, args):
        """meta-func to search for any records with substrings in a key"""
        res = []
        for i in self.logs:
            if key not in i:
                continue
            for a in args:
                if a in i[key]:
                    res.append(i)
                    break
        return res

    def search_errorCode(self, args):
        """find all logs with an errorCode containing the specified string"""
        return self._search_element_substr('errorCode', args)

    def search_errorMessage(self, args):
        """find all logs with an errorMessage containing the specified string"""
        return self._search_element_substr('errorMessage', args)

    def search_eventSource(self, args):
        """find all logs with an eventSource containing the specified string"""
        return self._search_element_substr('eventSource', args)

    def search_eventName(self, args):
        """find all logs with an eventName containing the specified string"""
        return self._search_element_substr('eventName', args)

    def search_string(self, args):
        """find all logs with the specified string ANYWHERE in them"""
        res = []
        for i in self.logs:
            _repr = str(i)
            for a in args:
                if a in _repr:
                    res.append(i)
                    break
        return res

    def format_log(self, rec):
        """format a log record as a human-readable string"""
        s = pformat(rec)
        return s

    def search(self, search_type, query, error_only=False):
        """wrapper around search functions"""
        func_name = "search_{s}".format(s=search_type)
        fn = getattr(self, func_name)
        res = fn(query)
        self.logger.debug("Search function {f} found {c} matches.".format(
            c=len(res),
            f=func_name))
        if error_only:
            tmp = []
            for r in res:
                if 'errorCode' in r or 'errorMessage' in r:
                    tmp.append(r)
        else:
            tmp = res
        if len(tmp) == 1:
            self.logger.info("Found 1 match.")
        else:
            self.logger.info("Found {c} matches.".format(c=len(tmp)))
        return tmp

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    pwd = os.getcwd()
    epil = "Search Types:\n"
    for i in dir(QuickCloudtrail):
        if i.startswith('search_'):
            epil += "  {i} - {d}\n".format(i=i[7:],
                                           d=getattr(QuickCloudtrail, i).__doc__)
    p = argparse.ArgumentParser(description='Simple AWS CloudTrail JSON log searcher (searches *.json).',
                                epilog=epil,
                                formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-d', '--logdir', dest='logdir', action='store', type=str,
                   default=pwd,
                   help='directory containing .json logs (default ./)')
    p.add_argument('-e', '--errors-only', dest='error_only', action='store_true',
                   default=False,
                   help='return only records with an errorCode or errorMessage')
    p.add_argument('-j', '--json', dest='json', action='store_true',
                   default=False, help='instead of pretty-printing output, print'
                   ' output as JSON')
    p.add_argument('search_type', metavar='SEARCH_TYPE', type=str,
                   help='type of search to perform')
    p.add_argument('query', metavar='QUERY', type=str, nargs='+',
                   help='Search query (can be specified multiple times). Any\n'
                   'records with an appropriate value containing this string\n'
                   '(case-insensitive) will be matched.')

    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    search_func_name = "search_{s}".format(s=args.search_type)
    if search_func_name not in dir(QuickCloudtrail):
        sys.stderr.write("ERROR: {s} is not a valid search type.\n".format(
            s=args.search_type))
        raise SystemExit(1)
    qt = QuickCloudtrail(args.logdir, verbose=args.verbose)
    res = qt.search(args.search_type, args.query, error_only=args.error_only)
    if len(res) < 1:
        sys.stderr.write("0 matches found.")
        raise SystemExit(0)
    if args.json:
        print(json.dumps(res))
        raise SystemExit(0)
    for r in res:
        print(qt.format_log(r))
