#!/usr/bin/env python
"""
Script to generate a YouTube playlist from a puppet videos page
"""

import sys
import requests

try:
    from lxml import etree, html
except ImportError:
    try:
        # normal cElementTree install
        import cElementTree as etree
    except ImportError:
        try:
            # normal ElementTree install
            import elementtree.ElementTree as etree
        except ImportError:
            raise SystemExit("Failed to import ElementTree from any known place")


VIDEO_PAGE = 'https://puppetlabs.com/puppetconf-2015-videos-and-presentations'

def main():
    r = requests.get(VIDEO_PAGE)
    tree = html.fromstring(r.text)
    links = []
    for item in tree.iterlinks():
        element, attrib, link, pos = item
        if not link.startswith('https://puppetlabs.com/presentations/'):
            continue
        links.append(link)
    print("# Found %d links" % len(links))
    for link in links:
        do_link(link)

def do_link(link):
    r = requests.get(link)
    tree = html.fromstring(r.text)
    for item in tree.xpath('//iframe'):
        if 'src' in item.attrib and 'youtube.com' in item.attrib['src']:
            print(item.attrib['src'])

if __name__ == "__main__":
    main()
