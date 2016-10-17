#!/usr/bin/env python
"""
Python script using python-jenkins (https://pypi.python.org/pypi/python-jenkins)
to query Jenkins for all installed plugins, and list them. Optionally output as
a block of Puppet code for the
[puppet-jenkins](https://github.com/jenkinsci/puppet-jenkins) module.

requirements:
- pip install python-jenkins>=0.4.9

##################

Copyright 2015, 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/jenkins_list_plugins.py

CHANGELOG:

2016-10-17 jantman:
  - migrate from jenkins_plugins_to_puppet.py; default to just listing them,
    optional Puppet output.

2015-11-16 jantman:
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

from jenkins import Jenkins, JenkinsException, NotFoundException

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

def get_plugins_dict(jenkins_url, puppet=False, user=None, password=None):
    if user is not None:
        logger.debug("Connecting to Jenkins (<%s>) as user %s ...",
                     jenkins_url, user)
        j = Jenkins(jenkins_url, user, password)
    else:
        logger.debug("Connecting to Jenkins (<%s>) anonymously...", jenkins_url)
        j = Jenkins(jenkins_url)
    logger.debug("Connected.")
    p = j.get_plugins()
    plugins = {}
    for k, v in p.items():
        plugins[k[0]] = v['version']
    return plugins

def main(jenkins_url, puppet=False, user=None, password=None):
    plugins = get_plugins_dict(jenkins_url, puppet=puppet, user=user, password=password)
    for name, ver in sorted(plugins.items()):
        if puppet:
            print("  jenkins::plugin {'%s': version => '%s'}" % (name, ver))
        else:
            print('%s:%s' % (name, ver))

def parse_args(argv):
    """ parse arguments/options """
    p = argparse.ArgumentParser()

    p.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                   help='verbose (debugging) output')
    p.add_argument('-u', '--user', dest='user', action='store', type=str,
                   default=None, help='Jenkins username (optional)')
    p.add_argument('-p', '--password', dest='password', action='store', type=str,
                   default=None, help='Jenkins password (optional; if -u/--user'
                   ' is specified and this is not, you will be interactively '
                   'prompted')
    p.add_argument('-P', '--puppet', dest='puppet', action='store_true',
                   default=False, help='output as Puppet code')
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

    main(args.JENKINS_URL, puppet=args.puppet, user=args.user, password=args.password)
