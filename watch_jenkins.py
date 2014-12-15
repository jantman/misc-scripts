#!/usr/bin/env python
"""
Python script using python-jenkins (https://pypi.python.org/pypi/python-jenkins) to
watch a job (specified by URL), and exit 0 on success or 1 on failure.

requirements:
pip install python-jenkins
pip install python-pushover (optional)

for pushover configuration, see the section on ~/.pushoverrc in the Configuration section:
http://pythonhosted.org/python-pushover/#configuration

NOTICE: this assumes that you have unauthenticated read access enabled for Jenkins.
If you need to authenticate to Jekins in order to read job status, see the comment
in the main() function.

##################

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/watch_jenkins.py

CHANGELOG:

2014-12-12 jantman:
- initial script
2014-12-14 jantman:
- add better links to config docs
"""

import sys
import optparse
import logging
import re
import time
import os
import datetime

try:
    from urllib.parser import urlparse
except ImportError:
    from urlparse import urlparse

from jenkins import Jenkins, JenkinsException

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

try:
    from pushover import init, Client, get_sounds
    have_pushover = True
except ImportError:
    logger.warning("Pushover support disabled; `pip install python-pushover` to enable it")
    have_pushover = False

def main(build_url, sleeptime=15, pushover=False):
    if pushover and not have_pushover:
        raise SystemExit("ERROR: to use pushover notifications, please `pip install python-pushover` and configure it.")
    job_name, build_no = get_job_name_and_build_number(build_url)
    jenkins_url = get_jenkins_base_url(build_url)
    logger.debug("Connecting to Jenkins...")
    """
    NOTE: this is using unauthenticated / anonymous access.
    If that doesn't work for you, change this to something like:
    j = Jenkins(jenkins_url, 'username', 'password')
    """
    j = Jenkins(jenkins_url)
    logger.debug("Connected.")
    if build_no is None:
        jobinfo = j.get_job_info(job_name)
        build_no = jobinfo['nextBuildNumber'] - 1
        print("Using latest build, #{b}".format(b=build_no))
    build_url = get_formal_build_url(jenkins_url, job_name, build_no)
    print("Watching job {j} #{b} until completion <{u}>...".format(j=job_name, b=build_no, u=build_url))
    while True:
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
    Shamelessly stolen from twoline-utils by @coddingtonbear
    https://github.com/coddingtonbear/twoline-utils/blob/master/twoline_utils/commands.py
    licensed under MIT license, Copyright 2014 Adam Coddington

    with slight modifications for job without build number
    """
    job_build_matcher = re.compile(
        ".*/job/(?P<job>[^/]+)/((?P<build_number>[^/]+)/.*)?"
    )
    tmp = job_build_matcher.search(url).groups()
    job = tmp[0]
    if tmp[2] is not None:
        build_no = int(tmp[2])
    else:
        build_no = None
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
    p = optparse.OptionParser(usage="usage: %prog [options] build_or_job_url")

    p.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False,
                 help='verbose (debugging) output')
    p.add_option('-s', '--sleep-time', dest='sleeptime', action='store', type=int, default=15,
                 help='time in seconds to sleep between status checks; default 15')
    push_default = False
    if os.path.exists(os.path.expanduser('~/.watch_jenkins_pushover')):
        push_default = True
    p.add_option('-p', '--pushover', dest='pushover', action='store_true', default=push_default,
                 help='notify on completion via pushover (default {p}; touch ~/.watch_jenkins_pushover to default to True)'.format(p=push_default))

    options, args = p.parse_args(argv)

    return options, args


if __name__ == "__main__":
    opts, args = parse_args(sys.argv[1:])

    if opts.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if len(args) < 1:
        raise SystemExit("ERROR: you must specify a build or job url")

    main(args[0], sleeptime=opts.sleeptime, pushover=opts.pushover)
