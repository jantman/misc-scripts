#!/usr/bin/env python
"""
Python script using requests and BeautifulSoup4 to request all URLs/links/images/CSS/feeds/etc. found on a domain.

Used to ensure full apache logs for apache_log_verify_site_move.py

By Jason Antman <jason@jasonantman.com> <http://blog.jasonantman.com>
LICENSE: GPLv3

The latest version of this script will always be available at:
<https://github.com/jantman/misc-scripts/blob/master/scrape_domain.py>

If you have any modifications/improvements, please send me a patch
or a pull request.

CHANGELOG:

2014-01-01
  - initial version

"""

import sys
import optparse
import re
import time

import requests
import lxml.html

# yeah, I'm bad and lazy. I'm using globals for this.
DONE = []
TODO = []
ASSET_DONE = []
ASSET_TODO = []

DOMAIN_RE = None

def parse_page(url, content, domain, strip_qs=False, strip_anchors=False, verbose=False):
    """
    - parse page content with beautifulsoup
    - pull out any a href links, append them to TODO if not
      already there or in DONE
    - pull out any asset links (images, css, feeds, etc.) and
      append them to ASSET_TODO if not already there or in
      ASSET_DONE
    """
    global DOMAIN_RE

    doc = lxml.html.fromstring(content)
    doc.make_links_absolute(url)

    hrefs = doc.xpath('//a/@href')
    appended = 0
    for href in hrefs:
        #print("+++ found a href: %s" % href) # TODO this should be DEBUG not VERBOSE
        if DOMAIN_RE.match(href):
            # TODO - implement strip_qs and strip_anchors here
            if href not in DONE and href not in TODO:
                print("++++ append a href to todo: %s" % href) # TODO this should be DEBUG not VERBOSE
                TODO.append(href)
                appended = appended + 1
    print("+++ Found %d a href's, appended %d new ones." % (len(hrefs), appended))

    # images, css, feeds, scripts, etc.
    appended = 0
    found_items = 0
    for xp in ['//img/@src', '//link/@href', '//script/@src']:
        items = doc.xpath(xp)
        found_items = found_items + len(items)
        for item in items:
            #print("+++ found asset: %s" % item) # TODO this should be DEBUG not VERBOSE
            if DOMAIN_RE.match(item):
                # TODO - implement strip_qs and strip_anchors here
                if item not in ASSET_DONE and item not in ASSET_TODO:
                    print("++++ append asset to todo: %s" % item) # TODO this should be DEBUG not VERBOSE
                    ASSET_TODO.append(item)
                    appended = appended + 1
    print("+++ Found %d assets, appended %d new ones." % (found_items, appended))
    return True

def do_page(url, domain, strip_qs=False, strip_anchors=False, verbose=False):
    """
    Request a page. If it returns 200, pass the content
    on to parse_page; else just print a message.

    Either way, remove the url from TODO and append to DONE.
    """
    res = requests.get(url)
    if verbose:
        print("+ page %s" % url)
    if res.status_code != 200:
        print("++ returned status %s, moving on" % res.status_code)
    else:
        parse_page(url, res.content, domain, strip_qs, strip_anchors, verbose)
    DONE.append(url)
    TODO.remove(url)
    return True

def do_asset(url, domain, verbose=False):
    """
    Request an asset. Remove it from TODO and append to DONE.
    """
    r = requests.get(url)
    ASSET_DONE.append(url)
    ASSET_TODO.remove(url)

def crawl(domain, sleep=0.0, limit=0, strip_qs=False, strip_anchors=False, verbose=False):
    """
    Crawl all pages in the TODO list until it's empty.
    Print a short report about each page crawled.
    """
    global DOMAIN_RE
    DOMAIN_RE = re.compile(r'^http://' + domain)
    TODO.append('http://%s/' % domain)
    count = 0
    while len(TODO) > 0:
        do_page(TODO[0], domain, strip_qs, strip_anchors, verbose)
        count = count + 1
        print("Pages: %d TODO, %d DONE - Assets: %d TODO" % (len(TODO), len(DONE), len(ASSET_TODO)))
        if limit > 0 and count > limit:
            print("Reached limit of %d, break." % limit)
            break
        if sleep > 0:
            time.sleep(sleep)
    print("= Done with pages, starting assets")
    count = 0
    while len(ASSET_TODO) > 0:
        do_asset(ASSET_TODO[0], domain, verbose)
        count = count + 1
        print("Assets: %d TODO %d DONE" % (len(ASSET_TODO), len(ASSET_DONE)))
        if limit > 0 and count > limit:
            print("Reached limit of %d, break." % limit)
            break
        if sleep > 0:
            time.sleep(sleep)
    print("Done.")

def parse_opts(argv):
    """
    Parse command-line options.

    :param argv: sys.argv or similar list
    :rtype: optparse.Values
    """
    parser = optparse.OptionParser()
    parser.add_option('-d', '--domain', dest='domain',
                      help='domain to crawl (and limit crawl to)')
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False,
                      help='verbose output')
    parser.add_option('-s', '--sleep', dest='sleep', action='store', type='float', default=0.0,
                      help='time to sleep between requests (float; default 0)')
    parser.add_option('-l', '--limit', dest='limit', action='store', type='int', default=0,
                      help='limit to this (int) number of pages and assets (each); 0 for no limit')
    parser.add_option('--strip-qs', dest='strip_qs', action='store_true', default=False,
                      help='strip query strings from URLs (? and everything after; default false)')
    parser.add_option('--strip-anchors', dest='strip_anchors', action='store_true', default=False,
                      help='strip anchors from URLs (default False)')

    options, args = parser.parse_args(argv)

    if not options.domain:
        print("ERROR: domain to crawl must be specified with -d|--domain")
        sys.exit(1)

    return options

def main():
    """
    Main method
    """
    opts = parse_opts(sys.argv[1:])

    crawl(opts.domain, opts.sleep, opts.limit, opts.strip_qs, opts.strip_anchors, opts.verbose)

if __name__ == "__main__":
    main()
