#!/usr/bin/env python
"""
Python script that parses Apache HTTPD access logs,
finds all unique URLs, and compares the current HTTP
response code to that of another server.

Written for when I moved my blog from self-hosted WordPress
to a static site, to verify that proper redirects and content
were migrated over.

REQUIREMENTS:
apache_log_parser >= 1.3.0 (from pypi)
anyjson >= 0.3.3
requests

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
import time
from urlparse import urlparse

import requests
import anyjson
import apache_log_parser

LOG_FORMAT = "%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-agent}i\" %D"

def get_log_filenames(logdir, filename_re=None, verbose=False):
    """
    Return a list of non-empty files within a given directory,
    optionally with names matching filename_re
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

def url_strip(url, strip_qs=False, strip_anchors=False):
    """
    Return url (string), with query string and/or anchors
    stripped off of it.

    :param url: the URL
    :type url: string
    :param strip_qs: True to strip query string
    :type strip_qs: boolean
    :param strip_anchors: True to strip anchors
    :type string_anchors: boolean
    :return: url with query string and/or anchors stripped
    :rtype: string
    """
    parsed = urlparse(url)
    ret = parsed.path
    if not strip_qs:
        ret = ret + "?" + parsed.query
    if not strip_anchors:
        ret = ret + "#" + parsed.fragment
    return ret

def get_log_urls(logfiles, logformat, strip_qs=False, strip_anchors=False, verbose=False):
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
    p = apache_log_parser.make_parser(logformat)
    for fpath in logfiles:
        parsefail = 0
        lcount = 0
        if verbose:
            print("++ Parsing %s" % fpath)
        for line in open(fpath):
            line = str(line).strip()
            lcount = lcount + 1
            try:
                data = p(line)
                if data['request_method'] != 'GET':
                    continue
                data['request_url'] = url_strip(data['request_url'], strip_qs, strip_anchors)
                if data['request_url'] not in temp:
                    temp[data['request_url']] = {'datetime': data['time_recieved_datetimeobj'],
                                                 'status': int(data['status'])}
                else:
                    if temp[data['request_url']]['datetime'] < data['time_recieved_datetimeobj']:
                        temp[data['request_url']] = {'datetime': data['time_recieved_datetimeobj'],
                                                     'status': int(data['status'])}
            except Exception, e:
                if verbose:
                    print("Parse Exception: %s for line '%s'" % (str(e), line))
                parsefail = parsefail + 1
        sys.stderr.write("++ Failed parsing %d of %d lines from %s\n" % (parsefail, lcount, fpath))
    # remove the dates
    ret = {}
    for f in temp:
        ret[f] = temp[f]['status']
    return ret

def confirm_urls(urls, host=None, ip=None, port=80, sleep=0.0, limit=0, verbose=False):
    """
    Confirm that the given URLs have the specified HTTP response code.

    :param urls: dict of paths to check, path => response code
    :type urls: dict of string => int
    :param host: hostname to request from. If specified along with ip, will be sent as a Host: header
    :type host: string
    :param ip: IP address to request from.
    :type ip: string
    :param port: port to use for requests (default 80)
    :type port: integer
    :param sleep: how long to sleep between requests, default 0
    :type sleep: float
    :param limit: stop after this number of requests, default 0 (no limit)
    :type limit: int
    :param verbose: whether or not to print verbose output
    :type verbose: boolean
    :returns: dict of request path => dict {'old_status': int, 'new_staus': int, 'same': boolean}
    :rtype: dict, string keys to dict values
    """
    headers = None
    if host is None and ip is not None:
        url_base = "http://%s" % ip
    elif ip is None and host is not None:
        url_base = "http://%s" % host
    else:
        url_base = "http://%s" % ip
        headers['Host'] = host
    if port != 80 and port is not None:
        url_base = "%s:%d" % (url_base, port)

    rdict = {}
    count = 0
    if limit == 0:
        limit = len(urls) + 1
    for path in urls:
        count = count + 1
        if count > limit:
            break
        url = url_base + path
        if verbose:
            print("++ GETing %s" % url)
        r = requests.get(url, headers=headers, allow_redirects=False)
        rdict[path] = {'old_status': urls[path], 'new_status': r.status_code, 'same': True}
        if urls[path] != r.status_code:
            rdict[path]['same'] = False
        if sleep > 0:
            time.sleep(sleep)
    return rdict

def parse_opts(argv):
    """
    Parse command-line options.

    :param argv: sys.argv or similar list
    :rtype: optparse.Values
    """
    parser = optparse.OptionParser()

    parser.add_option('-H', '--host', dest='host', action='store', type='string', default=None,
                      help='host to make requests to')

    parser.add_option('-I', '--ip', dest='ip', action='store', type='string', default=None,
                      help='IP address to make requests to. If -H|--host is also specified, it will be sent as a Host: header')

    parser.add_option('-p', '--port', dest='port', action='store', type='integer', default=80,
                      help='port to make requests to (default 80)')

    parser.add_option('-d', '--logdir', dest='logdir', action='store', type='string',
                      help='path to directory containing apache access logs')

    parser.add_option('--filename-re', dest='filename_re', action='store', type='string',
                      help='regex to match access log filenames against, default=".+-access.+"', default=".+-access.+")

    parser.add_option('-f', '--logformat', dest='logformat', action='store', type='string', default=LOG_FORMAT,
                      help="apache access log format. default: %s" % LOG_FORMAT)

    parser.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False,
                      help='verbose output')

    parser.add_option('--url-savefile', dest='url_savefile', action='store', type='string',
                      help='parsed URL savefile. If specified, will write JSON of all parsed URLs to this file. If present, will read access log URLS from this file INSTEAD OF parsing them.')

    parser.add_option('-s', '--sleep', dest='sleep', action='store', type='float', default=0.0,
                      help='time to sleep between requests (float; default 0)')

    parser.add_option('-l', '--limit', dest='limit', action='store', type='int', default=0,
                      help='limit to this (int) number of requests; 0 for no limit')

    # the following are not implemented yet
    parser.add_option('--strip-qs', dest='strip_qs', action='store_true', default=False,
                      help='strip query strings from URLs (? and everything after; default false)')

    parser.add_option('--strip-anchors', dest='strip_anchors', action='store_true', default=False,
                      help='strip anchors from URLs (default False)')


    options, args = parser.parse_args(argv)

    if options.host is None and options.ip is None:
        print("ERROR: you must specify -H|--host and/or -I|--ip")
        sys.exit(1)

    if not options.logdir and not (options.url_savefile and os.path.exists(options.url_savefile)):
        print("ERROR: you must specify -d|--logdir or --url-savefile pointing to a valid savefile")
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

    if opts.url_savefile and os.path.exists(opts.url_savefile):
        # read the savefile instead of parsing URLs
        try:
            with open(opts.url_savefile, 'r') as fh:
                urls = anyjson.deserialize(fh.read())
        except ValueError:
            sys.stderr.write("ERROR: could not deserialize URL JSON savefile %s\n" % opts.url_savefile)
            return False
    else:
        logfiles = get_log_filenames(opts.logdir, filename_re=opts.filename_re, verbose=opts.verbose)
        if opts.verbose:
            print("+ Found %d log files" % len(logfiles))

        urls = get_log_urls(logfiles, opts.logformat, strip_qs=opts.strip_qs, strip_anchors=opts.strip_anchors, verbose=opts.verbose)
        if opts.verbose:
            print("+ Found %d distinct matching URLs" % len(urls))
        if opts.url_savefile:
            with open(opts.url_savefile, "w") as fh:
                fh.write(anyjson.serialize(urls))
            if opts.verbose:
                print("+ Wrote URLs as JSON to %s" % opts.url_savefile)

    if opts.verbose:
        print("+ Confirming %d paths..." % len(urls))

    # ok, now do stuff with them
    res = confirm_urls(urls, host=opts.host, ip=opts.ip, port=opts.port, sleep=opts.sleep, limit=opts.limit, verbose=opts.verbose)

    changed = 0
    total = len(res)
    for r in res:
        if res[r]['same'] is False:
            print("%d => %d %s" % (res[r]['old_status'], res[r]['new_status'], r))
            changed = changed + 1
    print("===========================================")
    print("%d URLs checked, %d different status codes" % (total, changed))

if __name__ == "__main__":
    main()
