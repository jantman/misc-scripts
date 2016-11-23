#!/usr/bin/env python
#
# Script using PyGithub to list an organization's members, and then find who
# has a specified public key.
#
# Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
# Free for any use provided that patches are submitted back to me.
#
# The latest version of this script can be found at:
# <https://github.com/jantman/misc-scripts/blob/master/github_find_member_with_key.py>
#
# Requires PyGithub - `pip install PyGithub` (tested against 1.23.0)
# tested with py27 and py32
#
# Assumes you have a GitHub API Token, either in ~/.ssh/apikeys.py or
# in a GITHUB_TOKEN environment variable.
#
# CHANGELOG:
#
# * 2016-11-23 Jason Antman <jason@jasonantman.com>
# - initial script
#

from github import Github
import os
import sys
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('orgname', type=str, help='github org name')
parser.add_argument('KEY_FILE_PATH', type=str, help='path to public key')
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

print("Logging in to github")
g = Github(login_or_token=TOKEN)
with open(args.KEY_FILE_PATH, 'r') as fh:
    priv_key = fh.read().strip()
# strip the title
priv_key = ' '.join(priv_key.split(' ')[0:2]).strip()


members = [m for m in g.get_organization(args.orgname).get_members()]
print("Organization %s has %d members; searching their keys" % (args.orgname, len(members)))
for m in members:
    keys = [k for k in m.get_keys()]
    print("Checking %s (%d keys)" % (m.login, len(keys)))
    for k in keys:
        try:
            title = k.title
        except AttributeError:
            title = ''
        key_s = "Key %d %s" % (k.id, title)
        if k.key == priv_key:
            print("\tMATCH: %s" % key_s)
            raise SystemExit(0)
        else:
            print("\tno match: %s" % key_s)
print("NO MATCH!")
