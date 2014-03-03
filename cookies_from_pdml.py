#!/usr/bin/env python
"""
Script to parse http Cookie header field from WireShark PDML XML.

This is a quick hack. Lots of problems.

By Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
https://github.com/jantman/misc-scripts/blob/master/cookies_from_pdml.py
"""

from lxml import etree
import binascii
import sys
import optparse


def pdml_header_fields(fname, field_name):
    """ return list of all values for HTTP header field_name """
    tree = etree.parse(fname)
    results = []
    for e in tree.xpath('/pdml/packet/proto[@name="http"]/field[@name="http.cookie"]'):
        data = binascii.unhexlify(e.get("value"))
        results.append(data)
    return results

def parse_options(argv):
    """ parse command line options """
    parser = optparse.OptionParser()

    parser.add_option('-f', '--pdml-file', dest='fname', action='store', type='string',
                      help='PDML file name/path')

    parser.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False,
                      help='verbose output')

    options, args = parser.parse_args(argv)

    if not options.fname:
        sys.stderr.write("ERROR: you must specify PDML file with -f|--pdml-file\n")
        sys.exit(1)

    return options

if __name__ == "__main__":
    opts = parse_options(sys.argv)
    cookies = pdml_header_fields(opts.fname, "Cookie")
    for cookie in cookies:
        print("Length: %d" % len(cookie))
        print(cookie)
        print("####################")
