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
import feedparser
import os.path
import logging
import os
import sys

PROG_DIR="~/.rsstomail"
DEBUG = False
VERBOSE = False
DRY_RUN = False

def do_config_setup():
    """
    Sets up the configuration/save directory (PROG_DIR) and initializes an example config file, if not present.
    """
    logger.debug("entering do_config_setup()")
    if not os.path.exists(PROG_DIR):
        logger.info("PROG_DIR does not exist, creating it now")
        try:
            os.makedirs(PROG_DIR)
        except:
            logger.critical("ERROR - could not create program directory at %s", PROG_DIR)
            sys.exit(1)
    if not os.path.exists("%s/config.py" % PROG_DIR):
        logger.debug("config file does not exist at %s/config.py", PROG_DIR)
        if not os.path.exists("%s/config.py.example" % PROG_DIR):
            logger.debug("example config does not exist at %s/config.py.example, downloading it", PROG_DIR)
            # need to pre-seed the example config file
            print "foo"
        logger.critical("Example configuration file exists at %s/config.py.example", PROG_DIR)
        logger.critical("Please edit example config file and copy to %s/config.py", PROG_DIR)
        sys.exit(1)

if __name__ == '__main__':
    cmd_parser = OptionParser(version="%prog",description="RSS to Email Script", usage="%prog [options]")
    cmd_parser.add_option("-d", "--dir", type="string", action="store", dest="dir", default="~/.rsstomail", help="Program config/save directort (default: ~/.rsstomail")
    cmd_parser.add_option("-r", "--dry-run", action="store_true", dest="dryrun", default=False, help="Dry run - don't send mail or update saved state, just show what would be done")
    cmd_parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=False, help="Verbose output - show what's being sent")
    cmd_parser.add_option("-D", "--debug", action="store_true", dest="debug", default=False, help="debug-level output of internal logic")
    (cmd_options, cmd_args) = cmd_parser.parse_args()

    logger = logging.getLogger("rss_to_mail")
    ch = logging.StreamHandler()
    logger.addHandler(ch)

    if cmd_options.debug and cmd_options.debug is True:
        DEBUG = cmd_options.debug
        logger.setLevel(logging.DEBUG)
    elif cmd_options.verbose and cmd_options.verbose is True:
        VERBOSE = cmd_options.verbose
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)

    if cmd_options.dryrun and cmd_options.dryrun is True:
        DRY_RUN = cmd_options.dryrun
        logger.warning("setting DRY_RUN to True, will not send mail or set saved state")

    if cmd_options.dir:
        PROG_DIR = os.path.expanduser(cmd_options.dir)
        logger.info("Setting PROG_DIR to '%s'", PROG_DIR)

    if not os.path.exists("%s/config.py" % PROG_DIR):
        logger.info("config file does not exist, calling do_config_setup()")
        do_config_setup()
