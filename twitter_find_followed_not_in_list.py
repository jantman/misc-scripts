#!/usr/bin/env python
"""
Terribly simple script using python-twitter to
list any users you're following but whom aren't
in any of your lists.

##################

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/twitter_find_followed_not_in_list.py
"""

import sys
import optparse
import logging
import os
import time

try:
    import twitter
except ImportError:
    raise SystemExit("ERROR: could not import twitter. Please `pip install python-twitter` and run script again.")

from twitter.error import TwitterError

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)


class FindFollowedNotInList:

    credentials = {'api_key': None, 'api_secret': None, 'access_token': None, 'access_secret': None}

    def get_credentials(self):
        """
        Get all credentials or error out
        """
        cred_env_vars = {'api_key': 'TWITTER_API_KEY',
                         'api_secret': 'TWITTER_API_SECRET',
                         'access_token': 'TWITTER_ACCESS_TOKEN',
                         'access_secret': 'TWITTER_ACCESS_SECRET',
                         }
        error = False
        for varname in cred_env_vars:
            val = os.getenv(cred_env_vars[varname], None)
            if val is None:
                error = True
                logger.error("Please export the '{name}' environment variable.".format(name=cred_env_vars[varname]))
            else:
                self.credentials[varname] = val
        if error:
            raise SystemExit("ERROR: incomplete credentials")
        return True

    def main(self, dry_run=False):
        """ do something """
        self.get_credentials()
        self.api = twitter.Api(consumer_key=self.credentials['api_key'],
                               consumer_secret=self.credentials['api_secret'],
                               access_token_key=self.credentials['access_token'],
                               access_token_secret=self.credentials['access_secret'])
        try:
            foo = self.api.VerifyCredentials()
            self.my_user_id = foo.id
        except:
            raise SystemExit("Invalid credentials / auth failed")
            # might need to pass owner_id or something
        list_members = []
        lists = invoke_with_throttling_retries(self.api.GetLists, user_id=self.my_user_id)
        for l in lists:
            print("{id} {name}".format(id=l.id, name=l.name))
            m = invoke_with_throttling_retries(self.api.GetListMembers, l.id, l.slug)
            for member in m:
                list_members.append(member.id)
        followed = invoke_with_throttling_retries(self.api.GetFriends)
        for u in followed:
            if u.id not in list_members:
                print("user {sn} not in any lists (id={id} name={name})".format(
                    id=u.id,
                    name=u.name.encode('utf-8'),
                    sn=u.screen_name.encode('utf-8'))
                )
        return True

def invoke_with_throttling_retries(function_ref, *argv, **kwargs):
    MAX_RETRIES = 6
    SLEEP_BASE_SECONDS = 5

    retries = 0
    while True:
        try:
            retval = function_ref(*argv, **kwargs)
            return retval
        except TwitterError as e:
            if e[0]['message'] != 'Rate limit exceeded':
                raise e
            if retries == MAX_RETRIES:
                logger.error("Reached maximum number of retries; raising error")
                raise e
        stime = SLEEP_BASE_SECONDS * (2**retries)
        logger.info("Call of %s got throttled; sleeping %s seconds before "
                    "retrying", function_ref, stime)
        time.sleep(stime)
        retries += 1

def parse_args(argv):
    """ parse arguments/options """
    p = optparse.OptionParser()

    p.add_option('-v', '--verbose', dest='verbose', action='count', default=0,
                      help='verbose output. specify twice for debug-level output.')

    options, args = p.parse_args(argv)

    return options


if __name__ == "__main__":
    opts = parse_args(sys.argv[1:])

    if opts.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif opts.verbose > 0:
        logger.setLevel(logging.INFO)

    cls = FindFollowedNotInList()
    cls.main()
