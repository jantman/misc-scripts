#!/usr/bin/env python
"""
rss_to_mail.py

Dead simple python script to find new entries in an RSS feed,
and email listing of new entries matching a regex to you.
Intended to be run via cron.

By Jason Antman <jason@jasonantman.com> <http://blog.jasonantman.com>
LICENSE: GPLv3

The latest version of this script will always be available at:
<>

If you have any modifications/improvements, please send me a patch
or a pull request.

Instructions: 
Grab this script and put it somewhere you can run via cron. At start,
if ~/.rsstomail doesn't exist yet, it will create it, populate it with 
an an example config file, and exit. Move ~/.rsstomail/config.py.example
to ~/.rsstomail/config.py and edit it as needed. Then cron up the script.

The first time it sees a new feed, it won't send anything, it will just grab
all the entries and mark them as seen.

CHANGELOG:
* Fri Jun  7 2013 <jason@jasonamtan.com>:
- initial version of script
"""

from optparse import OptionParser
import os.path
import os
import sys
import urllib2 #feedparser requires this too
import pickle
import feedcache
import shelve
#import feedparser

import logging

PROG_DIR="~/.rsstomail"
CONFIG_EXAMPLE_URL="https://raw.github.com/jantman/misc-scripts/master/rss_to_mail_config.py"
DRY_RUN = False

def do_config_setup():
    """
    Sets up the configuration/save directory (PROG_DIR) and initializes an example config file, if not present.
    """
    logging.debug("entering do_config_setup()")
    if not os.path.exists(PROG_DIR):
        logging.info("PROG_DIR does not exist, creating it now")
        try:
            os.makedirs(PROG_DIR)
        except:
            logging.critical("could not create program directory at %s", PROG_DIR)
            sys.exit(1)
    if not os.path.exists("%s/config.py" % PROG_DIR):
        logging.debug("config file does not exist at %s/config.py", PROG_DIR)
        if not os.path.exists("%s/config.py.example" % PROG_DIR):
            logging.debug("example config does not exist at %s/config.py.example, downloading it", PROG_DIR)
            # need to pre-seed the example config file
            try:
                logging.debug("getting %s", CONFIG_EXAMPLE_URL)
                u = urllib2.urlopen(CONFIG_EXAMPLE_URL)
                content = u.read()
            except:
                logging.critical("could not download example config file from %s", CONFIG_EXAMPLE_URL)
                sys.exit(1)
            try:
                f = open("%s/config.py.example" % PROG_DIR, 'w')
                f.write(content)
                f.close()
            except:
                logging.critical("could not write example config file to %s/config.py.example", PROG_DIR)
                sys.exit(1)
        logging.critical("Example configuration file exists at %s/config.py.example", PROG_DIR)
        logging.critical("Please edit example config file and copy to %s/config.py", PROG_DIR)
        sys.exit(1)

def check_one_feed(name, url, title_regex = None, body_regex = None):
    """
    :param fc: an initialized feedcache.Cache object
    :param name: name of the feed, as defined in the config file
    :param url: url of the feed, from the config file
    :param title_regex: optional, a regex to match the entry title against
    :param body_regex: optional, a regex to match the entry body against

    retrns a list of all new entries matching the specified regexes
    """

    matching = []
    logging.info("checking feed '%s' (%s)", name, url)

    SHELVE_FILE = "%s/feedcache.shelve" % PROG_DIR
    try:
        logging.debug("opening shelve file at %s", SHELVE_FILE)
        storage = shelve.open(SHELVE_FILE)
    except:
        logging.critical("unable to open feedcache shelve file (%s)", SHELVE_FILE)
        return []

    try:
        logging.debug("initialize feedcache.Cache")
        fc = feedcache.Cache(storage)
        logging.debug("feedcache.fetch(%s)", url)
        parsed_data = fc.fetch(url)
    except:
        logging.error("unable to fetch/cache feed '%s' from %s", name, url)
        storage.close()
        return []

    storage.close()

    if 'bozo_exception' in parsed_data:
        logging.error("exception parsing feed '%s': %s", name, parsed_data['bozo_exception'])
        return []

    SEEN_PICKLE_FILE = "%s/%s.pkl" % (PROG_DIR, name)
    if os.path.exists(SEEN_PICKLE_FILE):
        try:
            pf = open(SEEN_PICKLE_FILE, 'r')
            seen_ids = pickle.load(pf)
            pf.close()
            logging.debug("loaded %i seen_ids from pickle file" % len(seen_ids))
        except:
            logging.error("unable to load seen_ids from pickle file %s", SEEN_PICKLE_FILE)
    else:
        logging.debug("no existing pickle file for seen_ids for feed '%s', creating empty list", name)
        seen_ids = []

    matching_entries = [] # store the entries that match, return then when we're done

    for entry in parsed_data.entries:
        if entry.id not in seen_ids:
            seen_ids.append(entry.id)
            logging.debug("feed %s: new entry: id %s", name, entry.id)
            print entry.id
            # process the entry
            matching_entries.append(entry)
        else:
            logging.debug("feed %s: already seen: id %s", name, entry.id)

    # write out the seen_ids pickle file so we know what's new
    try:
        pf = open(SEEN_PICKLE_FILE, 'w')
        pickle.dump(seen_ids, pf)
        pf.close()
        logging.debug("wrote seen_ids to pickle file %s", SEEN_PICKLE_FILE)
    except:
        logging.error("could not write seen_ids to pickle file for feed '%s'", name)

    return matching_entries

def check_feeds(FEEDS, EMAIL_TO):
    """
    :param FEEDS: FEEDS dict from config file
    :param EMAIL_TO: EMAIL_TO list from config file

    Main function to handle checking all of the feeds and sending mail on anything new.
    """
    
    for feed in FEEDS:
        if 'title_regex' not in FEEDS[feed]:
            FEEDS[feed]['title_regex'] = None
        if 'body_regex' not in FEEDS[feed]:
            FEEDS[feed]['body_regex'] = None
        foo = check_one_feed(feed, FEEDS[feed]['url'], FEEDS[feed]['title_regex'], FEEDS[feed]['body_regex'])


def main():
    global DEBUG, PROG_DIR, VERBOSE
    cmd_parser = OptionParser(version="%prog",description="RSS to Email Script", usage="%prog [options]")
    cmd_parser.add_option("-d", "--dir", type="string", action="store", dest="dir", default="~/.rsstomail", help="Program config/save directort (default: ~/.rsstomail")
    cmd_parser.add_option("-r", "--dry-run", action="store_true", dest="dryrun", default=False, help="Dry run - don't send mail, just show what would be sent on STDOUT")
    cmd_parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=False, help="Verbose output - show what's being sent")
    cmd_parser.add_option("-D", "--debug", action="store_true", dest="debug", default=False, help="debug-level output of internal logic")
    (cmd_options, cmd_args) = cmd_parser.parse_args()

    log_level = logging.WARNING
    if cmd_options.debug and cmd_options.debug is True:
        log_level = logging.DEBUG
    elif cmd_options.verbose and cmd_options.verbose is True:
        log_level = logging.INFO
    logging.basicConfig(level=log_level, format   = '%(asctime)s %(levelname)s %(name)s %(message)s', datefmt  = '%H:%M:%S')

    if cmd_options.dryrun and cmd_options.dryrun is True:
        DRY_RUN = cmd_options.dryrun
        logging.warning("setting DRY_RUN to True, will not send mail")

    if cmd_options.dir:
        PROG_DIR = os.path.expanduser(cmd_options.dir)
        logging.info("Setting PROG_DIR to '%s'", PROG_DIR)

    if not os.path.exists("%s/config.py" % PROG_DIR):
        logging.info("config file does not exist, calling do_config_setup()")
        do_config_setup()

    try:
        sys.path.append(PROG_DIR)
        import config
    except:
        logging.critical("could not import config.py")
        sys.exit(1)
    logging.debug("Imported config")

    check_feeds(config.FEEDS, config.EMAIL_TO)

if __name__ == '__main__':
    main()
