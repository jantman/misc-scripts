#!/usr/bin/env python
"""
sync_git_clones.py
-------------------

NOTICE - 2014-04-26 I got this script to this point, and then found that a known bug in
GitPython (https://github.com/gitpython-developers/GitPython/issues/28) prevents
it from fetching *any* repository that has a remote configured with a non-branch,
non-tag refspec, such as the ones used by GitHub (refs/pull/*/head) to check
out pull requests. As such, this is unusable to me until this issue is fixed.
I have enough projects in progress, I can't devote the time to trying to fix
this issue in GitPython correctly. So, this is going to sit here, partially
finished, until the issue is fixed.

A script to keep your git clones (in a specified list of directories) in sync
with origin and optionally upstream, and optionally to keep origin's master
branch in sync with upstream.

Main Features
=============

* Fail/exit if one of a list of shell commands fail (use to ensure that ssh-agent
  must be running, VPN connection must be up, etc.)
* Operate on all git repos in specified directories (REPO_DIRS) non-recursively
* Fetch origin for each git repo found
* Optionally switch to master branch and pull (controlled globally via ENABLE_PULL
  and per-repo via REPO_OPTIONS)
* If using github API (see below):
  * Add fetch refs to fetch PRs as branches.
  * If the repo is a fork, add a remote for the upstream (parent). Optionally, pull
    master on the upstream and push back to origin (keep origin master in sync with
    upstream).

Warnings / ToDo
===============

* GitPython 0.3.2 fails with a TypeError (Cannot handle reference type: "'refs/pull/1/head'")
  on any GitHub repos that are setup to check out PRs as branches (i.e. as described
  in: https://help.github.com/articles/checking-out-pull-requests-locally). I'm working on
  a PR to fix this, but until then... caveat emptor.

Requirements
============

Unfortunately this only works with python2, as GitPython (its gitdb package) does
not yet support python3. All efforts have been made to keep everything within this
script ready for python3 once GitPython chooses to support it.

No, this isn't a real Python package. You should run it from a virtualenv with these
requirements (feel free to ``pip isntall`` them as seen here):

* GitPython==0.3.2.RC1
* githup3.py>=0.8.2 (if using GitHub integration; tested with 0.8.2)

Configuration
=============

Configuration is stored as JSON, in a text configuration file at
``~/.sync_git_clones.conf.py`` by default. Running this script without an existing
configuration file and with the ``-g`` option will cause it to write a sample config
file to disk, for you to edit.

The configuration file supports the following keys:
* __gitdirs__ - (list of strings) a list of directories to search _non_-recursively for
  git directories/clones. These will be passed through os.path.expanduser and
  os.pathabspath before being used.
* __skipdirty__ - (boolean) If true, skip past dirty repos and log an error.
* __only_fetch_origin__ - (boolean) If true, only fetch a remote called "origin".
  Otherwise, fetch all remotes.
* __github__ - (boolean) whether to enable GitHub API integration.

If you want to use the GitHub API integration, you should have an API key/token available.
This script will parse ~/.gitconfig using the ConfigParser module, looking for github.token
as explained in the [Local GitHub Config blog post](https://github.com/blog/180-local-github-config).

Changelog
=========
2014-04-26 jantman (Jason Antman) <jason@jasonantman.com>
- initial version

"""

import optparse
import sys
import logging
import os.path
import json
import git

# prefer the pip vendored pkg_resources
try:
    from pip._vendor import pkg_resources
except ImportError:
    import pkg_resources

logging.basicConfig(level=logging.WARNING, format="[%(levelname)s %(filename)s:%(lineno)s - %(funcName)s() ] %(message)s")
logger = logging.getLogger(__name__)

def fetch_remote(rmt, dryrun=False):
    """ fetch a remote """
    if dryrun:
        logger.info("DRYRUN - would fetch rmt %s" % rmt.name)
    else:
        print("fetching remote %s" % rmt.name)
        rmt.fetch()
    return True

def do_git_dir(path, config, gh_client=None, dryrun=False):
    """
    operate on a single git directory/clone
    :param path: path to the clone
    :type path: string
    :param config: config dict
    :type config: dict
    :param gh_client: a GitHub API client object (TODO)
    :type gh_client: TODO
    :param dryrun: if true, do not change anything; log actions that would be taken
    :type dryrun: boolean
    """
    logger.info("doing gitdir %s" % path)
    repo = git.Repo(path)
    if repo.bare:
        logger.warining("Skipping bare repo: %s" % path)
        return False
    if repo.is_dirty():
        if config['skipdirty']:
            logger.error("Skipping dirty repo: %s" % path)
            return False
        else:
            raise SystemExit("TODO: implement what to do with dirty repos")
    # ok, repo isn't bare or dirty
    current_branch = repo.active_branch
    logger.debug("current branch is %s" % current_branch)

    on_github = False
    for rmt in repo.remotes:
        if 'github.com' in rmt.url:
            on_github = True

    if on_github:
        # TODO - guard this with a config setting?
        do_github_repo(repo, config, gh_client, dryrun=False)

    for rmt in repo.remotes:
        if rmt.name != 'origin' and config['only_fetch_origin']:
            logger.debug("skipping remote %s - only_fetch_origin" % rmt.name)
            continue
        fetch_remote(rmt, dryrun=dryrun)
        if 'github.com' in rmt.url:
            on_github = True

    # guard with config setting TODO
    # if branch is not master, switch to master; pull; switch back to original branch

    return True

def do_github_repo(repo, config, gh_client, dryrun=False):
    """
    operate on a single git directory/clone of a GitHub repo
    :param repo: a GitPython Repository object, passed in from do_git_dir
    :type path: Repository
    :param config: config dict
    :type config: dict
    :param gh_client: TODO
    :param dryrun: if true, do not change anything; log actions that would be taken
    :type dryrun: boolean
    """
    raise SystemExit("Do GitHub stuff here")

def get_github_client(config, dryrun=False):
    """ read API key from git config and return a <TODO> github client instance """
    # `git config --global github.token` and trim that, make sure it's 40 characters

    # try to instantiate API client, and connect
    # return client object
    return None

def main(configpath='~/.sync_git_clines.conf.py', dryrun=False, genconfig=False):
    """
    main entry point

    :param config: path to configuration file
    :type config: string
    :param dryrun: if true, do not change anything; log actions that would be taken
    :type dryrun: boolean
    :param genconfig: if config file does not exist, write a sample one and exit
    :type genconfig: boolean
    """
    logger.debug("main called with config=%s" % configpath)
    if dryrun:
        logger.warning("dryrun=True - no changes will actually be made")
    configpath = os.path.abspath(os.path.expanduser(configpath))
    logger.debug("config expanded to '%s'" % configpath)

    if not os.path.exists(configpath):
        logger.debug("config file does not exist")
        if genconfig:
            logger.debug("generating sample config file")
            generate_config(configpath, dryrun=dryrun)
            raise SystemExit("Sample configuration file written to: %s" % configpath)
        else:
            raise SystemExit("ERROR: configuration file does not exist. Run with -g|--genconfig to write a sample config at %s" % configpath)

    # attempt to read JSON config
    config = load_config(configpath)
    logger.debug("config loaded")

    if config['github']:
        gh_client = get_github_client(config, dryrun=dryrun)
    else:
        gh_client = None
        logger.info("github integration disabled by config")

    git_dirs = get_git_dirs(config)
    logger.info("found %d git directories" % len(git_dirs))
    for d in git_dirs:
        do_git_dir(d, config, gh_client=gh_client, dryrun=dryrun)

def get_git_dirs(config):
    """ get a list of all git directories to examine """
    logger.debug("finding git directories")
    gitdirs = []
    for d in config['gitdirs']:
        d = os.path.abspath(os.path.expanduser(d))
        logger.debug("checking %s" % d)
        for name in os.listdir(d):
            path = os.path.join(d, name)
            if os.path.isdir(path) and os.path.isdir(os.path.join(path, '.git')):
                if path in gitdirs:
                    logger.debug("found git dir but already in list: %s" % path)
                else:
                    logger.debug("found git dir: %s" % path)
                    gitdirs.append(path)
    return gitdirs

def check_versions():
    """
    checks that requirements have supported versions

    this is mainly needed for GitPython, where we rely on features
    in the heavily-rewritten 0.3.2RC1 version, which is marked as
    beta / RC. ``pip install GitPython`` currently yields 0.1.7, which
    is utterly useless.

    thanks to @qwcode for this simple logic
    """
    gp_req_str = 'GitPython>=0.3.2.RC1'
    gp_req = pkg_resources.Requirement.parse(gp_req_str)
    gp_dist = pkg_resources.get_distribution('GitPython')
    logger.debug("Checking GitPython requirement")
    if gp_dist not in gp_req:
        raise SystemExit("ERROR: sync_git_clones.py requires %s" % gp_req_str)
    logger.debug("All requirements satisfied")
    return True

def load_config(configpath):
    """ load the configuration file at configpath """
    logger.debug("loading config from %s" % configpath)
    with open(configpath, 'r') as fh:
        configstr = fh.read()
    config = json.loads(configstr)

    # apply defaults
    defaults = {'skipdirty': True, 'only_fetch_origin': False}
    for k in defaults:
        if k not in config:
            logger.debug("applying default config value for %s" % (k))
            config[k] = defaults[k]
    return config

def generate_config(configpath, dryrun=False):
    """ Write out a sample config file. """
    config = {'gitdirs': ['~/GIT', '/path/to/dir'],
              'skipdirty': True,
              'github': True,
              }
    logger.debug("serializing sample config")
    configstr = json.dumps(config, sort_keys=True, indent=4, separators=(',', ': '))
    logger.debug("writing serialized sample config to %s" % configpath)
    if dryrun:
        logger.info("DRYRUN: would have written to %s: \n%s" % (path, configstr))
    else:
        with open(configpath, 'w') as fh:
            fh.write(configstr)
        logger.debug("sample config written")
    return True

def parse_args(argv):
    """ parse arguments with OptionParser """
    parser = optparse.OptionParser()

    parser.add_option('-c', '--config', dest='config', action='store', type='string',
                      default='~/.sync_git_clones.conf.py',
                      help='JSON config file location (default: ~/.sync_git_clones.conf.py)')

    parser.add_option('-t', '--test', dest='test', action='store_true', default=False,
                      help='test / dry-run - do not take any action, print what would be done')

    parser.add_option('-v', '--verbose', dest='verbose', action='count',
                      help='verbose output on what actions are being taken. Specify twice for debug-level output.')

    parser.add_option('-g', '--gen-config', dest='genconfig', action='store_true', default=False,
                      help='if config file does not exist, generate a sample one and exit')

    options, args = parser.parse_args(argv)
    return options

if __name__ == "__main__":
    opts = parse_args(sys.argv)
    if opts.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif opts.verbose == 1:
        logger.setLevel(logging.INFO)
    check_versions()
    main(configpath=opts.config, dryrun=opts.test, genconfig=opts.genconfig)
