#!/usr/bin/env python
"""
Sample configuration file for rss_to_mail.py

For full information, see rss_to_mail.py:
<https://github.com/jantman/misc-scripts/blob/master/rss_to_mail.py>

CHANGELOG:
* Fri Jun  7 2013 <jason@jasonamtan.com>:
- initial version of script
"""

EMAIL_TO = ['user@example.com', 'user2@example.com']
EMAIL_FROM = 'sender@example.com' # sender address
# set EMAIL_TEXT_ONLY to True to send plain text email only, not MIME Multipart
EMAIL_TEXT_ONLY = False

# feeds is a dict of name (something you set) to some values
FEEDS = {}

"""
each feeds element has a key of the feed name, and a dict of some values, including:
url - the URL to get the feed from
title_regex - optional, a regex to match for post titles. emails will be sent for matching titles
title_regex_i - optional, make title regex case-insensitive, boolean
body_regex - optional, a regex to match for post body. emails will be sent for matching post bodies
body_regex_i - optional, make body regex case-insensitive, boolean

The key of each feed MUST be a string that includes only filename-safe characters ([A-Za-z0-9_-\.])

Be aware that the regexes are full-string match, so to match anything with "foo" in it, you need ".*foo.*".

if a title_regex is specified, only entries with a title matching it will be included in the email.
if a body_regex is specified, only entries with a body matching it will be included in the email.
if both are specified, only entries matching both will be included in the email.
if neither is specified, all new entries will be included in the email.
"""
FEEDS['python_releases'] = { 
    'url': 'http://python.org/channews.rdf',
    'title_regex': '.*released.*',
    'title_regex_i': True,
}
