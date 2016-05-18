#!/usr/bin/env python
"""
Script to check raspberry pi zero availability and send GMail if found.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/where_is_my_pi_zero.py>

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

REQUIREMENTS:
Python (tested with 2.7)
requests

GMAIL CREDENTIALS:
Either export as GMAIL_USERNAME and GMAIL_PASSWORD environment variables,
or define as GMAIL_USERNAME and GMAIL_PASSWORD in ~/.ssh/apikeys.py

CHANGELOG:
2016-05-18 jantman:
- first version

"""

import os
import sys
import re
import argparse
import requests
from datetime import datetime

import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from email.utils import make_msgid
from email.utils import formataddr

import logging

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

UK_STORES = ['pimoroni', 'thepihut']


class PiZeroChecker:
    """check RaspberryPi Zero availability"""

    def __init__(self, no_mail=False):
        """initialize, get javascript and get GMail credentials"""
        self.gmail_user = None
        self.gmail_password = None
        if not no_mail:
            self.get_gmail_creds()
        self.get_stores()

    def run(self, mail_success=False, no_uk=False):
        """run the actual check, send mail if desired"""
        results = {}
        for s in self.stores:
            results[s] = self.get_store(s)
            logger.warning('%s - %s', s, results[s])
        if no_uk:
            logger.debug('Removing UK stores from results (%s)', UK_STORES)
            for s in UK_STORES:
                if s in results:
                    del results[s]
        have_stock = False
        for s in results:
            if results[s] is True:
                logger.debug('have stock at %s', s)
                have_stock = True
        logger.debug('have_stock=%s', have_stock)
        msg = self.format_msg(results)

    def format_msg(self, results):
        """format an email message with results"""
        m = "PiZero stock as of %s\n\n" % datetime.now().isoformat()
        for store, stock in sorted(results.items()):
            m += '%s: ' % store
            if stock is True:
                m += 'IN STOCK'
            elif stock is False:
                m += 'out of stock'
            else:
                m += 'unknown'
            m += "\n"
        return m

    def get_store(s, name):
        """
        get the status for a given store

        returns:
        True - in-stock
        False - out-of-stock
        None - unknown
        """
        url = 'http://whereismypizero.com/api/public/stock/%s' % name
        logger.debug('getting store %s from %s', name, url)
        r = requests.get(url)
        r.raise_for_status()
        j = r.json()
        logger.debug('response: %s' % j)
        if name not in j:
            logger.error('Error: could not find response element for %s - %s',
                         name, j)
            return None
        if 'class="in-stock"' in j[name]:
            return False
        elif 'class="sold-out"' in j[name]:
            return True
        return None

    def get_gmail_creds(self):
        """load gmail credentials"""
        if 'GMAIL_USERNAME' in os.environ and 'GMAIL_PASSWORD' in os.environ:
            logger.debug('setting GMail credentials from environment vars')
            self.gmail_user = os.environ['GMAIL_USERNAME']
            self.gmail_password = os.environ['GMAIL_PASSWORD']
            return
        try:
            # look for GITHUB_TOKEN defined in ~/.ssh/apikeys.py
            sys.path.append(
                os.path.abspath(os.path.join(os.path.expanduser('~'), '.ssh'))
            )
            from apikeys import GMAIL_USERNAME, GMAIL_PASSWORD
            logger.debug('setting GMail credentials from ~/.ssh/apikeys.py')
            self.gmail_user = GMAIL_USERNAME
            self.gmail_password = GMAIL_PASSWORD
        except:
            raise SystemExit("Error: could not find GMail credentials in "
                             "environment variables or ~/.ssh/apikeys.py")

    def get_stores(self):
        """grab the list of stores to check from the JS"""
        url = 'http://whereismypizero.com/js/api_calls.js'
        logger.debug('getting list of stores from: %s', url)
        r = requests.get(url)
        r.raise_for_status()
        m = re.search(r'var stores=\[([^\]]+)\]', r.text)
        if m is None:
            logger.debug('script content:\n%s', r.text)
            raise SystemExit("Error: could not find stores variable in JS")
        logger.debug('raw stores list: %s', m.group(1))
        parts = m.group(1).split(',')
        stores = []
        for p in parts:
            p = p.strip('"\'')
            p = p.strip()
            stores.append(p)
        logger.debug('stores: %s', stores)
        return stores

    def send_email(self, subj, content):
        """send email"""
        msg = MIMEText(content)
        msg['Subject'] = subj
        msg['From'] = formataddr((self.gmail_user, self.gmail_user))
        msg['To'] = self.gmail_user
        msg['Date'] = formatdate(localtime=True)
        msg['Message-Id'] = make_msgid()
        logger.debug('Connecting to GMail')
        s = smtplib.SMTP('smtp.gmail.com:587')
        s.starttls()
        logger.debug('Logging in to GMail')
        s.login(self.gmail_user, self.gmail_password)
        logger.debug('Sending email')
        s.sendmail(self.gmail_user, [self.gmail_user], msg.as_string())
        s.quit()


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='check RaspberryPi Zero '
                                'availability')
    p.add_argument('-m', '--no-mail', dest='no_mail', action='store_true',
                   default=False, help='dont send mail via GMail')
    p.add_argument('-s', '--mail-success', dest='mail_success',
                   action='store_true', default=False,
                   help='only send mail on success')
    p.add_argument('--no-uk', dest='no_uk', action='store_true', default=False,
                   help='ignore pimoroni and pihut (UK stores)')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    args = p.parse_args(argv)
    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    script = PiZeroChecker(no_mail=args.no_mail)
    script.run(args.mail_success, args.no_uk)
