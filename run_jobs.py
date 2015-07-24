#!/usr/bin/env python
"""
Python script using python-jenkins (https://pypi.python.org/pypi/python-jenkins) to
trigger a series of Jenkins jobs which depend on each other. This is NOT well-parameterized;
configuration is hard-coded in the run() method.

requirements:
pip install python-jenkins
pip install python-pushover (optional)

for pushover configuration, see the section on ~/.pushoverrc in the Configuration section:
http://pythonhosted.org/python-pushover/#configuration

NOTICE: this assumes that you have unauthenticated read access enabled for Jenkins.
If you need to authenticate to Jekins in order to read job status, see the comment
in the main() function.

##################

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:

2015-06-03 jantman:
- initial script

"""

import sys
import argparse
import logging
import re
import time
import os
import datetime
from pprint import pprint, pformat
from ConfigParser import SafeConfigParser
from cm.utils import get_id_pw
from six.moves.urllib.request import Request, urlopen
from copy import deepcopy

try:
    from urllib.parser import urlparse
except ImportError:
    from urlparse import urlparse

from jenkins import Jenkins, JenkinsException

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger(__name__)

try:
    from pushover import init, Client, get_sounds
    have_pushover = True
except ImportError:
    logger.warning("Pushover support disabled; `pip install python-pushover` to enable it")
    have_pushover = False


class JobFailedError(Exception):

    def __init__(self, job_name, build_num, duration):
        self.job_name = job_name
        self.duration = duration
        self.build_num = build_num

        msg = "Job {j} #{b} failed after {d}".format(j=job_name, d=duration, b=build_num)
        super(JobFailedError, self).__init__(msg)


class JenkinsMultiJobRunner(object):

    def __init__(self, jenkins_url, cm_ini_path, sleeptime=15, pushover=False):
        self.jenkins_url = jenkins_url
        self.sleeptime = sleeptime
        self.pushover = pushover

        logger.debug("Getting Jenkins credentials from cm configuration")
        # get jenkins API credentials from cm
        cm_ini_path = os.path.abspath(os.path.expanduser(cm_ini_path))
        config = SafeConfigParser()
        config.readfp(open(cm_ini_path))
        # like cm.utils.get_id_pw but gets token too
        idpw = SafeConfigParser()
        idpw_path = os.path.expanduser(config.get("defaults", "id_pw"))
        idpw.readfp(open(idpw_path))
        username = idpw.get('jenkins_api', 'id')
        password = idpw.get('jenkins_api', 'pw')
        token = idpw.get('jenkins_api', 'token')
        self.token = token
        # done getting from cm
        logger.debug("Connecting to Jenkins")
        self.jenkins = Jenkins(jenkins_url, username=username, password=password)
        logger.debug("Connected; auth={a}".format(a=self.jenkins.auth))

    def run(self):
        """main entry point"""
        # map params to their values;
        # applies them to any jobs that have a same-named parameter
        builds = [
            # img_type, cm_branch, machinist_branch
            ('rhel7-base-vmware', 'B-07245', 'B-07245'),
        ]
        for b in builds:
            try:
                res = self.do_build(b[0], b[1], b[2])
                print("SUCCEEDED: img_type=%s cm_branch=%s machinist_branch=%s" % b)
            except Exception as ex:
                logger.exception(ex)
                print("FAILED: img_type=%s cm_branch=%s machinist_branch=%s" % b)

    def do_build(self, img_type, cm_br, mach_br):
        params = {
            'IMAGE_TYPE': img_type,
            'CM_BRANCH': cm_br,
            'MACHINIST_BRANCH': mach_br,
            'NETWORK_NAME': 'CMGIT_ProdVLAN_67',
            'GIT_REPO': 'cci-myconnection',
            'TAG': 'Webapp-Component-Build#378',
            'WSGI_FILE': 'app/wsgi.py',
            'INSTALL_REQUIREMENTS_FILE': 'true',
            'REQUIREMENTS_FILE': 'app/requirements.txt',
        }
        #base_num = self.run_job('Base-OVF-Build', params)
        base_num = 39
        ovf_b_params = deepcopy(params)
        ovf_b_params['BASE_OVF'] = "Base-OVF-Build#{b}".format(b=base_num)
        ovf_build_num, ovf_build_downstreams = self.run_job_with_downstreams('CCIMyConnection-OVF-Build', ovf_b_params)
        dep_params = deepcopy(params)
        dep_params['VM_Template'] = 'CCIMyConnection-OVF-Import#{o}'.format(o=ovf_build_downstreams['CCIMyConnection-OVF-Import'])
        # run deploy job

    def run_job_with_downstreams(self, jobname, params):
        """
        Find a job's downstream jobs. Trigger the job and wait for it to finish.
        Then wait for all triggered downstream builds to finish.
        return a tuple (build number, {downstream_name: build_num})
        """
        jobinfo = self.jenkins.get_job_info(jobname)
        downstreams = []
        if 'downstreamProjects' in jobinfo:
            downstreams = [x['name'] for x in jobinfo['downstreamProjects']]
            logger.debug("Job {j} downstreams: {d}".format(j=jobname, d=downstreams))
        build_num = self.run_job(jobname, params)
        dbuilds = {}
        for d_name in downstreams:
            d_num = self.find_downstream_build(jobname, build_num, d_name)
            dbuilds[d_name] = d_num
            logger.info("Found triggered downstream build: {d_name} #{d_num}".format(d_name=d_name, d_num=d_num))
            self.wait_on_job_status(d_name, d_num)
        logger.info("{j} #{b} and all downstreams have finished".format(j=jobname, b=build_num))
        return (build_num, dbuilds)

    def run_job(self, jobname, input_params):
        """
        Trigger a job and wait for completion.
        Return the build number.
        Raise JobFailedError if it fails
        """
        jobinfo = self.jenkins.get_job_info(jobname)
        last_build = jobinfo['lastBuild']['number']
        build_num = last_build + 1
        logger.debug("Found Job {j} <{u}> last build: {n}".format(
            j=jobname,
            u=jobinfo['url'],
            n=last_build,
        ))
        job_params = jobinfo['property'][0]['parameterDefinitions']
        params = {}
        for p in job_params:
            pname = p['name']
            if pname in input_params:
                params[pname] = input_params[pname]
            elif 'defaultParameterValue' in p and 'value' in p['defaultParameterValue'] and p['defaultParameterValue']['value'] != '':
                params[pname] = p['defaultParameterValue']['value']
        logger.info("Running job {j} with params: {p}".format(j=jobname, p=params))
        url = self.jenkins.build_job_url(jobname, params, self.token)
        logger.debug("Job URL: {u}".format(u=url))
        res = self.jenkins.build_job(jobname, parameters=params, token=self.token)
        if res is None:
            logger.error("Failed to run: {res}".format(res=res))
            raise JobFailedError(jobname, build_num, 0)
        # poll the job info
        self.wait_on_job_status(jobname, build_num)
        return build_num

    def wait_on_job_status(self, job_name, build_no):
        """
        Poll a job until it completes.
        Raise JobFailedError if it fails.
        """
        build_url = self.get_formal_build_url(self.jenkins_url, job_name, build_no)
        logger.info("Watching job {j} #{b} until completion <{u}>...".format(j=job_name, b=build_no, u=build_url))
        while True:
            buildinfo = self.jenkins.get_build_info(job_name, build_no)
            if buildinfo['building']:
                duration = datetime.datetime.now() - datetime.datetime.fromtimestamp(buildinfo['timestamp'] / 1000)
                logger.debug("still running ({d})...".format(d=duration))
                time.sleep(sleeptime)
            break
        # job is not still building
        duration = datetime.timedelta(seconds=(buildinfo['duration'] / 1000))
        logger.info("Build finished after {d} - result: {s}".format(d=duration, s=buildinfo['result']))
        if buildinfo['result'] == "SUCCESS":
            return
        raise JobFailedError(job_name, build_no, str(duration))

    def find_downstream_build(self, jobname, build_num, d_name):
        """
        For a given upstream job and build_num, find the build of downstream
        job d_name that was triggered by it. Return the downstream build number or raise.
        """
        jobinfo = self.jenkins.get_job_info(d_name)
        for build in jobinfo['builds']:
            buildinfo = self.jenkins.get_build_info(d_name, build['number'])
            for x in buildinfo['actions']:
                if 'causes' not in x:
                    continue
                for c in x['causes']:
                    if c['upstreamProject'] == jobname and c['upstreamBuild'] == build_num:
                        return build['number']
        raise RuntimeError("Unable to find build of {d} triggered by {j} #{n}".format(d=d_name, j=jobname, n=build_num))
        
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

    def get_formal_build_url(self, jenkins_url, job_name, build_no):
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

    def get_jenkins_base_url(self, url):
        """
        Shamelessly stolen from twoline-utils by @coddingtonbear
        https://github.com/coddingtonbear/twoline-utils/blob/master/twoline_utils/commands.py
        licensed under MIT license, Copyright 2014 Adam Coddington
        """
        parsed = urlparse(url)
        return parsed.scheme + '://' + parsed.netloc

    """
    def notify_pushover(self, result, job_name, build_no, duration, build_url):
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
    """


def parse_args(argv):
    """ parse arguments/options """
    p = argparse.ArgumentParser()

    p.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                   help='verbose (debugging) output')
    p.add_argument('-s', '--sleep-time', dest='sleeptime', action='store', type=int, default=15,
                   help='time in seconds to sleep between status checks; default 15')
    p.add_argument('-c', '--cm-ini', dest='cm_ini_path', action='store', type=str,
                   default='~/CMG/git/cm/cm.ini',
                   help='path to cm.ini for Jenkins credentials')
    push_default = False
    if os.path.exists(os.path.expanduser('~/.watch_jenkins_pushover')):
        push_default = True
    p.add_argument('-p', '--pushover', dest='pushover', action='store_true', default=push_default,
                   help='notify on completion via pushover (default {p}; touch ~/.watch_jenkins_pushover to default to True)'.format(p=push_default))
    p.add_argument('jenkins_url', help='jenkins base URL')
    args = p.parse_args(argv)

    return args


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    j = JenkinsMultiJobRunner(args.jenkins_url, args.cm_ini_path, sleeptime=args.sleeptime, pushover=args.pushover)
    j.run()
