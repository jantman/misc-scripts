#!/usr/bin/env python
"""
Python script that parses Apache HTTPD access logs,
finds all unique URLs, and compares the current HTTP
response code to that of another server.

Written for when I moved my blog from self-hosted WordPress
to a static site, to verify that proper redirects and content
were migrated over.

REQUIREMENTS:
apachelog >= 1.0 (from pypi)

By Jason Antman <jason@jasonantman.com> <http://blog.jasonantman.com>
LICENSE: GPLv3

The latest version of this script will always be available at:
<https://github.com/jantman/misc-scripts/blob/master/apache_log_verify_site_move.py>

If you have any modifications/improvements, please send me a patch
or a pull request.

CHANGELOG:

2014-01-01
  - initial version

"""

import sys
import os
import optparse
import re

import apachelog # 1.0

LOG_FORMAT = "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-agent}i\" %D"

def get_log_filenames(logdir, filename_re=None, verbose=False):
    """
    Return a list of non-empty files within a given directory
    """
    ret = []
    for f in os.listdir(logdir):
        fpath = os.path.join(logdir, f)
        if os.path.isfile(fpath) and os.path.getsize(fpath) > 0:
            if filename_re is None:
                ret.append(fpath)
            else:
                if re.match(filename_re, f):
                    ret.append(fpath)
                elif verbose:
                    print("get_log_filenames(%s): filename does not match filename-re: %s" % (logdir, f))
        elif verbose:
            print("get_log_filenames(%s): ignoring %s" % (logdir, f))
    return ret

def get_log_urls(logfiles, logformat, verbose=False):
    """
    Parse apache log files, return a dict of distinct URLs (keys)
    and their most recent HTTP response code (values).

    :param logfiles: list of absolute paths to access logs to parse
    :type logfiles: list of strings
    :param verbose: whether or not to print verbose output
    :type verbose: boolean
    :returns: dict of request path => latest response code
    :rtype: dict, string keys to int values
    """
    temp = {}
    p = apachelog.parser(logformat)
    for fpath in logfiles:
        parsefail = 0
        lcount = 0
        if verbose:
            print("++ Parsing %s" % fpath)
        for line in open(fpath):
            lcount = lcount + 1
            try:
                data = p.parse(line)
                print data
            except Exception, e:
                if verbose:
                    print e
                parsefail = parsefail + 1
        sys.stderr.write("++ Failed parsing %d of %d lines from %s" % (parsefail, lcount, fpath))
        break
    # remove the dates
    ret = {}
    for f in temp:
        ret[f] = temp[f]['rcode']
    return ret

def parse_opts(argv):
    """
    Parse command-line options.

    :param argv: sys.argv or similar list
    :rtype: optparse.Values
    """
    parser = optparse.OptionParser()

    parser.add_option('-H', '--host', dest='host', action='store', type='string',
                      help='host to make requests to')

    parser.add_option('-I', '--ip', dest='ip', action='store', type='string',
                      help='IP address to make requests to. If -H|--host is also specified, it will be sent as a Host: header')

    parser.add_option('-d', '--logdir', dest='logdir', action='store', type='string',
                      help='path to directory containing apache access logs')

    parser.add_option('--filename-re', dest='filename_re', action='store', type='string',
                      help='regex to match access log filenames against, default=".+-access.+"', default=".+-access.+")

    parser.add_option('-f', '--logformat', dest='logformat', action='store', type='string', default=LOG_FORMAT,
                      help="apache access log format. default: %s" % LOG_FORMAT)

    parser.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False,
                      help='verbose output')

    parser.add_option('-s', '--sleep', dest='sleep', action='store', type='float', default=0.0,
                      help='time to sleep between requests (float; default 0)')

    parser.add_option('-l', '--limit', dest='limit', action='store', type='int', default=0,
                      help='limit to this (int) number of requests; 0 for no limit')

    parser.add_option('--strip-qs', dest='strip_qs', action='store_true', default=False,
                      help='strip query strings from URLs (? and everything after; default false)')

    parser.add_option('--strip-anchors', dest='strip_anchors', action='store_true', default=False,
                      help='strip anchors from URLs (default False)')

    options, args = parser.parse_args(argv)

    if not options.host and not options.ip:
        print("ERROR: you must specify -H|--host and/or -I|--ip")
        sys.exit(1)

    if not options.logdir:
        print("ERROR: you must specify -d|--logdir")
        sys.exit(1)

    if not os.path.exists(options.logdir):
        print("ERROR: logdir %s does not appear to exist." % options.logdir)
        sys.exit(1)

    return options

def main():
    """
    Main method
    """
    opts = parse_opts(sys.argv[1:])

    logfiles = get_log_filenames(opts.logdir, filename_re=opts.filename_re, verbose=opts.verbose)
    if opts.verbose:
        print("+ Found %d log files" % len(logfiles))

    urls = get_log_urls(logfiles, opts.logformat, verbose=opts.verbose)
    if opts.verbose:
        print("+ Found %d distinct matching URLs" % len(urls))
    #print urls

if __name__ == "__main__":
    main()
