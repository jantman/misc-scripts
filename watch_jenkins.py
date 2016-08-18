#!/usr/bin/env python
"""
Python script using python-jenkins (https://pypi.python.org/pypi/python-jenkins) to
watch a job (specified by URL), and exit 0 on success or 1 on failure.

requirements:
pip install python-jenkins
pip install python-pushover (optional)

for pushover configuration, see the section on ~/.pushoverrc in the Configuration section:
http://pythonhosted.org/python-pushover/#configuration

##################

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/watch_jenkins.py

CHANGELOG:

2016-08-17 jantman:
- environment variables for username and password
- change get_job_name_and_build_number(url) algorithm to be a bit more naive,
  but properly handle namespaced jobs from the Folders plugin.
2015-11-15 jantman:
- switch from optparse to argparse
- add support for authenticated access
2014-12-14 jantman:
- add better links to config docs
2014-12-12 jantman:
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

from jenkins import Jenkins, JenkinsException

try:
    from urllib.parser import urlparse
except ImportError:
    from urlparse import urlparse

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

try:
    from pushover import init, Client, get_sounds
    have_pushover = True
except ImportError:
    logger.warning("Pushover support disabled; `pip install python-pushover` to enable it")
    have_pushover = False

def main(build_url, sleeptime=15, pushover=False, user=None, password=None):
    if pushover and not have_pushover:
        raise SystemExit("ERROR: to use pushover notifications, please `pip install python-pushover` and configure it.")
    job_name, build_no = get_job_name_and_build_number(build_url)
    logger.info("Job: %s", job_name)
    logger.info("Build Number: %s", build_no)
    jenkins_url = get_jenkins_base_url(build_url)
    logger.debug("Connecting to Jenkins...")

    if user is not None:
        logger.debug("Connecting to Jenkins as user %s ...", user)
        j = Jenkins(jenkins_url, user, password)
    else:
        logger.debug("Connecting to Jenkins anonymously...")
        j = Jenkins(jenkins_url)
    logger.debug("Connected.")

    if build_no is None:
        jobinfo = j.get_job_info(job_name)
        build_no = jobinfo['nextBuildNumber'] - 1
        logger.info("Using latest build, #{b}".format(b=build_no))
    build_url = get_formal_build_url(jenkins_url, job_name, build_no)
    print("Watching job {j} #{b} until completion <{u}>...".format(j=job_name, b=build_no, u=build_url))
    while True:
        logger.debug("Getting build info...")
        buildinfo = j.get_build_info(job_name, build_no)
        if not buildinfo['building']:
            # job is not still building
            duration = datetime.timedelta(seconds=(buildinfo['duration'] / 1000))
            if pushover:
                notify_pushover(buildinfo['result'], job_name, build_no, duration, build_url)
            if buildinfo['result'] == "SUCCESS":
                print("SUCCESS for {j} #{b} in {d} <{bu}>".format(j=job_name, b=build_no, bu=build_url, d=duration))
                raise SystemExit(0)
            print("{r}: {j} #{b} failed in {d}".format(j=job_name, b=build_no, r=buildinfo['result'], d=duration))
            raise SystemExit(1)
        else:
            duration = datetime.datetime.now() - datetime.datetime.fromtimestamp(buildinfo['timestamp'] / 1000)
            print("still running ({d})...".format(d=duration))
        time.sleep(sleeptime)

def notify_pushover(result, job_name, build_no, duration, build_url):
    """ send notification via pushover """
    msg = '{r}: {j} #{b} finished in {d} <{u}>'.format(r=result,
                                                       j=job_name,
                                                       b=build_no,
                                                       d=duration,
                                                       u=build_url)
    title = '{r}: {j} #{b}'.format(r=result,
                                   j=job_name,
                                   b=build_no)
    if result != "SUCCESS":
        req = Client().send_message(msg, title=title, priority=0, sound='falling')
    else:
        req = Client().send_message(msg, title=title, priority=0)

def get_job_name_and_build_number(url):
    """
    Simple, naive implementation of getting job name and build number from URL.
    """
    # strip /console if present
    if url.endswith('/console'):
        url = url[:len(url) - 8]
    # make sure it's a job URL
    if 'job/' not in url:
        raise Exception("Could not parse URL - 'job/' not in %s" % url)
    # if it ends in a build number, capture that and then strip it
    build_no = None
    m = re.match(r'.*(/\d+/?)$', url)
    if m is not None and m.group(1) != '':
        build_no = int(m.group(1).strip('/'))
        url = url[:(-1 * len(m.group(1))) + 1]
    # get the path
    parsed = urlparse(url)
    # simple, naive job URL parsing
    job = parsed.path.replace('job/', '').strip('/')
    return job, build_no

def get_formal_build_url(jenkins_url, job_name, build_no):
    """
    Shamelessly stolen from twoline-utils by @coddingtonbear
    https://github.com/coddingtonbear/twoline-utils/blob/master/twoline_utils/commands.py
    licensed under MIT license, Copyright 2014 Adam Coddington
    """
    return os.path.join(
        jenkins_url,
        'job',
        job_name,
        str(build_no)
    )

def get_jenkins_base_url(url):
    """
    Shamelessly stolen from twoline-utils by @coddingtonbear
    https://github.com/coddingtonbear/twoline-utils/blob/master/twoline_utils/commands.py
    licensed under MIT license, Copyright 2014 Adam Coddington
    """
    parsed = urlparse(url)
    return parsed.scheme + '://' + parsed.netloc

def parse_args(argv):
    """ parse arguments/options """
    p = argparse.ArgumentParser()

    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='verbose (debugging) output')
    p.add_argument('-s', '--sleep-time', dest='sleeptime', action='store',
                   type=int, default=15, help='time in seconds to sleep '
                   'between status checks; default 15')
    p.add_argument('-u', '--user', dest='user', action='store', type=str,
                   default=None, help='Jenkins username (optional); will be '
                                      'read from JENKINS_USER environment '
                                      'variable if that is set.')
    p.add_argument('-p', '--password', dest='password', action='store',
                   type=str,
                   default=None, help='Jenkins password (optional; if -u/--user'
                   ' is specified and this is not, you will be interactively '
                   'prompted); will be read from JENKINS_PASS environment '
                   'variable if that is set.')

    push_default = False
    if os.path.exists(os.path.expanduser('~/.watch_jenkins_pushover')):
        push_default = True
    p.add_argument('-P', '--pushover', dest='pushover', action='store_true',
                   default=push_default, help='notify on completion via '
                   'pushover (default {p}; touch ~/.watch_jenkins_pushover to '
                   'default to True)'.format(p=push_default))

    p.add_argument('URL', action='store', type=str,
                   help='Build URL')

    args = p.parse_args(argv)
    if args.user is None and 'JENKINS_USER' in os.environ:
        logger.warning('Setting username from JENKINS_USER env var.')
        args.user = os.environ['JENKINS_USER']
    if args.password is None and 'JENKINS_PASS' in os.environ:
        logger.warning('Setting password from JENKINS_PASS env var.')
        args.password = os.environ['JENKINS_PASS']
    if args.user is not None and args.password is None:
        args.password = getpass.getpass("Password for %s Jenkins "
                                        "user: " % args.user)
    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    main(args.URL, sleeptime=args.sleeptime, pushover=args.pushover,
         user=args.user, password=args.password)
