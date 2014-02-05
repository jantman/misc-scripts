#!/usr/bin/env python
#
# Script using PyGithub to list an organization's repos and some info about them.
#
# <https://github.com/jantman/misc-scripts/blob/master/list_github_org_repos.py>
#
# Requires PyGithub - `pip install PyGithub` (tested against 1.23.0)
# tested with py27 and py32
#
# Assumes you have a GitHub API Token, either in ~/.ssh/apikeys.py or
# in a GITHUB_TOKEN environment variable.
#

from github import Github
import os
import sys

if len(sys.argv) < 2:
    sys.stderr.write("USAGE: github_org_repos.py <orgname>")
    sys.exit(1)

orgname = sys.argv[1]

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

for repo in g.get_organization(orgname).get_repos():
    f = " fork of %s/%s" % (repo.parent.owner.name, repo.parent.name) if repo.fork else ''
    p = 'private' if repo.private else 'public'
    fc = "; %d forks" % (repo.forks_count) if (repo.forks_count > 0) else ''
    print("%s (%s%s%s) %s" % (repo.name, p, f, fc, repo.html_url))
