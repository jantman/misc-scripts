#!/usr/bin/env python
"""
github_irc_hooks.py
===================

Python script to setup IRC notification hooks on GitHub repositories.

Your GitHub API token should either be in your global (user) git config
as github.token, or in a GITHUB_TOKEN environment variable.

This script assumes a server without Nickserv.

Requirements
-------------

github3.py (`pip install github3.py`)

License
--------

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/github_irc_hooks.py>

CHANGELOG
----------

2015-07-08 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import subprocess
import os
from github3 import login, GitHub

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)


class GitHubIRCHooker:
    """ might as well use a class. It'll make things easier later. """

    def __init__(self, apitoken, server, port, nick, password):
        """ init method, run at class creation """
        logger.debug("Connecting to GitHub")
        self.gh = login(token=apitoken)
        logger.info("Connected to GitHub API")
        self.server = server
        self.port = port
        self.nick = nick
        self.password = password

    def get_config(self, channel, branches):
        config = {
            'notice': '0',
            'branches': branches,
            'room': channel,
            'ssl': '1',
            'no_colors': '0',
            'server': self.server,
            'nick': self.nick,
            'nickserv_password': '',
            'message_without_join': '1',
            'long_url': '0',
            'password': self.password,
            'port': self.port,
        }
        return config

    def add_hook(self, repo, channel, branches):
        config = self.get_config(channel, branches)
        logger.info("Adding IRC hook to repo {r}; config: {c}".format(
            c=config,
            r=repo.name
        ))
        hook = repo.create_hook(
            'irc',
            config,
            events=['push', 'pull_request'],
            active=True,
        )
        if hook is None:
            logger.error("Error creating hook.")
            raise SystemExit(1)
        logger.info("Added hook to repository.")

    def run(self, orgname, reponame, channel, branches):
        """ do stuff here """
        repo = self.gh.repository(orgname, reponame)
        num_hooks = 0
        for hook in repo.iter_hooks():
            num_hooks += 1
            if hook.name == 'irc':
                logger.error("ERROR: repository already has an IRC hook")
                raise SystemExit(1)
        logger.debug("Repository has %d hooks, no IRC hooks yet.", num_hooks)
        self.add_hook(repo, channel, branches)

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Add IRC notifications to a GitHub repo')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    BRANCHES_DEFAULT = ''
    p.add_argument('-b', '--branches', dest='branches', action='store',
                   default=BRANCHES_DEFAULT,
                   help='comma-separated list of branch names to notify for'
                   ' (default: %s)' % BRANCHES_DEFAULT)
    p.add_argument('-o', '--orgname', dest='orgname', action='store',
                   required=True, help='repository owner name')
    p.add_argument('-s', '--server', action='store', required=True,
                   help='IRC server hostname/IP')
    p.add_argument('-p', '--port', action='store', required=True,
                   help='IRC server port')
    p.add_argument('-n', '--nick', action='store', required=True,
                   help='IRC nick')
    p.add_argument('-P', '--password', action='store', required=True,
                   default='',
                   help='password for IRC nick (server password)')
    p.add_argument('reponame', action='store', help='repository name')
    p.add_argument('channel', action='store', help='channel name')
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
    script = GitHubIRCHooker(
        token,
        args.server,
        args.port,
        args.nick,
        args.password,
    )
    script.run(args.orgname, args.reponame, args.channel, args.branches)
