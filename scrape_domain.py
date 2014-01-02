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

import requests
from bs4 import BeautifulSoup

# yeah, I'm bad and lazy. I'm using globals for this.
DONE = []
TODO = []
ASSET_DONE = []
ASSET_TODO = []

DOMAIN_RE = None

def parse_page(content, domain, verbose=False):
    """
    - parse page content with beautifulsoup
    - pull out any a href links, append them to TODO if not
      already there or in DONE
    - pull out any asset links (images, css, feeds, etc.) and
      append them to ASSET_TODO if not already there or in
      ASSET_DONE
    """
    global DOMAIN_RE

    bs = BeautifulSoup(content, "lxml")

    # links
    for l in bs.find_all('a'):
        try:
            href = l.get('href')
        except:
            continue
        #print("+++ found link: %s" % href) # TODO this should be DEBUG not VERBOSE
        if DOMAIN_RE.match(href):
            if href not in DONE and href not in TODO:
                print("++++ append link to todo: %s" % href) # TODO this should be DEBUG not VERBOSE
                TODO.append(href)

    # images
    for i in bs.find_all('img'):
        try:
            src = i.get('src')
        except:
            continue
        print("+++ found img src: %s" % src) # TODO this should be DEBUG not VERBOSE
        if DOMAIN_RE.match(src):
            if src not in ASSET_DONE and src not in ASSET_TODO:
                print("++++ asset src to todo: %s" % src) # TODO this should be DEBUG not VERBOSE
                ASSET_TODO.append(src)

    # css
    # feeds
    return True

def do_page(url, domain, verbose=False):
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
        parse_page(res.content, domain, verbose)
    DONE.append(url)
    TODO.remove(url)
    return True

def crawl(domain, verbose=False):
    """
    Crawl all pages in the TODO list until it's empty.
    Print a short report about each page crawled.
    """
    global DOMAIN_RE
    DOMAIN_RE = re.compile(r'^http://' + domain)
    TODO.append('http://%s/' % domain)
    while len(TODO) > 0:
        do_page(TODO[0], domain, verbose)
        print("Pages: %d TODO, %d DONE - Assets: %d TODO" % (len(TODO), len(DONE), len(ASSET_TODO)))
        break # DEBUG
    print("= Done with pages, starting assets")
    while len(ASSET_TODO) > 0:
        do_asset(ASSET_TODO[0], domain, verbose)
        print("Assets: %d TODO %d DONE" % (len(ASSET_TODO), len(ASSET_DONE)))
        break # DEBUG
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

    crawl(opts.domain, opts.verbose)

if __name__ == "__main__":
    main()
