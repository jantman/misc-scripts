#!/usr/bin/env python
"""
trello_copy_checklist.py - Script to copy a checklist from one Trello card
to another.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/trello_copy_checklist.py>

Copyright 2018 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

REQUIREMENTS:
`requests` (pip install requests)

CHANGELOG:
2018-04-30 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import logging
import argparse
import requests
import re

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger()

# suppress logging from requests, used internally by TrelloApi
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)
requests_log.propagate = True


class TrelloCopyChecklist():

    def __init__(self):
        """get credentials and connect"""
        self._app_key = os.environ.get('TRELLO_APP_KEY', None)
        if self._app_key is None:
            raise SystemExit('Please export your Trello application key as the '
                             'TRELLO_APP_KEY environment variable.')
        self._token = os.environ.get('TRELLO_TOKEN', None)
        if self._token is None:
            raise SystemExit('Please export your Trello API token as the '
                             'TRELLO_TOKEN environment variable.')

    def run(self, source_url, checklist_name, dest_url):
        """main entry point"""
        src_id = self._get_card_id_from_url(source_url)
        dest_id = self._get_card_id_from_url(dest_url)
        logger.info(
            'source card ID: %s destination card ID: %s', src_id, dest_id
        )
        checklists = self._get_card_checklists(src_id)
        clist = None
        for l in checklists:
            if l['name'] == checklist_name:
                clist = l
                break
        if clist is None:
            raise RuntimeError(
                'ERROR: No checklist named "%s" found on card %s' % (
                    checklist_name, src_id
                )
            )
        logger.debug('Source checklist: %s', clist)
        logger.info('Found source checklist with ID: %s', clist['id'])
        res = requests.post(
            'https://api.trello.com/1/cards/%s/checklists?name=%s&'
            'idChecklistSource=%s&bos=bottom&key=%s&token=%s' % (
                dest_id, checklist_name, clist['id'], self._app_key, self._token
            )
        )
        res.raise_for_status()
        resp = res.json()
        logger.info('Created checklist ID %s', resp['id'])

    def _get_card_checklists(self, card_id):
        logger.debug('GET checklists for card ID %s', card_id)
        res = requests.get(
            'https://api.trello.com/1/cards/%s/checklists?key=%s&token=%s' % (
                card_id, self._app_key, self._token
            )
        )
        res.raise_for_status()
        j = res.json()
        logger.debug('Response JSON: %s', j)
        return j

    def _get_card_id_from_url(self, url):
        parsed = urlparse(url)
        m = re.match(r'^/c/([^/]+)/.*', parsed.path)
        if not m:
            raise RuntimeError('ERROR: Invalid card URL: %s', url)
        return m.group(1)


def parse_args(argv):
    """
    parse arguments/options
    """
    p = argparse.ArgumentParser(
        description='Script to copy checklist from one Trello card to another.')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('SOURCE_CARD_URL', action='store', type=str,
                   help='URL to source Trello card')
    p.add_argument('CHECKLIST_NAME', action='store', type=str,
                   help='name of checklist to copy')
    p.add_argument('DEST_CARD_URL', action='store', type=str,
                   help='URL to destination Trello card')

    args = p.parse_args(argv)
    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    script = TrelloCopyChecklist()
    script.run(args.SOURCE_CARD_URL, args.CHECKLIST_NAME, args.DEST_CARD_URL)
