#!/usr/bin/env python
"""
rss_to_mail.py

Dead simple python script to find new entries in an RSS feed,
and email listing of new entries matching a regex to you.
Intended to be run via cron.

By Jason Antman <jason@jasonantman.com> <http://blog.jasonantman.com>
LICENSE: GPLv3

The latest version of this script will always be available at:
<https://github.com/jantman/misc-scripts/blob/master/rss_to_mail.py>

If you have any modifications/improvements, please send me a patch
or a pull request.

Instructions: 
Grab this script and put it somewhere you can run via cron. At start,
if ~/.rsstomail doesn't exist yet, it will create it, populate it with 
an an example config file, and exit. Move ~/.rsstomail/config.py.example
to ~/.rsstomail/config.py and edit it as needed. Then cron up the script.

The first time it sees a new feed, it won't send anything, it will just grab
all the entries and mark them as seen.

NOTE - This script sends email using the local SMTP server.

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
import re
import time
import logging
import getpass # to find current username for email footer
import platform

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import message

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

def check_one_feed(name, config):
    """
    :param name: name of the feed, as defined in the config file
    :param config: configuration file dict for this feed

    retrns a dict {'matching_entries': list of all new entries matching the specified regexes, 'link': feed link}
    """

    url = config['url']
    matching = []
    logging.info("checking feed '%s' (%s)", name, url)

    SHELVE_FILE = "%s/feedcache.shelve" % PROG_DIR
    try:
        logging.debug("opening shelve file at %s", SHELVE_FILE)
        storage = shelve.open(SHELVE_FILE)
    except:
        logging.critical("unable to open feedcache shelve file (%s)", SHELVE_FILE)
        return {'matching_entries': [], 'link': ""}

    try:
        logging.debug("initialize feedcache.Cache")
        fc = feedcache.Cache(storage)
        logging.debug("feedcache.fetch(%s)", url)
        parsed_data = fc.fetch(url)
    except:
        logging.error("unable to fetch/cache feed '%s' from %s", name, url)
        storage.close()
        return {'matching_entries': [], 'link': ""}

    storage.close()

    if 'bozo_exception' in parsed_data:
        logging.error("exception parsing feed '%s': %s", name, parsed_data['bozo_exception'])
        return {'matching_entries': [], 'link': ""}

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

    if 'title_regex' in config:
        if 'title_regex_i' in config:
            title_re = re.compile(config['title_regex'], re.I)
        else:
            title_re = re.compile(config['title_regex'])
    if 'body_regex' in config:
        if 'body_regex_i' in config:
            body_re = re.compile(config['body_regex'], re.I)
        else:
            body_re = re.compile(config['body_regex'])

    for entry in parsed_data.entries:
        if entry.id not in seen_ids:
            seen_ids.append(entry.id)
            logging.debug("feed %s: new entry: id %s", name, entry.id)
            # process the entry
            title_match = False
            if 'title_regex' in config:
                if title_re.match(entry.title):
                    logging.debug("title regex match, title '%s', id %s", entry.title, entry.id)
                    title_match = True
            body_match = False
            if 'body_regex' in config:
                if body_re.match(entry.title):
                    logging.debug("body regex match, id %s", entry.id)
                    body_match = True
            if 'title_regex' in config and 'body_regex' in config:
                if title_match and body_match:
                    matching_entries.append(entry)
            elif 'title_regex' in config:
                if title_match:
                    matching_entries.append(entry)
            elif 'body_regex' in config:
                if body_match:
                    matching_entries.append(entry)
            else:
                # else we just want everything new
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

    if 'feed' in parsed_data and 'link' in parsed_data['feed']:
        link = parsed_data['feed']['link']
    else:
        link = ""
    return {'matching_entries': matching_entries, 'link': link}

def check_feeds(FEEDS, EMAIL_TO, EMAIL_TEXT_ONLY, EMAIL_FROM):
    """
    :param FEEDS: FEEDS dict from config file
    :param EMAIL_TO: EMAIL_TO list from config file

    Main function to handle checking all of the feeds and sending mail on anything new.
    """
    
    matched = {}
    links = {}
    for feed in FEEDS:
        foo = check_one_feed(feed, FEEDS[feed])
        logging.info("matched %i entries in feed %s", len(foo['matching_entries']), feed)
        if len(foo) > 0:
            matched[feed] = foo['matching_entries']
            links[feed] = foo['link']
    
    # ok, we have all of our stuff, format an email to send
    subject = "rss_to_mail - new feed items"
    plain = "rss_to_mail new feed items at %s\n\n" % time.strftime('%a, %B %s %Y %H:%M')
    html = "<html><head><body><p>rss_to_mail new feed items at %s</p>\n" % time.strftime('%a, %B %s %Y %H:%M')

    for feed in matched:
        # print header for each feed
        if feed in links:
            plain = plain + "\n\n%s <%s>\n" % (feed, links[feed])
            html = html + "<p><strong><a href=\"%s\">%s</a></p>" % (feed, links[feed])
        else:
            plain = plain + "%s\n" % feed
            html = html + "<p><strong>%s</p>" % feed
        html = html + "<p><ul>"
        for entry in matched[feed]:
            # print link/info for each entry
            plain = plain + "+ %s (%s) <%s>\n" % (entry['title'], entry['published'], entry['link'])
            html = html + "<li><a href=\"%s\">%s</a> (published at %s)</li>" % (entry['link'], entry['title'], entry['published'])
        html = html + "</ul></p>"

    # TODO - footer for where and how this was generated - hostname, path to script, PROG_DIR, username, date, time
    username = getpass.getuser()
    hostname = platform.node()
    foo = "Generated by: %s running as user %s on %s at %s, configured with PROG_DIR=%s" % (__file__, username, hostname, time.strftime('%a, %B %s %Y %H:%M:%S'), PROG_DIR)
    plain = plain + "\n\n" + foo + "\n"
    html = html + "<br /><p><em>%s</em></p>\n" % foo

    html = html + "</body></html>\n"
    
    # send mail
    if DRY_RUN:
        print "Dry Run only. Not sending mail."
        print "Would have sent the following to: %s" % ", ".join(EMAIL_TO)
        print "#### HTML #####"
        print html
        print "#### PLAIN #####"
        print plain
    else:
        if EMAIL_TEXT_ONLY:
            s = smtplib.SMTP('localhost')
            logging.debug("formatted mail as MIME")
            for addr in EMAIL_TO:
                msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n%s\r\n" % (EMAIL_FROM, addr, subject, plain)
                s.sendmail(EMAIL_FROM, addr, msg)
                logging.debug("sent email to %s" % addr)
            s.quit()
        else:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = EMAIL_FROM
            part1 = MIMEText(plain, 'plain')
            part2 = MIMEText(html, 'html')
            msg.attach(part1)
            msg.attach(part2)
            s = smtplib.SMTP('localhost')
            logging.debug("formatted mail as MIME")
            for addr in EMAIL_TO:
                msg['To'] = addr
                s.sendmail(EMAIL_FROM, addr, msg.as_string())
                logging.debug("sent email to %s" % addr)
            s.quit()
        
def main():
    global PROG_DIR, DRY_RUN
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

    try:
        config.EMAIL_TEXT_ONLY
    except NameError:
        config.EMAIL_TEXT_ONLY = False
    check_feeds(config.FEEDS, config.EMAIL_TO, config.EMAIL_TEXT_ONLY, config.EMAIL_FROM)

if __name__ == '__main__':
    main()
