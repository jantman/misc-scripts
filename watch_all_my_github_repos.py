#!/usr/bin/env python
"""
Script using PyGithub to make sure you're watching all of your own GitHub
repos.

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/watch_all_my_github_repos.py>

Requires PyGithub - `pip install PyGithub` (tested against 1.23.0)
tested with py27 and py32

Assumes you have a GitHub API Token, either in ~/.ssh/apikeys.py or
in a GITHUB_TOKEN environment variable.

CHANGELOG:

2015-07-28 Jason Antman <jason@jasonantman.com>
 - initial script
"""

from github import Github
import os
import sys

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# suppress github internal logging
github_log = logging.getLogger("github")
github_log.setLevel(logging.WARNING)
github_log.propagate = True

TOKEN = None
try:
    # look for GITHUB_TOKEN defined in ~/.ssh/apikeys.py
    sys.path.append(os.path.abspath(os.path.join(os.path.expanduser('~'), '.ssh')))
    from apikeys import GITHUB_TOKEN
    TOKEN = GITHUB_TOKEN
    logger.debug("Using GITHUB_TOKEN from ~/.ssh/apikeys")
except ImportError:
    pass

if TOKEN is None:
    try:
        TOKEN = os.environ['GITHUB_TOKEN']
        logger.debug("Using GITHUB_TOKEN env var")
    except KeyError:
        sys.stderr.write("ERROR: you must either set GITHUB_TOKEN in ~/.ssh/apikeys.py or export it as an env variable.\n")
        raise SystemExit(1)

logger.debug("Connecting to GitHub")
g = Github(login_or_token=TOKEN)
user = g.get_user()
logger.info("Connected to GitHub API as %s (%s)", user.login, user.name)

repos = user.get_repos()
for repo in repos:
    if repo.owner.login != user.login:
        logger.debug("Skipping repo %s owned by %s", repo.name, repo.owner.login)
        continue
    watched = False
    for watcher in repo.get_subscribers():
        if watcher.login == user.login:
            watched = True
            break
    if watched:
        logger.debug("Repo %s is already watched by %s", repo.name, user.login)
        continue
    logger.info("Watching repo %s", repo.name)
    user.add_to_subscriptions(repo)
