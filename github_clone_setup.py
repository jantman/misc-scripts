#!/usr/bin/env python
"""
github_clone_setup.py
---------------------

Simple script to use on clones of GitHub repositories. Sets fetch refs for pull
requests and, if `git config --global github.token` returns a valid API token,
sets an 'upstream' remote if the repository is a fork.

Note - I *was* going to use ConfigParser to interact with .git/config instead
of shelling out like a bad person. Then I found that ConfigParser barfs on any
lines with leading space, like .git/config. Oh well. I can't fix *every* upstream
bug.

The canonical version of this script lives at:
https://github.com/jantman/misc-scripts/blob/master/github_clone_setup.py

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

Requirements
============
* Python 2.7+ (uses subprocess.check_output)
* github3.py>=0.8.2 (if using GitHub integration; tested with 0.8.2)

Changelog
=========
2014-04-27 jantman (Jason Antman) <jason@jasonantman.com>
- initial version

"""

import sys
import os.path
import subprocess
import optparse
import re

from github3 import login, GitHub

def get_api_token():
    """ get GH api token """
    apikey = subprocess.check_output(['git', 'config', '--global', 'github.token']).strip()
    if len(apikey) != 40:
        raise SystemExit("ERROR: invalid github api token from `git config --global github.token`: '%s'" % apikey)
    return apikey


def get_config_value(confpath, key):
    """ gets a git config value using `git config` """
    output = subprocess.check_output(['git', 'config', '--file=%s' % confpath, '--get-all', '%s' % key])
    return output


def add_config_value(confpath, key, value):
    """ adds a git config value using `git config` """
    cmd = ['git', 'config', '--file=%s' % confpath, '--add', '%s' % key, value]
    output = subprocess.check_output(cmd)
    print(" ".join(cmd))
    return output


def get_remotes(confpath, gitdir):
    """ list all remotes for a repo """
    remotes_str = subprocess.check_output(['git', '--work-tree=%s' % gitdir, '--git-dir=%s' % (os.path.join(gitdir, '.git')), 'remote'])
    remotes = remotes_str.splitlines()
    return remotes


def set_pull_fetches(confpath, gitdir, remotes):
    """ set fetch refs for pulls if not already there """
    for rmt in remotes:
        fetches_str = get_config_value(confpath, 'remote.%s.fetch' % rmt)
        fetches = fetches_str.splitlines()
        pull_fetch = '+refs/pull/*/head:refs/pull/%s/*' % rmt
        if pull_fetch not in fetches:
            add_config_value(confpath, 'remote.%s.fetch' % rmt, pull_fetch)
    return True


def get_owner_reponame_from_url(url):
    """
    parse a github repo URL into (owner, reponame)

    patterns:
    git@github.com:jantman/misc-scripts.git
    https://github.com/jantman/misc-scripts.git
    http://github.com/jantman/misc-scripts.git
    git://github.com/jantman/misc-scripts.git
    """
    m = re.match(r'^.+[/:]([^/]+)/([^/\.]+)(\.git)?$', url)
    if not m:
        raise SystemExit("ERROR: unable to parse URL '%s'" % url)
    if len(m.groups()) < 3:
        raise SystemExit("ERROR: unable to parse URL '%s'" % url)
    return (m.group(1), m.group(2))


def setup_upstream(confpath, gitdir):
    """ use GH API to find parent/upstream, and set remote for it """
    # see if upstream is set
    try:
        upstream = get_config_value(confpath, 'remote.upstream.url')
        return True
    except subprocess.CalledProcessError:
        pass
    origin_url = get_config_value(confpath, 'remote.origin.url')
    (owner, reponame) = get_owner_reponame_from_url(origin_url)
    apikey = get_api_token()
    gh = login(token=apikey)
    repo = gh.repository(owner, reponame)
    if repo.fork:
        upstream_url = repo.parent.ssh_url
        cmd = ['git', '--work-tree=%s' % gitdir, '--git-dir=%s' % (os.path.join(gitdir, '.git')), 'remote', 'add', 'upstream', upstream_url]
        subprocess.check_call(cmd)
        print(" ".join(cmd))
    return True


def is_github_repo(confpath, gitdir):
    """ return true if this repo origin is on GitHub, False otherwise """
    origin_url = get_config_value(confpath, 'remote.origin.url')
    if 'github.com' in origin_url:
        return True
    return False


def main(gitdir):
    """ main entry point """
    gitdir = os.path.abspath(os.path.expanduser(gitdir))
    if not os.path.exists(gitdir):
        raise SystemExit("ERROR: path does not exist: %s" % gitdir)
    confpath = os.path.join(gitdir, '.git', 'config')
    if not os.path.exists(confpath):
        raise SystemExit("ERROR: does not appear to be a valid git repo - path does not exist: %s" % confpath)

    if not is_github_repo(confpath, gitdir):
        raise SystemExit("%s is not a clone of a github repo" % gitdir, 0)

    remotes = get_remotes(confpath, gitdir)
    if 'upstream' not in remotes:
        setup_upstream(confpath, gitdir)
    remotes = get_remotes(confpath, gitdir)
    if 'upstream' not in remotes:
        raise SystemExit("Error: upstream not successfully added to remotes")

    set_pull_fetches(confpath, gitdir, remotes)


def parse_args(argv):
    """ parse arguments with OptionParser """
    parser = optparse.OptionParser(usage='github_clone_setup.py -d <path to clone>')

    parser.add_option('-d', '--dir', dest='gitdir', action='store', type='string',
                      help='path to the local clone of the repository')

    options, args = parser.parse_args(argv)
    return (options, args)


if __name__ == "__main__":
    opts, args = parse_args(sys.argv)
    main(opts.gitdir)
