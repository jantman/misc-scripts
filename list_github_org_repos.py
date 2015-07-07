#!/usr/bin/env python
#
# Script using PyGithub to list an organization's repos and some info about them.
#
# Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
# Free for any use provided that patches are submitted back to me.
#
# The latest version of this script can be found at:
# <https://github.com/jantman/misc-scripts/blob/master/list_github_org_repos.py>
#
# Requires PyGithub - `pip install PyGithub` (tested against 1.23.0)
# tested with py27 and py32
#
# Assumes you have a GitHub API Token, either in ~/.ssh/apikeys.py or
# in a GITHUB_TOKEN environment variable.
#
# CHANGELOG:
#
# * 2015-07-07 Jason Antman <jason@jasonantman.com>
# - use argparse, add csv output option
#
# * 2014-02-14 Jason Antman <jason@jasonantman.com>
# - initial script
#

from github import Github
import os
import sys
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--csv', dest='csv', action='store_true', default=False,
                    help='output as CSV')
parser.add_argument('orgname', type=str, help='github org name')
args = parser.parse_args()

TOKEN = None
try:
    # look for GITHUB_TOKEN defined in ~/.ssh/apikeys.py
    sys.path.append(os.path.abspath(os.path.join(os.path.expanduser('~'), '.ssh')))
    from apikeys import GITHUB_TOKEN
    TOKEN = GITHUB_TOKEN
except ImportError:
    pass

if TOKEN is None:
    try:
        TOKEN = os.environ['GITHUB_TOKEN']
    except KeyError:
        sys.stderr.write("ERROR: you must either set GITHUB_TOKEN in ~/.ssh/apikeys.py or export it as an env variable.\n")
        sys.exit(1)

g = Github(login_or_token=TOKEN)

if args.csv:
    print("repo_name,private_or_public,fork_of,forks,url")

for repo in g.get_organization(args.orgname).get_repos():
    p = 'private'if repo.private else 'public'
    fork_of = ''
    if repo.fork:
        fork_of = '%s/%s' % (repo.parent.owner.name, repo.parent.name)
    if args.csv:
        print("{name},{p},{fork_of},{forks},{url}".format(
            name=repo.name,
            p=p,
            fork_of=fork_of,
            forks=repo.forks_count,
            url=repo.html_url
        ))
    else:
        f = " fork of %s" % fork_of if repo.fork else ''
        fc = "; %d forks" % (repo.forks_count) if (repo.forks_count > 0) else ''
        print("%s (%s%s%s) %s" % (repo.name, p, f, fc, repo.html_url))
