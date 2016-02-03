#!/usr/bin/env python
"""
Python script to retrieve HipChat room history for a specific date.

One of the features missing from the HipChat client (that I really miss from
having an IRC server with HTTP-accessible log archives) is the ability to
quickly pull up logs from a specific date. As far as I can tell, the only way to
do this in the client is to scroll back. That's fine for yesterday. It doesn't
really work for three months ago.

## Requirements

1. The [hypchat](https://github.com/RidersDiscountCom/HypChat) Python package
  (``pip install hypchat``) and the ``pytz`` package (``pip install pytz``).
2. Your HipChat API token exported as the ``HIPCHAT_TOKEN`` environment
  variable, or saved in ``~/.hypchat`` or ``/etc/hypchat``. If using one of the
  configuration files, they should be in INI format (parsable by Python's
  ConfigParser), with the token set as the ``token`` attribute in the
  ``HipChat`` section.
3. If you wish to use an endpoint other than https://www.hipchat.com, you can
  set the endpoint URL as the ``endpoint`` attribute under the ``HipChat``
  section of one of the above-mentioned config files, or export it as the
  ``HIPCHAT_ENDPOINT`` environment variable.

## Usage



If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/hipchat_date_history.py>

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2016-02-03 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import ConfigParser
import argparse
import logging
import re
import json
from datetime import datetime
from hypchat import HypChat
from hypchat.restobject import Linker, mktimestamp
from pytz import timezone

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)


class HypchatHistory:
    """ might as well use a class. It'll make things easier later. """

    def __init__(self):
        """ init method, run at class creation """
        endpoint, token = self._get_token_endpoint()
        if token is None:
            raise SystemExit('Authorization token not detected! The token is '
                             'pulled from ~/.hypchat, /etc/hypchat, or the '
                             'environment variable HIPCHAT_TOKEN.')
        logger.debug("Connecting to HipChat (endpoint=%s)", endpoint)
        self.hipchat = HypChat(token, endpoint)
        logger.debug("Connected")

    def _get_token_endpoint(self):
        """get the API token - pulled from HypChat __main__.py"""
        token = None
        endpoint = None
        config = ConfigParser.ConfigParser()
        config.read([os.path.expanduser('~/.hypchat'), '/etc/hypchat'])

        # get token
        if config.has_section('HipChat'):
            token = config.get('HipChat', 'token')
        elif 'HIPCHAT_TOKEN' in os.environ:
            token = os.environ['HIPCHAT_TOKEN']

        # get endpoint
        if config.has_section('HipChat'):
            endpoint = config.get('HipChat', 'endpoint')
        elif 'HIPCHAT_ENDPOINT' in os.environ:
            endpoint = os.environ['HIPCHAT_ENDPOINT']
        else:
            endpoint = 'https://www.hipchat.com'
        return (endpoint, token)

    def _get_dates(self, hx_date, tz_name):
        """
        return start and end  datetimes for the given date string and TZ name
        """
        tz = timezone(tz_name)
        m = re.match(r'(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})',
                     hx_date)
        if m is None:
            raise SystemExit("ERROR: date must match YYYY-MM-DD format.")
        year = int(m.group('year'))
        month = int(m.group('month'))
        day = int(m.group('day'))
        start_dt = datetime(year, month, day, 0, 0, 0, tzinfo=tz)
        end_dt = datetime(year, month, day, 23, 59, 59, tzinfo=tz)
        return (start_dt, end_dt)

    def _get_hx(self, room, start_dt, end_dt):
        """
        HypChat's Room.history() method only takes a ``date`` argument, which
        fetches ALL history up to that date. We just want a specific date...
        """
        start_date, start_tz = mktimestamp(start_dt)
        end_date, end_tz = mktimestamp(end_dt)
        params = {
            'date': end_date,
            'end-date': start_date,
            'timezone': start_tz,
            'max-results': 1000,
        }
        resp = room._requests.get(room.url + '/history', params=params)
        return Linker._obj_from_text(resp.text, room._requests)

    def _dump_json(self, items):
        """print json"""
        json_items = []
        for i in items:
            i['date'] = str(i['date'])
            json_items.append(i)
            print(json.dumps(json_items))

    def _format_message(self, msg):
        from_s = ''
        if isinstance(msg['from'], dict):
            from_s = '@' + msg['from']['mention_name']
        else:
            from_s = str(msg['from'])
        date_s = msg['date'].strftime('%H:%M:%S')
        return "%s %s: %s" % (date_s, from_s, msg['message'])

    def run(self, room_name, hx_date, tz_name='UTC', json_out=False):
        """ do stuff here """
        room = self.hipchat.get_room(room_name)
        start_dt, end_dt = self._get_dates(hx_date, tz_name)
        hx = self._get_hx(room, start_dt, end_dt)
        all_items = []
        for item in hx.contents():
            all_items.append(item)
        if json_out:
            self._dump_json(all_items)
            return
        for item in all_items:
            print(self._format_message(item))


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Python script to retrieve HipChat '
                                'room history for a specific date.')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-t', '--tz', dest='tz', action='store', type=str,
                   default='UTC', help='timezone (default: UTC; must be '
                   'recognized by pytz)')
    p.add_argument('-j', '--json', dest='json', action='store_true',
                   default=False, help='dump all messages as JSON')
    p.add_argument('ROOM', action='store', type=str, help='room name or ID')
    p.add_argument('DATE', action='store', type=str, help='date (YYYY-MM-DD)')

    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    script = HypchatHistory()
    script.run(args.ROOM, args.DATE, tz_name=args.tz, json_out=args.json)
