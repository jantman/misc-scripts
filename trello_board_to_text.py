#!/usr/bin/env python
"""
trello_board_to_text.py - Print to STDOUT the names of the columns on the
    specified trello board and the titles of the cards in that column in order.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/trello_board_to_text.py>

Copyright 2023 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

REQUIREMENTS:
trello package
"""

import sys
import os
import logging
import argparse
from collections import defaultdict

try:
    from trello import TrelloApi
except ImportError:
    sys.stderr.write(
        "trello package not found; please 'pip install trello'\n"
    )
    raise SystemExit(1)

logger = logging.getLogger(__name__)

# suppress logging from requests, used internally by TrelloApi
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)
requests_log.propagate = True


class TrelloBoardToText:

    board_get_kwargs = {
        'cards': 'visible',
        'card_fields': 'all',
        'lists': 'all',
        'list_fields': 'all',
        'labels': 'all',
    }

    def __init__(self):
        """get credentials and connect"""
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

    def run(self, board_name):
        """main entry point"""
        board_id = self.get_board_id(board_name)
        board = self.trello.boards.get(board_id, **self.board_get_kwargs)
        cards_per_col = defaultdict(list)
        for card in board['cards']:
            if card['closed']:
                continue
            cards_per_col[card['idList']].append(card)
        for column in sorted(board['lists'], key=lambda x: x['pos']):
            if column['closed']:
                continue
            print(f"\n* {column['name']}\n")
            for card in sorted(
                cards_per_col[column['id']], key=lambda x: x['pos']
            ):
                print(f'{card["name"]}')

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
    """
    p = argparse.ArgumentParser(
        description='Script print all columns and cards on a Trello board '
                    'to STDOUT'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('BOARD_NAME', type=str, help='board name')
    return p.parse_args(argv)


if __name__ == "__main__":
    FORMAT = ("[%(levelname)s %(filename)s:%(lineno)s - "
              "%(funcName)20s() ] %(message)s")
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    logger = logging.getLogger()
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    TrelloBoardToText().run(args.BOARD_NAME)
