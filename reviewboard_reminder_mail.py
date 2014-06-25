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

from platform import node
from getpass import getuser

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

def generate_report_html_table(reviews, base_url):
    """ generate a report table of the old reviews """
    header = "<tr><th>User</th><th>Review</th><th>Last Updated</th><th>Repo</th><th>Summary</th></tr>\n"
    rev_line = "<tr><td>{user_title}</td><td><a href=\"{url}\">{rev[id]}</a></td><td>{rev[updated]}</td><td>{rev[repo]}</td><td>{rev[summary]}</td></tr>\n"

    users = {}
    for rev in reviews:
        user = rev._links['submitter']['title']
        if user not in users:
            users[user] = []
        user_dict = {'id': rev.id,
                     'url': rev.url,
                     'updated': parse_rb_time_string(rev.last_updated),
                     'submitter': user,
                     'summary': rev.summary,
        }
        try:
            user_dict['repo'] = rev._links['repository']['title']
        except KeyError:
            user_dict['repo'] = 'unknown'
        users[user].append(user_dict)

    html = "<table border=\"1\">\n" + header
    for user in sorted(users):
        logger.debug("%s: %d" % (user, len(users[user])))
        user_title = user
        for rev in sorted(users[user], key=lambda k: k['updated']):
            html += rev_line.format(user_title=user_title,
                                    rev=rev,
                                    url=(base_url + rev['url']),
                                )
            user_title = '&nbsp;' # only list the user once

    html += "</table>\n"
    return html

def get_submitters_for_reviews(reviews):
    """
    return a dict of Users that submitted for reviews, key is username,
    each val is the User object returned by RBClient
    """
    users = {}
    for rev in reviews:
        s = rev.get_submitter()
        users[s.username] = s
    return users

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

    users = get_submitters_for_reviews(old_reviews)
    logger.debug("got user information for %d users" % len(users))
    recipients = []
    for u in users:
        recipients.append("{u.fullname} <{u.email}>".format(u=users[u]))

    table = generate_report_html_table(old_reviews, url)

    body = "<h1>ReviewBoard reminder</h1>\n"
    body += """<p>You're receiving this message because you have one or more pending code reviews on <a href="{url}">{url}</a>
targeted at the '{group_names}' group(s) that have not been updated in over {days_old} days and have not been submitted.
At your convenience, please evaluate these reviews and close/submit any that have been merged or discarded.
Thank You.</p>\n""".format(url=url, days_old=days_old, group_names=", ".join(group_names))
    body += table
    body += "\n<br />\n"
    host = node()
    user = getuser()
    body += """
<p><em>generated by <a href=\"https://github.com/jantman/misc-scripts/blob/master/reviewboard_reminder_mail.py">reviewboard_reminder_mail.py</a>
running on {host} as {user} at {ds}</em></p>
""".format(host=host, user=user, ds=datetime.datetime.now().isoformat())

    if dry_run:
        print("Message to send:\n##############################\n{msg}\n#################################\n".format(msg=body))
        print("Would send to:\n {to}".format(to=", ".join(recipients)))
    else:
        raise SystemExit("Oops - never actually implemented the mail sending...")

    return True

def parse_args(argv):
    """ parse arguments/options """
    p = optparse.OptionParser()

    p.add_option('-d', '--dry-run', dest='dry_run', action='store_true', default=False,
                      help='dry-run - dont actually send anything')

    p.add_option('-v', '--verbose', dest='verbose', action='count', default=0,
                      help='verbose output. specify twice for debug-level output.')

    p.add_option('-u', '--url', dest='url', action="store", type="string",
                       help='reviewboard server url (default: \'reviews\')', default='http://reviews')

    p.add_option('-g', '--groups', dest='groups', action="store", type="string",
                      help="CSV list of review groups to show reviews for")

    p.add_option('-a', '--age', dest='age', action='store', type='int', default=7,
                 help='notify on reviews with no update in at least this many days (default 7)')

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
