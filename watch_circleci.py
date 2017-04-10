#!/usr/bin/env python
"""
Python script using circleclient (https://pypi.python.org/pypi/circleclient) to
watch a job, exit 0 on success or 1 on failure, and optionally notify via Pushover.

**Note:** To use with CircleCI Enterprise instances, this requires
`circleclient PR #11 <https://github.com/qba73/circleclient/pull/11>`_ which
was merged in June 2016, but 10 months later still isn't in the latest PyPI
release. Until 0.1.7 is out, please install circleclient from git as shown
below:

requirements:
pip install git+https://github.com/qba73/circleclient.git
pip install python-pushover (optional)

Tested with circleclient @ b766f7d and ``python-pushover==0.3``

for pushover configuration, see the section on ~/.pushoverrc in the
Configuration section:
http://pythonhosted.org/python-pushover/#configuration

##################

Copyright 2017 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/watch_circleci.py>

CHANGELOG:

2017-04-06 jantman:
- initial script
"""

import sys
import argparse
import logging
from time import sleep
import re
import os
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

from circleclient import circleclient

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger(__name__)

try:
    from pushover import init, Client, get_sounds
    have_pushover = True
except ImportError:
    logger.warning(
        "Pushover support disabled; `pip install python-pushover` to enable it"
    )
    have_pushover = False


def red(s):
    """
    Return the given string (``s``) surrounded by the ANSI escape codes to
    print it in red.
    :param s: string to console-color red
    :type s: str
    :returns: s surrounded by ANSI color escapes for red text
    :rtype: str
    """
    return "\033[0;31m" + s + "\033[0m"


def yellow(s):
    """
    Return the given string (``s``) surrounded by the ANSI escape codes to
    print it in yellow.
    :param s: string to console-color yellow
    :type s: str
    :returns: s surrounded by ANSI color escapes for yellow text
    :rtype: str
    """
    return "\033[0;33m" + s + "\033[0m"


def green(s):
    """
    Return the given string (``s``) surrounded by the ANSI escape codes to
    print it in green.
    :param s: string to console-color green
    :type s: str
    :returns: s surrounded by ANSI color escapes for green text
    :rtype: str
    """
    return "\033[0;32m" + s + "\033[0m"


def human_duration(millis):
    """
    Return a human-readable duration for a time in milliseconds.

    :param millis: milliseconds
    :type millis: int
    :return: human-readable duration
    :rtype: str
    """
    seconds = millis / 1000.0
    s = ''
    if seconds > 3600:
        s = '%dh ' % (seconds / 3600)
        seconds = seconds % 3600
    if seconds > 60:
        s += '%dm ' % (seconds / 60)
        seconds = seconds % 60
    s += '%ds' % seconds
    return s


class CircleWatcher(object):

    _circle_url_re = re.compile(
        r'^/gh/(?P<org>[^/]+)/(?P<proj>[^/]+)(?:/(?P<buildnum>\d+))?$', re.I
    )

    def __init__(self, url, token,
                 sleep_time=15, pushover=False, retry_failed=False):
        """
        Instantiate a CircleWatcher.

        :param url: URL to build or project
        :type url: str
        :param token: CircleCI API token
        :type token: str
        :param sleep_time: time to sleep between polls, in seconds
        :type sleep_time: int
        :param pushover: whether to notify via Pushover on build completion
        :type pushover: bool
        :param retry_failed: whether or not to retry the build if it fails
        :type retry_failed: bool
        """
        self._url = url
        self._token = token
        self._sleep_time = sleep_time
        if args.pushover:
            if not have_pushover:
                raise SystemExit(
                    "ERROR: to use pushover notifications, please `pip "
                    "install python-pushover` and configure it."
                )
            if 'PUSHOVER_APIKEY' not in os.environ:
                raise SystemExit(
                    "ERROR: to use pushover notifications, export your "
                    "Pushover API key as the 'PUSHOVER_APIKEY' environment "
                    "variable."
                )
            if 'PUSHOVER_USERKEY' not in os.environ:
                raise SystemExit(
                    "ERROR: to use pushover notifications, export your "
                    "Pushover User Key as the 'PUSHOVER_USERKEY' environment "
                    "variable."
                )
            init(os.environ['PUSHOVER_APIKEY'])
            self._pushover_userkey = os.environ['PUSHOVER_USERKEY']
        self._pushover = pushover
        self._retry_failed = retry_failed
        self._endpoint = self._endpoint_for_url(self._url)
        logger.debug('Connecting to CircleCI with API URL: %s', self._endpoint)
        # BEGIN hack around unreleased circleclient PR #11
        if self._endpoint == 'https://circleci.com/api/v1':
            self._circle = circleclient.CircleClient(api_token=self._token)
        else:
            try:
                self._circle = circleclient.CircleClient(
                    api_token=self._token, endpoint=self._endpoint
                )
            except TypeError:
                raise SystemExit(
                    'CircleCI Enterprise installations require circleclient '
                    '>0.1.6; please try: pip install --upgrade '
                    'git+https://github.com/qba73/circleclient.git')
        # END hack around unreleased circleclient PR #11
        logger.debug(
            'Connected to CircleCI as user: %s',
            self._circle.user.info()['name']
        )

    def _endpoint_for_url(self, url):
        """
        Given a CircleCI URL, return the appropriate endpoint URL for it.

        :param url: CircleCI build/job URL
        :type url: str
        :return: endpoint URL for that CircleCI instance
        :rtype: str
        """
        if url.startswith('https://circleci.com'):
            return 'https://circleci.com/api/v1'
        p = urlparse(url)
        return '%s://%s/api/v1' % (p.scheme, p.netloc)

    def _parse_circle_url(self, url):
        """
        Parse a CircleCI URL into org/user, project and build number.

        :param url: CircleCI URL
        :type url: str
        :return: org/user, project, build number
        :rtype: tuple
        """
        p = urlparse(url)
        logger.debug('Parsing project/build info from path: %s', p.path)
        m = self._circle_url_re.match(p.path)
        if not m:
            sys.stderr.write(
                "Error: URL path '%s' does not match CircleCI project URL "
                "regex: '%s'\n" % (p.path, self._circle_url_re.pattern)
            )
            raise SystemExit(1)
        return m.group(1), m.group(2), int(m.group(3))

    def _find_latest_build(self, org, project):
        """
        Given an org/user and project, find the latest build.

        :param org: org or user name
        :type org: str
        :param project: project name
        :type project: str
        :return: latest build number for project
        :rtype: int
        """
        return self._circle.build.recent(org, project)[0]['build_num']

    def _build_status_is_good(self, status):
        """
        Return True if the build status is a successful or positive status,
        False otherwise. Used to determine if Pushover notifications should
        be success or failure.

        :param status: CircleCI API build status
        :type status: str
        :return: whether or not the build is a success or failure
        :rtype: bool
        """
        if status in ['infrastructure_fail', 'timedout', 'failed', 'retried']:
            return False
        return True

    def _build_status_color(self, status):
        """
        Return an ANSI-colorized version of the build status

        :param status: CircleCI API build status
        :type status: str
        :return: colorized string
        :rtype: str
        """
        if status in ['infrastructure_fail', 'timedout', 'failed']:
            return red(status)
        if status in ['retried', 'no_tests']:
            return yellow(status)
        if status in ['canceled', 'fixed', 'success']:
            return green(status)
        return status

    def _build_status_is_running(self, status):
        """
        Given a textual CircleCI build status, True if the build is still
        running, False otherwise

        :param status: CircleCI API build status
        :type status: str
        :return: whether or not the build is still running/queued/scheduled
        :rtype: bool
        """
        if status in ['running', 'queued', 'scheduled']:
            return True
        return False

    def _watch_build(self, org, project, bnum):
        """
        Watch a build until it finishes.

        :param org: org or user name
        :type org: str
        :param project: project name
        :type project: str
        :param bnum: build number
        :type bnum: int
        """
        print('Watching build %d of %s/%s' % (bnum, org, project))
        info = self._circle.build.status(org, project, bnum)
        while self._build_status_is_running(info['status']):
            print('Build %d (%s) status: %s (sleeping %ds)...' % (
                bnum, info['build_url'], info['status'], self._sleep_time
            ))
            sleep(self._sleep_time)
            info = self._circle.build.status(org, project, bnum)
        print('Build %d of %s/%s (%s) finished: %s' % (
            bnum, org, project, info['build_url'],
            self._build_status_color(info['status'])
        ))
        if self._pushover:
            self.notify_pushover(
                info['status'], org, project, bnum,
                info['build_url'], human_duration(info['build_time_millis'])
            )
        if not self._retry_failed:
            return
        if self._build_status_is_good(info['status']):
            return
        # check status again in 15s to make sure it wasn't retried automatically
        print(
            'sleeping %ds to ensure status has stabilized...' % self._sleep_time
        )
        sleep(self._sleep_time)
        info = self._circle.build.status(org, project, bnum)
        if self._build_status_is_good(info['status']):
            return
        print('Retrying build...')
        newbuild = self._circle.build.retry(org, project, bnum)
        print('New (retry) build: %d <%s>' % (
            newbuild['build_num'], newbuild['build_url']
        ))
        self._watch_build(org, project, newbuild['build_num'])

    def run(self):
        """Run the watcher"""
        org, project, build = self._parse_circle_url(self._url)
        logger.info(
            'URL parsed to: org/user=%s project=%s build=%s',
            org, project, build
        )
        if build is None:
            build = self._find_latest_build(org, project)
            logger.info('Using latest build: %d', build)
        self._watch_build(org, project, build)

    def notify_pushover(self, status, org, project, build_num,
                        build_url, duration):
        """ send notification via pushover """
        msg = '{s}: {o}/{p} #{b} finished in {d} <{u}>'.format(
            s=status,
            o=org,
            p=project,
            b=build_num,
            d=duration,
            u=build_url
        )
        title = '{s}: {o}/{p} #{b}'.format(
            s=status,
            o=org,
            p=project,
            b=build_num
        )
        argv = {
            'title': title,
            'priority': 0
        }
        if not self._build_status_is_good(status):
            argv['sound'] = 'falling'
        logger.debug('Sending pushover notification; msg="%s" argv=%s',
                     msg, argv)
        Client(self._pushover_userkey).send_message(msg, **argv)


def parse_args(argv):
    """ parse arguments/options """
    desc = "Watch CircleCI build status, exit 0 on success or 1 on failure; " \
           "optionally notify via Pushover."
    p = argparse.ArgumentParser(description=desc)

    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='verbose (debugging) output')
    p.add_argument('-s', '--sleep-time', dest='sleeptime', action='store',
                   type=int, default=15, help='time in seconds to sleep '
                   'between status checks; default 15')
    p.add_argument('-P', '--pushover', dest='pushover', action='store_true',
                   default=False, help='notify on completion via pushover')
    p.add_argument('-r', '--retry-failed', dest='retry_failed',
                   action='store_true', default=False,
                   help='automatically retry failed builds')
    p.add_argument('URL', action='store', type=str,
                   help='Build or project URL. If Project URL, will watch '
                        'newest build for the project.')
    args = p.parse_args(argv)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if not hasattr(args, 'token'):
        args.token = os.environ.get('CIRCLE_TOKEN', None)
    if args.token is None:
        raise SystemExit('Please export your CircleCI token as the '
                         'CIRCLE_TOKEN environment variable')
    CircleWatcher(
        args.URL, args.token, sleep_time=args.sleeptime,
        pushover=args.pushover, retry_failed=args.retry_failed
    ).run()
