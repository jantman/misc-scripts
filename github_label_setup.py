#!/usr/bin/env python
"""
github_label_setup.py
===================

Python script to setup Issue Labels on GitHub Repositories.

Your GitHub API token should either be in your global (user) git config
as github.token, or in a GITHUB_TOKEN environment variable.

Takes configuration (currently in this script) of the labels you want on your
repos, or your org's. Makes it so. Has a dry-run mode.

Requirements
-------------

github3.py (`pip install --pre github3.py`) >= github3.py-1.0.0a2

License
--------

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/github_label_setup.py>

CHANGELOG
----------

2015-11-25 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import subprocess
import os
from github3 import login, GitHub
from pprint import pprint

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

##################################
# configuration of labels to set #
##################################
LABELS = {}
# GitHub default labels
LABELS['bug'] = 'fc2929'
LABELS['duplicate'] = 'cccccc'
LABELS['enhancement'] = '84b6eb'
LABELS['invalid'] = 'e6e6e6'
LABELS['question'] = 'cc317c'
LABELS['wontfix'] = 'ffffff'

# custom labels
LABELS['discussion'] = 'c7def8'
LABELS['Docs'] = 'fbca04'
LABELS['help wanted'] = '159818'
LABELS['needs decision'] = 'fad8c7'
LABELS['testing'] = 'bfe5bf'
LABELS['unreleased fix'] = '0052cc'
LABELS['Waiting For Response'] = 'fef2c0'
LABELS['unsupported-repo'] = 'b60205'
#####################
# end configuration #
#####################

class GitHubLabelFixer:

    def __init__(self, apitoken, orgname, dry_run=False):
        """ init method, run at class creation """
        self.dry_run = dry_run
        logger.debug("Connecting to GitHub")
        self.gh = login(token=apitoken)
        logger.info("Connected to GitHub API")
        self.me = self.gh.me()
        self.orgname = orgname
        if orgname is None:
            # no orgname specified, so current user
            self.orgname = self.me.login

    def run(self):
        """iterate your repos and fix the labels"""
        for repo in self.gh.repositories():
            labels = {}
            colors = {}
            if repo.owner.login != self.orgname:
                logger.debug("Skipping %s", repo.full_name)
                continue
            for label in repo.labels():
                labels[label.name] = label
                colors[label.name] = label.color
            logger.debug("%s labels: %s", repo.full_name, colors)
            for name, color in LABELS.items():
                if name not in labels:
                    logger.info("Adding '%s' (%s) to %s",
                                name, color, repo.full_name)
                    res = repo.create_label(name, color)
                    if res is None:
                        logger.error("Error creating label %s on %s",
                                     name, repo.full_name)
                elif colors[name] != color:
                    logger.info("Updating '%s' on %s - color %s to %s",
                                name, repo.full_name, colors[name], color)
                    res = labels[name].update(name, color)
                    if not res:
                        logger.error("Error updating color")


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Fix labels on GitHub Repos')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False, help='List what changes would be made, but '
                   'do not make any.')
    p.add_argument('-o', '--orgname', dest='orgname', action='store',
                   help='repository owner name, if different from login user',
                   default=None)
    args = p.parse_args(argv)
    return args

def get_api_token():
    """ get GH api token """
    apikey = subprocess.check_output(['git', 'config', '--global',
                                      'github.token']).strip()
    if len(apikey) != 40:
        raise SystemExit("ERROR: invalid github api token from `git config "
                         "--global github.token`: '%s'" % apikey)
    return apikey

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    try:
        token = os.environ['GITHUB_TOKEN']
        logger.debug("Using API token from GITHUB_TOKEN environment variable")
    except KeyError:
        token = get_api_token()
        logger.debug("Using API token from git config 'github.token'")
    script = GitHubLabelFixer(token, args.orgname, dry_run=args.dry_run)
    script.run()
