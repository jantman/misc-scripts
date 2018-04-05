#!/usr/bin/env python
"""
Python script using ``requests`` to generate, list, and download JFrog
Artifactory support bundles via the ReST API, from one or more instances/nodes.

Tested against JFrog Artifactory Enterprise 4.16.1 (HA Cluster).

Should work with python 3.4+. Requires ``requests`` from pypi.

The latest version of this script can be found at:
http://github.com/jantman/misc-scripts/blob/master/artifactory_support_bundle.py

Copyright 2018 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG (be sure to increment VERSION):

v0.1.0 2018-04-05 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import os
import sys
import argparse
import logging
from json.decoder import JSONDecodeError
from urllib.parse import urlparse
from time import time

try:
    import requests
except ImportError:
    sys.stderr.write(
        'ERROR: this script requires the python "requests" package. Please '
        'install it with "pip install requests"'
    )
    raise SystemExit(1)

VERSION = '0.1.0'
PROJECT_URL = 'https://github.com/jantman/misc-scripts/blob/master/' \
              'artifactory_support_bundle.py'

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class ArtifactorySupportBundles(object):
    """Class to manage JFrog Artifactory support bundles via ReST API"""

    def __init__(self, username, password, urls):
        self._username = username
        self._password = password
        self.urls = []
        for u in urls:
            if u.endswith('/'):
                self.urls.append(u)
            else:
                self.urls.append(u + '/')
        logger.debug('Artifactory URLs: %s', urls)
        self._requests = requests.Session()
        self._requests.auth = (self._username, self._password)

    def run(self, action):
        """ do stuff here """
        logger.debug('Running action: %s', action)
        if action == 'list-bundles':
            return self.list_bundles()
        if action == 'get-latest-bundle':
            return self.get_latest_bundle()
        if action == 'create-bundle':
            return self.create_bundle()
        raise RuntimeError('Unknown action: %s' % action)

    def _list_bundles(self, art_url):
        url = '%sapi/support/bundles/' % art_url
        logger.debug('GET %s', url)
        res = self._requests.get(url)
        logger.debug(
            '%s responded %s %s with %d bytes', url, res.status_code,
            res.reason, len(res.content)
        )
        if len(res.content) == 0:
            logger.info('%s returned empty response; assuming no bundles', url)
            return []
        try:
            val = res.json()['bundles']
        except JSONDecodeError:
            logger.error('Error decoding response as JSON: %s', res.text)
            raise
        return val

    def list_bundles(self):
        for url in self.urls:
            print('=> %s' % url)
            res = self._list_bundles(url)
            if len(res) == 0:
                print('(no bundles)')
                continue
            for b in res:
                print(b)

    def _get_bundle(self, url, bundle_path):
        p = urlparse(url)
        fname = '%s_%s' % (p.hostname, bundle_path)
        logger.debug('GET %s to: %s', url, fname)
        res = self._requests.get(url, stream=True)
        logger.debug(
            '%s responded %s %s; streaming to disk at %s', url, res.status_code,
            res.reason, fname
        )
        res.raise_for_status()
        size = 0
        with open(fname, 'wb') as fh:
            for block in res.iter_content(1024):
                fh.write(block)
                size += len(block)
        logger.info('Downloaded %d bytes to: %s', size, fname)
        return fname

    def get_latest_bundle(self):
        success = True
        for url in self.urls:
            bundles = self._list_bundles(url)
            logger.debug('Bundles for %s: %s', url, bundles)
            if len(bundles) < 1:
                logger.warning('No bundles found for %s; skipping', url)
                continue
            bundle_path = os.path.basename(sorted(bundles)[-1])
            logger.debug('Filename for latest bundle: %s', bundle_path)
            bundle_url = '%sapi/support/bundles/%s' % (url, bundle_path)
            try:
                path = self._get_bundle(bundle_url, bundle_path)
                print('Downloaded %s to: %s' % (bundle_url, path))
            except Exception:
                logger.error(
                    'Exception downloading %s', bundle_url, exc_info=True
                )
                success = False
        if not success:
            logger.error('Some downloads failed.')
            raise SystemExit(1)

    def _create_bundle(self, art_url):
        """
        see: https://www.jfrog.com/confluence/display/RTF/Artifactory+REST+API
        """
        data = {
            "systemLogsConfiguration": {
                "enabled": True,
                "daysCount": 7
            },
            "systemInfoConfiguration": {
                "enabled": True
            },
            "securityInfoConfiguration": {
                "enabled": True,
                "hideUserDetails": True
            },
            "configDescriptorConfiguration": {
                "enabled": True,
                "hideUserDetails": True
            },
            "configFilesConfiguration": {
                "enabled": True,
                "hideUserDetails": True
            },
            "storageSummaryConfiguration": {
                "enabled": True
            },
            "threadDumpConfiguration": {
                "enabled": True,
                "count": 1,
                "interval": 0
            }
        }
        url = '%sapi/support/bundles/' % art_url
        logger.debug('POST to %s: %s', url, data)
        print('Triggering creation of bundle on %s...' % art_url)
        start = time()
        res = self._requests.post(url, json=data)
        duration = time() - start
        logger.debug(
            '%s responded %s %s in %s seconds with %d bytes', url,
            res.status_code, res.reason, duration, len(res.content)
        )
        res.raise_for_status()
        print('\tBundle creation complete in %s seconds' % duration)
        try:
            val = res.json()['bundles'][0]
        except JSONDecodeError:
            logger.error('Error decoding response as JSON: %s', res.text)
            raise
        return val

    def create_bundle(self):
        success = True
        for url in self.urls:
            print('=> %s' % url)
            try:
                res = self._create_bundle(url)
                print('Created bundle "%s" on %s' % (res, url))
            except Exception:
                logger.error(
                    'Exception creating bundle on %s', url, exc_info=True
                )
                success = False
        if not success:
            logger.error('Some bundle creations failed.')
            raise SystemExit(1)


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(
        description='manage JFrog Artifactory support bundles via ReST API',
        prog='artifactory_support_bundle.py',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='ACTIONS:\n'
               '  list-bundles      - list all support bundles on specified '
               'instances.\n'
               '  get-latest-bundle - download the latest support bundle'
               'from each instance.\n'
               '  create-bundle     - trigger creation of a new support bundle '
               'with all data/options and 7 days of logs, on each instance.'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument(
        '-V', '--version', action='version',
        version='%(prog)s ' + '%s <%s>' % (VERSION, PROJECT_URL)
    )
    p.add_argument(
        '-u', '--username', action='store', dest='username', default=None,
        help='Artifactory username. Can also be specified via ARTIFACTORY_USER '
             'environment variable (argument overrides environment variable).',
        type=str
    )
    p.add_argument(
        '-p', '--password', action='store', dest='password', default=None,
        help='Artifactory password. Can also be specified via ARTIFACTORY_PASS '
             'environment variable (argument overrides environment variable). '
             'An Artifactory API key can also be used as a password with '
             'Artifactory >= 4.4.3.',
        type=str
    )
    actions = ['list-bundles', 'get-latest-bundle', 'create-bundle']
    p.add_argument(
        'ACTION', action='store', choices=actions,
        help='action to perform; see below for details'
    )
    p.add_argument(
        'ARTIFACTORY_URL', type=str, nargs='+',
        help='URL(s) to one or more Artifactory instances to run actions '
             'against; form should be "http(s)://server(:port)?/artifactory/"'
    )
    args = p.parse_args(argv)
    for argname, varname in {
        'username': 'ARTIFACTORY_USER',
        'password': 'ARTIFACTORY_PASS'
    }.items():
        if getattr(args, argname) is None:
            e = os.environ.get(varname, None)
            if e is None:
                raise RuntimeError(
                    'ERROR: you must specify either the %s option or the '
                    '%s environment variable.' % (argname, varname)
                )
            setattr(args, argname, e)
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

    script = ArtifactorySupportBundles(
        args.username, args.password, args.ARTIFACTORY_URL
    )
    script.run(args.ACTION)
