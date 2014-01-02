#!/usr/bin/env python
"""
Python script that parses Apache HTTPD access logs,
finds all unique URLs, and compares the current HTTP
response code to that of another server.

Written for when I moved my blog from self-hosted WordPress
to a static site, to verify that proper redirects and content
were migrated over.

By Jason Antman <jason@jasonantman.com> <http://blog.jasonantman.com>
LICENSE: GPLv3

The latest version of this script will always be available at:
<https://github.com/jantman/misc-scripts/blob/master/apache_log_verify_site_move.py>

If you have any modifications/improvements, please send me a patch
or a pull request.

CHANGELOG:

2014-01-01
  - initial version

"""
