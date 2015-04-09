#!/usr/bin/env python
"""
# jira2trello.py
Script for using Trello boards to track Jira cards.

## What it Does

Iterates over the cards on a given trello board that seem
to reference a Jira issue in the name and for each card:
- prefixes the title with (time estimate) if the Time Tracking
original estimate field is filled out in Jira
- updates the title with the issue summary, if changed
- prefixes the issue number in the Trello title with the parent
ticket ID, if it is a subtask
- moves the card to a specified list if it is closed in Jira

Jira issues are detected if the uppercased name of the card
matches the JIRA_TICKET_RE configuration value; the first
capture group of this value should be the ticket ID in Jira.

## Requirements

- python 2.7 (for the `imp` module)
- the ``trello`` package from PyPi (tested with 0.9.1)


## Configuration

Run with --genconfig to generate a sample configuration file at ~/.jira2trello.py
and fill in values per the comments.

## Source and Bugs

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/jira2trello.py>

## Copyright

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

## CHANGELOG

2015-04-01 Jason Antman <jason@jasonantman.com>:
  - initial version
2015-04-09 Jason Antman <jason@jasonantman.com>:
  - fix for missing issue.fields.aggregatetimeoriginalestimate attribute
"""

import sys
import argparse
import logging
import os
import imp
import textwrap
import re
import math
from pprint import pprint

from trello import TrelloApi
from jira import JIRA
from jira.utils import JIRAError

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)


class JiraToTrello:
    """jira-to-trello updater"""

    def __init__(self, confpath, logger=None, dry_run=False, verbose=0):
        """ init method, run at class creation """
        # setup a logger; allow an existing one to be passed in to use
        self.logger = logger
        if logger is None:
            self.logger = logging.getLogger(self.__class__.__name__)
        if verbose > 1:
            self.logger.setLevel(logging.DEBUG)
        elif verbose > 0:
            self.logger.setLevel(logging.INFO)
        self.dry_run = dry_run
        self.load_config(confpath)

    def load_config(self, confpath):
        """load config from disk"""
        if not os.path.exists(confpath):
            self.logger.error('Specified configuration file does not exist: {p}'.format(p=confpath))
            raise SystemExit(1)
        self.logger.info("Loading configuratin from {c}".format(c=confpath))
        self.config = imp.load_source('config', confpath)
        self.logger.debug("Config loaded")
        self.ticket_re = re.compile(self.config.JIRA_TICKET_RE)

    def run(self):
        """main entry point"""
        # connect to Jira
        self.logger.debug("Connecting to Jira API")
        j_options = {
            'server': self.config.JIRA_URL,
        }
        self.jira = JIRA(j_options, basic_auth=(self.config.JIRA_USER, self.config.JIRA_PASS))
        if not self.jira:
            self.logger.error("Error connecting to Jira")
            raise SystemExit(1)
        # connect to Trello
        self.logger.debug("Connecting to Trello API")
        self.trello = TrelloApi(self.config.TRELLO_APP_KEY,
                                token=self.config.TRELLO_TOKEN)
        if not self.trello:
            self.logger.error("Error connecting to Trello")
            raise SystemExit(1)
        self.logger.info("Connected to Trello")
        self.logger.debug("Getting Trello board")
        self.board = self.trello.boards.get(self.config.TRELLO_BOARD_ID)
        self.board_id = self.board['id']
        self.logger.info("Using board '{n}' ({u}; id={i})".format(n=self.board['name'], u=self.board['url'], i=self.board_id))
        self.logger.debug("Getting board lists")
        self.list_id = None
        for l in self.trello.boards.get_list(self.board['id']):
            if l['name'].lower() == self.config.TRELLO_DONE_LIST_NAME.lower():
                self.list_id = l['id']
                self.logger.info("Using done list {i}".format(i=self.list_id))
                break
        if self.list_id is None:
            self.logger.error("ERROR: Unable to find list with name '{n}' on board.".format(n=self.config.TRELLO_DONE_LIST_NAME))
            raise SystemExit(1)
        self.do_cards()

    def do_cards(self):
        """iterate over all cards on the board and update them"""
        self.logger.debug("Getting open cards on board.")
        cards = self.trello.boards.get_card_filter('open', self.board_id)
        self.logger.info("Found {c} open cards on board.".format(c=len(cards)))
        for card in cards:
            ticket = self.jira_id_for_card(card)
            if ticket is None:
                self.logger.debug("Skipping (not Jira card): '{n}' ({u})".format(u=card['url'], n=card['name']))
                continue
            self.do_card(card, ticket)

    def jira_id_for_card(self, card):
        m = self.ticket_re.match(card['name'].upper())
        if m:
            return m.group(1)
        return None

    def do_card(self, card, ticket_id):
        """handle a single card that appears to include a Jira ticket ID"""
        self.logger.debug("do_card ticket={t} card={c}".format(t=ticket_id, c=card['url']))
        try:
            issue = self.jira.issue(ticket_id)
        except JIRAError as ex:
            self.logger.error("ERROR - unable to get Jira issue {i}".format(i=ticket_id))
            self.logger.exception(ex)
            return
        # move if closed
        if issue.fields.status.name.upper() == 'CLOSED':
            if card['idList'] == self.list_id:
                self.logger.debug('Closed issue already in Done list')
                return
            self.logger.info("Moving card for Closed ticket to list '{l}'".format(
                l=self.config.TRELLO_DONE_LIST_NAME)
            )
            if not self.dry_run:
                self.trello.cards.update_idList(card['id'], self.list_id)
            else:
                self.logger.warning("DRY RUN - not actually moving card")
            return
        # check time tracking
        tt = ''
        if ( hasattr(issue.fields, 'aggregatetimeoriginalestimate') and 
             issue.fields.aggregatetimeoriginalestimate is not None):
            tt = '({t}) '.format(
                t=self.humantime(issue.fields.aggregatetimeoriginalestimate)
            )
        # parent issue
        parent_str = ''
        if hasattr(issue.fields, 'parent') and issue.fields.parent is not None:
            parent_str = '{p} -> '.format(p=issue.fields.parent.key)
        newname = '{tt}{p}{id}: {summary}'.format(
            tt=tt,
            id=issue.key,
            p=parent_str,
            summary=issue.fields.summary
        )
        if card['name'] == newname:
            self.logger.debug("card name is correct: {n}".format(n=newname))
            return
        self.logger.info('Changing card name from "{o}" to "{n}"'.format(o=card['name'], n=newname))
        if not self.dry_run:
            self.trello.cards.update(card['id'], name=newname)
        else:
            self.logger.warning("DRY RUN - not actually changing card name")

    def humantime(self, int_seconds):
        """convert integer seconds to human time, based on 8h days"""
        s = int_seconds
        day = 86400
        if s >= day:
            return '{c}d'.format(c=int(math.ceil(s / day)))
        if s >= 3600:
            return '{c}h'.format(c=int(math.ceil(s / 3600)))
        return '{c}m'.format(c=int(math.ceil(s / 60)))

    @staticmethod
    def gen_config(confpath):
        """write sample config file"""
        if os.path.exists(confpath):
            sys.stderr.write("ERROR: file already exists at: {p}\n".format(p=confpath))
            raise SystemExit(1)
        with open(confpath, 'w') as fh:
            fh.write(textwrap.dedent("""
            # sample config file for jira2trello.py
            # see: https://github.com/jantman/misc-scripts/blob/master/jira2trello.py

            # Jira credentials
            JIRA_URL = 'https://jira.example.com'
            JIRA_USER = 'myuser'
            JIRA_PASS = 'mypass'

            # regular expression to match against the upper-cased card name;
            # first capture group should be the Jira ticket ID
            JIRA_TICKET_RE = '.*((project1|project2|project3)-\d+):.*'
            # Note: the format that the card names will be converted to is:
            # <time tracking> <Issue Id>: <Issue Summary>
            # This is in line with <https://github.com/jantman/userscripts/blob/master/TrelloContextMenu.user.js>

            # Trello Developer/Application key - you can get this from <https://trello.com/app-key>
            TRELLO_APP_KEY = 'd141cd6874d46ba92770697e7721a614'
            # Trello token (secret) - get this from:
            # <https://trello.com/1/authorize?key=d141cd6874d46ba92770697e7721a614&name=jira2trello.py&expiration=never&response_type=token&scope=read,write>
            TRELLO_TOKEN = 'myToken'

            # Trello board to search; get this ID from the URL to the board
            TRELLO_BOARD_ID = 'myBoardId'
            # List on that board to move closed cards to
            TRELLO_DONE_LIST_NAME = 'Done'
            """))
        raise SystemExit(0)

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    confpath = os.path.abspath(os.path.expanduser('~/.jira2trello.py'))
    p = argparse.ArgumentParser(description='Sample python script skeleton.')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true', default=False,
                      help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                      help='verbose output. specify twice for debug-level output.')
    p.add_argument('-c', '--config', dest='confpath', action='store', type=str,
                   default=confpath,
                   help='path to config file; default: {c}'.format(c=confpath))
    p.add_argument('--genconfig', dest='genconfig', action='store_true', default=False,
                   help='Write out example config file to {c}'.format(c=confpath))

    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.genconfig:
        JiraToTrello.gen_config(args.confpath)
    script = JiraToTrello(args.confpath, dry_run=args.dry_run, verbose=args.verbose)
    script.run()
