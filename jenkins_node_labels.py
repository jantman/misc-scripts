#!/usr/bin/env python
"""
Python script using python-jenkins (https://pypi.python.org/pypi/python-jenkins)
to list all nodes on a Jenkins master, and their labels.

requirements:
- pip install python-jenkins
- lxml

NOTICE: this assumes that you have unauthenticated read access enabled for Jenkins.
If you need to authenticate to Jekins in order to read job status, see the comment
in the main() function.

##################

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/jenkins_node_labels.py

CHANGELOG:

2015-10-06 jantman:
- initial script
"""

import sys
import argparse
import logging
import re
import time
import os
import datetime
import getpass
from io import StringIO

try:
    from lxml import etree
except ImportError:
    try:
        # normal cElementTree install
        import cElementTree as etree
    except ImportError:
        try:
            # normal ElementTree install
            import elementtree.ElementTree as etree
        except ImportError:
            raise SystemExit("Failed to import ElementTree from any known place")

from jenkins import Jenkins, JenkinsException, NotFoundException

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

def main(jenkins_url, user=None, password=None, csv=False):
    """
    NOTE: this is using unauthenticated / anonymous access.
    If that doesn't work for you, change this to something like:
    j = Jenkins(jenkins_url, 'username', 'password')
    """
    if user is not None:
        logger.debug("Connecting to Jenkins as user %s ...", user)
        j = Jenkins(jenkins_url, user, password)
    else:
        logger.debug("Connecting to Jenkins anonymously...")
        j = Jenkins(jenkins_url)
    logger.debug("Connected.")
    labels = {}
    nodes = j.get_nodes()
    for node in nodes:
        try:
            config = j.get_node_config(node['name'])
            logger.debug("got config for node %s", node['name'])
            root = etree.fromstring(config.encode('UTF-8'))
            label = root.xpath('//label')[0].text
            if label is not None and label != '':
                labels[node['name']] = label.split(' ')
        except NotFoundException:
            logger.error("Could not get config for node %s", node['name'])
            continue
    if 'master' in labels:
        tmp = labels['master']
        labels['<master>'] = tmp
    else:
        labels['<master>'] = '<unknown>'
    if not csv:
        print(dict2cols(labels))
        return
    # csv
    for sname, lbls in labels.items():
        print('%s,%s' % (sname, ','.join(lbls)))

def dict2cols(d, spaces=2, separator=' '):
    """
    Code taken from awslimitchecker <http://github.com/jantman/awslimitchecker>

    Take a dict of string keys and string values, and return a string with
    them formatted as two columns separated by at least ``spaces`` number of
    ``separator`` characters.

    :param d: dict of string keys, string values
    :type d: dict
    :param spaces: number of spaces to separate columns by
    :type spaces: int
    :param separator: character to fill in between columns
    :type separator: string
    """
    if len(d) == 0:
        return ''
    s = ''
    maxlen = max([len(k) for k in d.keys()])
    fmt_str = '{k:' + separator + '<' + str(maxlen + spaces) + '}{v}\n'
    for k in sorted(d.keys()):
        s += fmt_str.format(
            k=k,
            v=d[k],
        )
    return s

def parse_args(argv):
    """ parse arguments/options """
    p = argparse.ArgumentParser()

    p.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                   help='verbose (debugging) output')
    p.add_argument('-u', '--user', dest='user', action='store', type=str,
                   default=None, help='Jenkins username (optional)')
    p.add_argument('-p', '--password', dest='password', action='store', type=str,
                   default=None, help='Jenkins password (optional; if -u/--user'
                   'is specified and this is not, you will be interactively '
                   'prompted')
    p.add_argument('-c', '--csv', dest='csv', action='store_true', default=False,
                   help='output in CSV')
    p.add_argument('JENKINS_URL', action='store', type=str,
                   help='Base URL to access Jenkins instance')
    args = p.parse_args(argv)
    if args.user is not None and args.password is None:
        args.password = getpass.getpass("Password for %s Jenkins user: " % args.user)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    main(args.JENKINS_URL, user=args.user, password=args.password, csv=args.csv)
