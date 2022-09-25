#!/usr/bin/env python
"""
trello_ensure_card.py - Script to ensure that a card with the given title (and
optionally other attributes) exists in the specified column of the specified
board.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/trello_ensure_card.py>

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

REQUIREMENTS:
trello and python-dateutil distributions

CHANGELOG:
2019-08-24 Jason Antman <jason@jasonantman.com>:
  - add -C/--checklist option to support adding checklists to cards
2019-01-05 Jason Antman <jason@jasonantman.com>:
  - add -D/--description to support adding description on new cards (only)
2016-12-03 Jason Antman <jason@jasonantman.com>:
  - add -p/--position to support adding card at top or bottom of list
2016-10-15 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import logging
import argparse
from datetime import timedelta
import requests

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

logger = logging.getLogger(__name__)

# suppress logging from requests, used internally by TrelloApi
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)
requests_log.propagate = True


class TrelloEnsureCard:

    board_get_kwargs = {
        'cards': 'visible',
        'card_fields': 'all',
        'lists': 'all',
        'list_fields': 'all',
        'labels': 'all',
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

    def run(self, card_title, list_name, board_name, labels=[], pos='bottom',
            desc=None, checklist_names=[]):
        """main entry point"""
        board_id = self.get_board_id(board_name)
        board = self.trello.boards.get(board_id, **self.board_get_kwargs)
        card_labels = self.labels_list(board, labels)
        list_id = self.id_for_list(board, list_name)
        cards = self.filter_cards(board['cards'], list_id)
        desired_card = None
        for card in cards:
            if card['name'] == card_title:
                desired_card = card
                break
        if desired_card is None:
            logger.debug("Adding card '%s' to list" % card_title)
            if self.dry_run:
                logger.warning("DRY RUN: would add card. dry run, so exiting")
                return
            desired_card = self.new_card(name=card_title, idList=list_id,
                                         pos=pos, desc=desc)
            logger.info(
                "Added card '%s' (%s <%s>) to list; position: %s",
                desired_card['name'], desired_card['id'], desired_card['url'],
                pos
            )
        else:
            logger.info("Found desired card '%s' (%s; <%s>) in list",
                        desired_card['name'], desired_card['id'],
                        desired_card['url'])
        if len(card_labels) > 0:
            self.ensure_card_labels(desired_card, card_labels)
        if len(checklist_names) > 0:
            self.ensure_card_checklists(desired_card, checklist_names)

    def new_card(self, **kwargs):
        """
        Wrapper around trello.cards.new because 0.9.1 on PyPI doesn't have a
        position argument (even though the source repo does...)

        :param name: card title
        :type name: str
        :param idList: list ID
        :type idList: str
        :param desc: card description
        :type desc: str
        :param pos: position, "top", "bottom", or a positive number
        :type pos: ``int`` or ``str``
        :param desc: card description
        :type desc: str
        """
        c = self.trello.cards
        resp = requests.post(
            "https://trello.com/1/cards" % (),
            params=dict(key=c._apikey, token=c._token),
            data=kwargs)
        resp.raise_for_status()
        return resp.json()

    def labels_list(self, board, labels):
        """
        Given a list of label names, return a corresponding list of the label
        IDs for the given board.

        :param board: Trello board information
        :type board: dict
        :param labels: list of label names
        :type labels: list
        :return: list of label IDs
        :rtype: list
        """
        logger.debug("Board labels: %s", board['labels'])
        names_to_ids = {x['name']: x['id'] for x in board['labels']}
        final = []
        for n in labels:
            if n in names_to_ids:
                final.append(names_to_ids[n])
                continue
            raise Exception("Error: '%s' is not a valid label color or title"
                            " on the board." % n)
        logger.debug('Final labels: %s', final)
        return final

    def ensure_card_labels(self, card, labels):
        """
        Given a card dict and a list of label IDs, ensure all those labels
        and only those labels are set on the card.

        :param card: Trello card information
        :type card: dict
        :param labels: list of label IDs
        :type labels: list
        """
        logger.debug('Ensuring labels on card...')
        logger.info('Labels: %s', card['labels'])
        # remove unwanted labels
        have_ids = []
        for l in card['labels']:
            if l['id'] not in labels:
                if self.dry_run:
                    logger.warning(
                        'DRY RUN: Would delete %s label from card.', l['id']
                    )
                else:
                    logger.info("Removing %s label from card", l['id'])
                    self.trello.cards.delete_idLabel_idLabel(l['id'], card['id'])
            else:
                have_ids.append(l['id'])
        # add wanted labels
        logger.debug('Card now has labels: %s', have_ids)
        for l_id in labels:
            if l_id not in have_ids:
                if self.dry_run:
                    logger.warning('DRY RUN: Would add %s label to card', l_id)
                else:
                    logger.info('Adding %s label to card', l_id)
                    self.trello.cards.new_idLabel(card['id'], l_id)
        logger.debug('Done ensuring labels.')

    def ensure_card_checklists(self, desired_card, checklist_names):
        """
        Given a card dict and a list of checklist names, ensure checklists
        with each of those names are set on the card.

        :param card: Trello card information
        :type card: dict
        :param checklist_names: names of checklists to ensure are on the card
        :type checklist_names: list
        """
        logger.debug('Checklists desired: %s', checklist_names)
        logger.debug(
            'Checklists on card: %s', desired_card.get('idChecklists', [])
        )
        if not checklist_names:
            return
        checklists_present = []
        if desired_card is not None:
            for clid in desired_card.get('idChecklists', []):
                cl = self.trello.checklists.get(clid)
                checklists_present.append(cl['name'])
                logger.debug('Checklist ID %s: %s', clid, cl)
        for clname in checklist_names:
            if clname in checklists_present:
                continue
            logger.debug('Adding checklist with name: %s', clname)
            self.new_checklist(desired_card['id'], clname)

    def filter_cards(self, orig_cards, list_id):
        """filter cards to ones with a due date, and if list_id is not None,
        also in the specified list"""
        cards = []
        logger.debug('Filtering %d cards on board', len(orig_cards))
        for card in orig_cards:
            if list_id is not None and list_id != card['idList']:
                logger.debug('Skipping card %s (%s) in wrong list (%s)',
                             card['id'], card['name'], card['idList'])
                continue
            cards.append(card)
        logger.info('Identified %d cards in list', len(cards))
        return cards

    def id_for_list(self, board, list_name):
        """get the ID for a list with the given name, on the board"""
        if list_name is None:
            logger.debug('No list name specified; skipping list filter')
            return None
        logger.debug('Board has %d lists', len(board['lists']))
        for l in board['lists']:
            if l['closed']:
                continue
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

    def new_checklist(self, card_id, name):
        resp = requests.post(
            "https://trello.com/1/cards/%s/checklists" % (card_id),
            params=dict(key=self.trello._apikey, token=self.trello._token),
            data=dict(name=name)
        )
        resp.raise_for_status()
        return resp.json()


def parse_args(argv):
    """
    parse arguments/options
    """
    p = argparse.ArgumentParser(
        description='Script to ensure that a card with the given title '
                    '(and optionally other attributes) exists in the '
                    'specified column of the specified board.')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-l', '--list', dest='list_name', action='store', type=str,
                   help='list name', required=True)
    p.add_argument('-b', '--board', dest='BOARD_NAME', action='store', type=str,
                   help='board name', required=True)
    p.add_argument('-L', '--label', dest='labels', action='append', type=str,
                   help='label name to set on card; can specify multiple times',
                   default=[])
    p.add_argument('-p', '--position', dest='pos', action='store', type=str,
                   default='bottom',
                   help='position in list to add the card at; "top", "bottom",'
                   'or a positive number (default: bottom)')
    p.add_argument('-D', '--description', dest='desc', action='store', type=str,
                   default=None, help='card description')
    p.add_argument('-C', '--checklist', dest='checklist_name', action='append',
                   default=[],
                   help='Ensure that a checklist with the specified name '
                        'exists on the card. May be specified multiple times.')
    p.add_argument('CARD_TITLE', action='store', type=str,
                   help='card title to ensure')

    args = p.parse_args(argv)
    if args.desc is not None:
        args.desc = args.desc.replace('\\n', "\n")
    try:
        i = float(args.pos)
        if '%s' % i == args.pos:
            args.pos = i
    except:
        pass
    return args


if __name__ == "__main__":
    FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    logger = logging.getLogger()
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    script = TrelloEnsureCard(dry_run=args.dry_run)
    script.run(args.CARD_TITLE,
               list_name=args.list_name,
               board_name=args.BOARD_NAME,
               labels=args.labels,
               pos=args.pos,
               desc=args.desc,
               checklist_names=args.checklist_name
    )
