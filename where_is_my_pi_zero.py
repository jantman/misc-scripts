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
import json
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
            self.gmail_creds()

    def run(self, mail_success=False, no_uk=False):
        """run the actual check, send mail if desired"""
        results = self.check_stock(no_uk)
        have_stock = False
        for s in results:
            if results[s] is True:
                logger.debug('have stock at %s', s)
                have_stock = True
        logger.debug('have_stock=%s', have_stock)
        msg = self.format_msg(results)

    def check_stock(self, no_uk=False):
        """
        query the current stock status from the stores

        returns a dict with store names as keys and values of:
        - True - in-stock
        - False - out-of-stock
        - None - unknown
        """
        results = {}
        for fname in dir(self):
            if not fname.startswith('get_'):
                continue
            storename = fname[4:]
            if storename in UK_STORES and no_uk:
                logger.debug('Skipping UK store: %s', storename)
                continue
            meth = getattr(self, fname)
            try:
                res = meth()
            except Exception:
                logger.exception('caught exception checking %s', storename)
                res = None
            if res is None:
                logger.warning('%s returned None; ignoring', fname)
            elif res is True or res is False:
                results[storename] = res
            else:
                results.update(res)
        return results

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

    def gmail_creds(self):
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

    def url_get(self, url):
        logger.debug('GETing %s', url)
        r = requests.get(url)
        r.raise_for_status()
        return r

    """ BEGIN GETTERS """

    def get_adafruit(self):
        urls = [
            'https://www.adafruit.com/products/2885',
            'https://www.adafruit.com/products/2817',
            'https://www.adafruit.com/products/2816'
        ]
        have_stock = None
        for url in urls:
            logger.debug('checking adafruit: %s', url)
            r = self.url_get(url)
            if 'IN STOCK' in r.text:
                logger.info('found in-stock for %s', url)
                return True
            if 'OUT OF STOCK' in r.text:
                logger.info('found out-of-stock for %s', url)
                have_stock = False
        return have_stock

    def get_pisupply(self):
        url = 'https://www.pi-supply.com/product/raspberry-pi-zero-cable-kit/'
        logger.debug('checking pisupply - %s', url)
        r = self.url_get(url)
        if 'class="stock out-of-stock"' in r.text:
            logger.info('found out-of-stock class for pisupply')
            return False
        if 'class="stock in-stock"' in r.text:
            logger.info('found in-stock class for pisupply')
            return True
        return None

    def get_pimoroni(self):
        url = 'https://shop.pimoroni.com/products/raspberry-pi-zero.js'
        return self.shopify_get('pimoroni', url)

    def shopify_get(self, store, url):
        logger.debug('checking %s at %s', store, url)
        r = self.url_get(url)
        for v in r.json()['variants']:
            if v['inventory_quantity'] > 0:
                logger.info('%s has stock based on variant %s %s (%s) '
                            'quantity %s', store, v['id'], v['sku'], v['title'],
                            v['inventory_quantity'])
                return True
        return False

    def get_thepihut(self):
        url = 'https://thepihut.com/products/raspberry-pi-zero.js'
        return self.shopify_get('thepihut', url)

    def get_element14(self):
        url =         'https://www.element14.com/community/docs/DOC-79263/l/' \
                      'introducing-the-raspberry-pi-zero'
        logger.debug('checking element14 at %s', url)
        r = self.url_get(url)
        if '<span style="color: #ff0000;">SOLD OUT</span>' in r.text:
            logger.info('element14 SOLD OUT for %s', url)
            return False
        if 'Buy Now</a>' in r.text:
            logger.info('element14 Buy Now button on %s', url)
            return True
        return None

    """ END GETTERS """

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
