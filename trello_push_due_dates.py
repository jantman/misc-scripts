#!/usr/bin/env python
"""
trello_push_due_dates.py - Script to push all due dates on a Trello board
(optionally in one list) back by N days.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/trello_push_due_dates.py>

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

REQUIREMENTS:
trello and python-dateutil distributions

CHANGELOG:
2016-07-09 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import logging
import argparse
from datetime import timedelta

try:
    from trello import TrelloApi
except ImportError:
    sys.stderr.write(
        "trello distribution not found; please 'pip install trello'\n"
    )
    raise SystemExit(1)

try:
    from dateutil import parser
except ImportError:
    sys.stderr.write(
        "dateutil distribution not found; please 'pip install python-dateutil'\n"
    )
    raise SystemExit(1)

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger()

# suppress logging from requests, used internally by TrelloApi
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)
requests_log.propagate = True


class TrelloDatePusher:

    board_get_kwargs = {
        'cards': 'visible',
        'card_fields': 'all',
        'lists': 'all',
        'list_fields': 'all',
    }

    def __init__(self, dry_run=False):
        """get credentials and connect"""
        self.dry_run = dry_run
        app_key = os.environ.get('TRELLO_APP_KEY', None)
        if app_key is None:
            raise SystemExit('Please export your Trello application key as the '
                             'TRELLO_APP_KEY environment variable.')
        token = os.environ.get('TRELLO_TOKEN', None)
        if token is None:
            raise SystemExit('Please export your Trello API token as the '
                             'TRELLO_TOKEN environment variable.')
        logger.debug('Initializing TrelloApi')
        self.trello = TrelloApi(app_key, token)
        logger.debug('TrelloApi initialized')

    def run(self, board_name, num_days, list_name=None):
        """main entry point"""
        td = timedelta(days=num_days)
        board_id = self.get_board_id(board_name)
        board = self.trello.boards.get(board_id, **self.board_get_kwargs)
        list_id = self.id_for_list(board, list_name)
        cards = self.filter_cards(board['cards'], list_id)
        success = 0
        for card in cards:
            res = self.update_card_date(card['id'], card['due'], td)
            if res:
                success += 1
        logger.warning('Successfully updated due dates on %d of %d cards',
                       success, len(cards))

    def update_card_date(self, card_id, orig_due, time_delta):
        """update the due date on a card"""
        dt = parser.parse(orig_due)
        new_dt = dt + time_delta
        new_due = new_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        logger.debug('Updating card %s: original due=%s, new due=%s',
                     card_id, orig_due, new_due)
        if self.dry_run:
            logger.warning(
                'DRY RUN: would call: self.trello.cards_update_due(%s, %s)',
                card_id, new_due)
            return False
        res = self.trello.cards.update_due(card_id, new_due)
        if res['id'] != card_id:
            logger.error(
                'ERROR: update operation on card %s returned API response '
                'containing wrong card_id (%s)', card_id, res['id'])
            return False
        if res['due'] != new_due:
            logger.error(
                'ERROR: update operation on card %s returned API response '
                'with due of "%s" instead of "%s"', card_id, res['due'],
                new_due)
            return False
        logger.warning('Card %s ("%s") successfully updated.', res['id'],
                       res['name'])
        return True

    def filter_cards(self, orig_cards, list_id):
        """filter cards to ones with a due date, and if list_id is not None,
        also in the specified list"""
        cards = []
        logger.debug('Filtering %d cards on board', len(orig_cards))
        for card in orig_cards:
            if card['due'] is None:
                logger.debug('Skipping card %s without due date', card['id'])
                continue
            if list_id is not None and list_id != card['idList']:
                logger.debug('Skipping card %s in wrong list', card['id'])
                continue
            cards.append(card)
        logger.info('Identified %d cards to update', len(cards))
        return cards

    def id_for_list(self, board, list_name):
        """get the ID for a list with the given name, on the board"""
        if list_name is None:
            logger.debug('No list name specified; skipping list filter')
            return None
        logger.debug('Board has %d lists', len(board['lists']))
        for l in board['lists']:
            if l['name'] == list_name:
                logger.info('Found list "%s" id=%s', list_name, l['id'])
                return l['id']
        raise SystemExit('Error: could not find a list with name "%s" on board '
                         '%s', list_name, board['name'])

    def get_board_id(self, board_name):
        """get the ID for a board name"""
        logger.debug('Getting boards')
        boards = self.trello.members.get_board('me')
        logger.debug('Found %d boards', len(boards))
        for b in boards:
            if b['name'] == board_name:
                logger.info('Board "%s" id=%s', board_name, b['id'])
                return b['id']
        raise SystemExit('Error: could not find board with name "%s"',
                         board_name)


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(
        description='Script to push all due dates on a Trello board '
                    '(optionally in one list) back by N days.'
    )
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-l', '--list', dest='list_name', action='store', type=str,
                   help='Only change cards in list with this name')
    p.add_argument('BOARD_NAME', action='store', type=str,
                   help='board name to update')
    p.add_argument('NUM_DAYS', action='store', type=int,
                   help='Number of days to add to due dates')

    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    script = TrelloDatePusher(dry_run=args.dry_run)
    script.run(args.BOARD_NAME, args.NUM_DAYS, list_name=args.list_name)
