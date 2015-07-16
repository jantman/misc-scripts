#!/usr/bin/env python
"""
gitlab_ssh_key_sync.py
=======================

Script to sync your ~/.ssh/authorized_keys to a GitLab instance.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/gitlab_ssh_key_sync.py>

Usage
-----

1. Export your GitLab Private API token as GITLAB_TOKEN, or you will be prompted
   for it interactively.
2. Run the script:

    gitlab_ssh_key_sync.py http://gitlab.example.com

Requirements
-------------

python-gitlab (tested with 0.9.2; `pip install python-gitlab`)

Copyright and License
----------------------

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

Changelog
----------

2015-07-15 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import gitlab
import os

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger(__name__)

# suppress requests internal logging
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)
requests_log.propagate = True


class GitLabSSHKeySync:
    """sync local ssh authorized_keys to GitLab"""

    def __init__(self, url, apikey, dry_run=False):
        """connect to GitLab"""
        self.dry_run = dry_run
        logger.debug("Connecting to GitLab")
        self.conn = gitlab.Gitlab(url, apikey)
        self.conn.auth()
        logger.info("Connected to GitLab as %s",
                    self.conn.user.username)

    def run(self, keyfile):
        """main entry point"""
        keys = self._parse_authorized_keys(keyfile)
        gitlab_keys = self.conn.user.Key()
        existing_keys = [
            self._parse_key_line(k.key, 0)['key'] for k in gitlab_keys
        ]
        user_id = self.conn.user.id
        logger.info("Syncing %d keys for user %s (%s)",
                    len(keys),
                    self.conn.user.username,
                    user_id)
        added = 0
        failed = 0
        for key in keys:
            if key['key'] in existing_keys:
                logger.info("Key from line %d (%s) already present for your "
                            "user",
                            key['line_num'],
                            key['comment']
                )
                continue
            logger.debug("Adding key from line %d: %s",
                         key['line_num'],
                         key['raw'])
            k = gitlab.UserKey(
                self.conn,
                data={
                    'user_id': user_id,
                    'title': key['comment'],
                    'key': key['raw'],
                }
            )
            if self.dry_run:
                logger.warning("Dry Run - not saving key", str(k))
                continue
            try:
                res = k.save()
                existing_keys.append(key['key'])
                added += 1
            except gitlab.GitlabCreateError as ex:
                failed += 1
                if (
                        ex.response_code != 400 or
                        (
                            (
                                'key' not in ex.error_message or
                                ex.error_message['key'][0] != 'has already been'
                                ' taken'
                            )
                            and
                            (
                                'fingerprint' not in ex.error_message or
                                ex.error_message['fingerprint'][0] != 'has '
                                'already been taken'
                            )
                        )
                ):
                    raise ex
                logger.error("ERROR: key on line %d (%s) is already in use by "
                             "another user.",
                             key['line_num'],
                             key['comment'])
                continue
        logger.info("Added %d keys for user %s (%s); %d keys failed to add",
                    added,
                    self.conn.user.username,
                    user_id,
                    failed
        )

    def _parse_authorized_keys(self, fpath):
        """parse authorized_keys file into a list"""
        fpath = os.path.abspath(os.path.expanduser(fpath))
        logger.debug("Reading authorized keys from %s", fpath)
        keys = []
        with open(fpath, 'r') as fh:
            lnum = 1
            for line in fh.readlines():
                line = line.strip()
                if line.startswith('#') or line == '':
                    logger.debug("Ignoring line %d (non-key line)", lnum)
                else:
                    keys.append(self._parse_key_line(line, lnum))
                lnum += 1
        logger.info("Read %d keys from %s", len(keys), fpath)
        return keys

    def _parse_key_line(self, line, lineno):
        parts = line.split(' ')
        if len(parts) == 4:
            # discard options
            parts = parts[1:]
        if len(parts) != 3:
            raise ValueError("Key on line %d appears invalid" % lineno)
        res = {
            'raw': line,
            'line_num': lineno,
            'keytype': parts[0],
            'key': parts[1],
            'comment': parts[2],
        }
        return res

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Script to sync your '
                                '~/.ssh/authorized_keys to a GitLab instance.')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False,
                   help='verbose output')
    p.add_argument('gitlab_url', action='store',
                   help='URL to GitLab instance')
    p.add_argument('-f', '--key-file', action='store', dest='key_file',
                   default='~/.ssh/authorized_keys',
                   help='read authorized keys from a file other than '
                   '~/.ssh/authorized_keys')

    args = p.parse_args(argv)

    return args

def get_api_key():
    if 'GITLAB_TOKEN' in os.environ:
        return os.environ['GITLAB_TOKEN']
    return raw_input("Enter your GitLab Private API token: ")

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    syncer = GitLabSSHKeySync(
        args.gitlab_url,
        get_api_key(),
        dry_run=args.dry_run
    )
    syncer.run(args.key_file)
