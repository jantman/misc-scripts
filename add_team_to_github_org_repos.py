#!/usr/bin/env python
#
# Script using PyGithub to add a specified GitHub Team to all of an Organization's repositories.
#
# Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
# Free for any use provided that patches are submitted back to me.
#
# The latest version of this script can be found at:
# <https://github.com/jantman/misc-scripts/blob/master/add_team_to_github_org_repos.py>
#
# Requires PyGithub - `pip install PyGithub` (tested against 1.23.0)
# tested with py27 and py32
#
# Assumes you have a GitHub API Token, either in ~/.ssh/apikeys.py or
# in a GITHUB_TOKEN environment variable.
#
# CHANGELOG:
# - initial script
#

from github import Github
import os
import sys

if len(sys.argv) < 3:
    sys.stderr.write("USAGE: github_org_repos.py <orgname> <teamname>\n")
    raise SystemExit(1)

orgname = sys.argv[1]
teamname = sys.argv[2]

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
        raise SystemExit(1)

g = Github(login_or_token=TOKEN)
org = g.get_organization(orgname)

team = None
for t in org.get_teams():
    if t.name == teamname:
        team = t

if team is None:
    sys.stderr.write("ERROR: could not find team '%s'\n" % teamname)
    raise SystemExit(1)

team_repos = [r.id for r in team.get_repos()]
print("Team %s has %d repositories" % (teamname, len(team_repos)))

for repo in org.get_repos():
    if repo.id in team_repos:
        print("%s is already in team's repositories" % repo.name)
        continue
    print("Adding repo %s to team's repositories" % repo.name)
    team.add_to_repos(repo)
