#!/usr/bin/env python
"""
github_issue_watch_pushover.py
==============================

Every time the script runs, poll GitHub for the latest comments on the specified
issues (CLI arguments). Cache the ID of the latest comment at
``~/.github_issue_watch_pushover.json``. If an issue has a new comment, notify
via Pushover.

Your GitHub API token should either be in your global (user) git config
as github.token, or in a GITHUB_TOKEN environment variable.

Your Pushover API Key and User Key must be in the ``PUSHOVER_APIKEY`` and
``PUSHOVER_USERKEY`` environment variables, respectively.

Requirements
-------------

github3.py (`pip install --pre github3.py`) >= github3.py-1.0.0a2
python-pushover (`pip install python-pushover`) == 0.2

License
--------

Copyright 2017 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/github_issue_watch_pushover.py>

CHANGELOG
----------

2017-01-05 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import os
import json
import re
from time import mktime
from github3 import login, GitHub
from pushover import init, Client

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

ISSUE_URL_RE = re.compile(
    r'^https?://github.com/([^/]+)/([^/]+)/issues/(\d+).*'
)


class GithubPushoverIssueNotifier(object):

    def __init__(self, apitoken, cache_path, pushover_apikey, pushover_userkey):
        """ init method, run at class creation """
        logger.debug("Connecting to GitHub")
        self._gh = login(token=apitoken)
        logger.info("Connected to GitHub API")
        self._cache_path = os.path.abspath(os.path.expanduser(cache_path))
        self._cache = self._get_cache()
        self._pushover = Client(pushover_userkey, api_token=pushover_apikey)
        logger.info('Connected to Pushover for user %s', pushover_userkey)

    def _get_cache(self):
        logger.debug('Reading state cache from: %s', self._cache_path)
        if not os.path.exists(self._cache_path):
            logger.debug('State cache does not exist.')
            return {}
        with open(self._cache_path, 'r') as fh:
            raw = fh.read()
        cache = json.loads(raw)
        logger.debug('State cache: %s', cache)
        return cache

    def _write_cache(self):
        logger.debug('Writing state cache to: %s', self._cache_path)
        with open(self._cache_path, 'w') as fh:
            fh.write(json.dumps(self._cache))
        logger.debug('State written.')

    def run(self, issues):
        """check the issues, notify if needed"""
        logger.info('Checking issues: %s', [i['url'] for i in issues])
        for i in issues:
            try:
                self._do_issue(i['user'], i['repo'], i['num'], i['url'])
            except Exception:
                logger.error('Unable to get issue %s/%s #%d', user,
                             repo, num, exc_info=True)
        logger.debug('Done with issues.')
        self._write_cache()

    def _send(self, title, body):
        logger.debug('Sending via pushover: title="%s" body="%s"', title, body)
        try:
            self._pushover.send_message(body, title=title)
        except Exception:
            logger.error('Error sending Pushover notification', exc_info=True)

    def _do_issue(self, user, repo, num, url):
        logger.debug('Checking issue: %s/%s #%d', user, repo, num)
        issue = self._gh.issue(user, repo, num)
        closed = issue.is_closed()
        num_comments = 0
        for comment in issue.comments():
            num_comments += 1
        updated = mktime(issue.updated_at.timetuple())
        logger.debug('Issue %s/%s #%d: closed=%s, %d comments, updated at %s',
                     user, repo, num, closed, num_comments, updated)
        if url not in self._cache:
            logger.info('Issue %s/%s %#d not in cache yet', user, repo, num)
            self._cache[url] = {
                'closed': closed,
                'num_comments': num_comments,
                'updated': updated
            }
            return
        cached = self._cache[url]
        logger.debug('Cached issue info: %s', cached)
        msg = None
        if closed != cached['closed']:
            logger.debug('closed status has changed from %s to %s',
                         cached['closed'], closed)
            if closed:
                msg = 'closed'
            else:
                msg = 'reopened'
        elif num_comments != cached['num_comments']:
            logger.debug('num_comments has changed from %d to %d',
                         cached['num_comments'], num_comments)
            msg = 'has %d new comments' % (
                num_comments - cached['num_comments']
            )
        elif updated != cached['updated']:
            logger.debug('updated has changed from %s to %s',
                         cached['updated'], updated)
            msg = 'updated'
        if msg is None:
            logger.debug('No changes for issue %s/%s #%d', user, repo, num)
            return
        title = 'GitHub issue %s/%s #%d %s' % (
            user, repo, num, msg
        )
        self._send(title, url)
        self._cache[url] = {
            'closed': closed,
            'num_comments': num_comments,
            'updated': updated
        }


def parse_args(argv):
    """
    parse arguments/options
    """
    p = argparse.ArgumentParser(
        description='Notify for GitHub issues via Pushover'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-c', '--cache_path', dest='cache_path', action='store',
                   default='~/.github_issue_watch_pushover.json',
                   help='path to JSON state cache')
    p.add_argument('ISSUE_URL', nargs='+',
                   help='GitHub issue URL (can be specified multiple times)')
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

def parse_issue_url(url):
    m = ISSUE_URL_RE.match(url)
    if not m:
        raise RuntimeError("ERROR: Issue URL '%s' does not match issue URL "
                           "regex: %s" % (url, ISSUE_URL_RE.pattern))
    return {
        'url': url,
        'user': m.group(1),
        'repo': m.group(2),
        'num': int(m.group(3))
    }


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    # set logging
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    # get token and API keys
    try:
        token = os.environ['GITHUB_TOKEN']
        logger.debug("Using API token from GITHUB_TOKEN environment variable")
    except KeyError:
        token = get_api_token()
        logger.debug("Using API token from git config 'github.token'")
    try:
        p_api = os.environ['PUSHOVER_APIKEY']
    except KeyError:
        raise RuntimeError("Error: PUSHOVER_APIKEY env var not set")
    try:
        p_user = os.environ['PUSHOVER_USERKEY']
    except KeyError:
        raise RuntimeError("Error: PUSHOVER_USERKEY env var not set")
    # parse issue URLs
    issues = []
    for url in args.ISSUE_URL:
        issues.append(parse_issue_url(url))
    # run
    script = GithubPushoverIssueNotifier(token, args.cache_path, p_api, p_user)
    script.run(issues)
