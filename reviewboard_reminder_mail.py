#!/usr/bin/env python
"""
ReviewBoard - Script to send reminder emails for any open reviews,
targeted at a specific group, not updated in more than X days.

Note:
if https://reviews.reviewboard.org/r/5446/ is really merged and works
the way it seems to, once people start using `rbt` to post reviews, it
should store the current commit hash in ReviewBoard, in which case it
should be possible to simply check if a review was merged or not.

requirements:
RBTools>=0.6,<=0.7

CHANGELOG:
2014-05-07 Jason Antman <jason@jasonantman.com> <@j_antman>:
- intial version
"""

import os
import sys
import optparse
import logging
import pprint
import datetime

from rbtools.api.client import RBClient

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

def parse_rb_time_string(s):
    """
    Unfortunately, the RB API gives us back "timestamps"
    in a non-standard string format, something like:
        2013-09-26T17:22:45.108Z
    AFAIK python can't easily parse this, so we do
    a bit of massaging before we parse it.

    @param s string, time representation to parse

    @return datetime.datetime object
    """
    tz = s[23:]
    if tz == "Z":
        tz = "UTC"
    s = s[0:23] + "000" + tz
    dt = datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%Z")
    return dt

def get_reviews_for_groups(root, groups, dry_run=False):
    """
    Gets a list of reviews for the given review group.
    returns a list of Review Requests

    @param root RBClient root
    @param group list of Review Group objects
    """
    # get open reviews to a specified user, group, etc.
    args = {}
    logger.debug("checking for open/pending reviews for group(s): %s" % groups)

    reviews = []
    count = 0
    try:
        # we don't appear to be able to filter on target_groups in the query :(
        req = root.get_review_requests(status='pending')
        logger.info("\tfound %d pending reviews total" % (req.total_results))
        while True:
            count += 1
            logger.error("debugging - disable the line after this")
            if count > 5:
                raise StopIteration()
            logger.debug("\tresult set iteration %d" % count)
            for review in req:
                for g in review.target_groups:
                    if g.title in groups:
                        logger.debug("found review with correct group(s) - id %d" % review.id)
                        reviews.append(review)
                        break
            req = req.get_next()
    except StopIteration:
        logger.debug("StopIteration - checked all result sets")
    logger.debug("found %d reviews for target groups" % (len(reviews)))
    return reviews

def get_group_id_by_name(root, g_name, dry_run=False):
    """ return the int ID for the ReviewGroup with the given name, or None """
    logger.debug("Looking for review group with name '%s'" % g_name)
    g = root.get_group(group_name=g_name, displayname=True)
    return g.id

def filter_reviews_older_than(root, reviews, days_old, dry_run=False):
    """ return a list with only reviews updated more than days_old days ago """
    newer_than = datetime.datetime.now() - datetime.timedelta(days=7)
    res = []
    for rev in reviews:
        updated = parse_rb_time_string(rev.last_updated)
        if updated <= newer_than:
            res.append(rev)
        else:
            logger.debug("filtering out new review %d - last updated %s" % (rev.id, updated))
    return res

def generate_report_html_table(reviews):
    """ generate a report table of the old reviews """
    users = {}
    for rev in reviews:
        user = rev._links['submitter']['title']
        if user not in users:
            users[user] = []
        users[user].append({'id': rev.id,
                            'url': rev.url,
                            'updated': parse_rb_time_string(rev.last_updated),
                            'submitter': user,
                            'summary': rev.summary,
                            'repo': rev._links['repository']['title'],
                        })

    for user in sorted(users):
        logger.debug("%s: %d" % (user, len(users[user])))
        user_title = user
        for rev in sorted(users[user], key=lambda k: k['updated']):
            html += '<tr><td>%s</td><td>%s</td>' % (user_title,
                                                    ))
            raise SystemExit("left off here - WIP")

    html = ""
    return html

def main(url, group_names, days_old=7, dry_run=False):
    """ do something """
    try:
        user = os.environ['RBUSER']
    except KeyError:
        raise SystemExit("please set RBUSER environment variable for reviewboard user")
    try:
        passwd = os.environ['RBPASS']
    except KeyError:
        raise SystemExit("please set RBPASS environment variable for reviewboard password")
    #client = RBClient(url, user, passwd)
    client = RBClient(url)
    root = client.get_root()
    if not root:
        raise SystemExit("Error - could not get RBClient root.")

    for g_name in group_names:
        o = get_group_id_by_name(root, g_name, dry_run=dry_run)
        if not o:
            raise SystemExit("ERROR: no group '%s' found." % g_name)
        logger.debug("Found group '%s' id=%d" % (g_name, o))

    reviews = get_reviews_for_groups(root, group_names, dry_run=dry_run)

    old_reviews = filter_reviews_older_than(root, reviews, days_old, dry_run=dry_run)
    logger.info("found %d reviews for target groups and last updated %d or more days ago" % (len(old_reviews), days_old))

    if len(old_reviews) < 1:
        logger.info("Found no reviews matching criteria, exiting")
        return False

    table = generate_report_html_table(old_reviews)
    print(table)

    return True

def parse_args(argv):
    """ parse arguments/options """
    p = optparse.OptionParser()

    p.add_option('-d', '--dry-run', dest='dry_run', action='store_true', default=False,
                      help='dry-run - dont actually send metrics')

    p.add_option('-v', '--verbose', dest='verbose', action='count', default=0,
                      help='verbose output. specify twice for debug-level output.')

    p.add_option('-u', '--url', dest='url', action="store", type="string",
                       help='reviewboard server url (default: \'reviews\')', default='http://reviews')

    p.add_option('-g', '--groups', dest='groups', action="store", type="string",
                      help="CSV list of review groups to show reviews for")

    p.add_option('-a', '--age', dest='age', action='store', type='int', default=7,
                 help='notify on reviews with no update in at least this many days (defaul 7)')

    options, args = p.parse_args(argv)

    if not options.url:
        raise SystemExit("ERROR: -u|--url must be specified.")

    if not options.groups:
        raise SystemExit("ERROR: -g|--groups must be specified.")

    if ',' in options.groups:
        options.groups = options.groups.split(',')
    else:
        options.groups = [options.groups]

    return options


if __name__ == "__main__":
    opts = parse_args(sys.argv[1:])

    if opts.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif opts.verbose > 0:
        logger.setLevel(logging.INFO)

    if opts:
        main(opts.url, opts.groups, days_old=opts.age, dry_run=opts.dry_run)
