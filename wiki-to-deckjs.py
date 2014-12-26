#!/usr/bin/env python2
"""
simple, awful script to change markdown-like (very restricted markup set) markup to deck.js-ready html

##################
Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/wiki-to-deckjs.py

CHANGELOG:
- initial version
"""

import sys
import re

ol_re = re.compile(r"^\d+\.\s(.*)")

in_slide = False
in_ul = False
in_2ul = False
in_ol = False
for line in sys.stdin:
    if line.strip() == "":
        if in_slide:
            if in_2ul:
                print "\t\t</ul>"
                in_2ul = False
            if in_ul:
                print "\t</ul>"
                in_ul = False
            if in_ol:
                print "\t</ol>"
                in_ol = False
            print '</section>'
            in_slide = False
            continue
    else:
        if not in_slide:
            in_slide = True
            print '<section class="slide">'

    if in_2ul and not line.startswith("** "):
        print "\t\t</ul>"
        in_2ul = False
    if in_ul and not line.startswith("* ") and not line.startswith("** ") and not in_2ul:
        print "\t</ul>"
        in_ul = False
    if in_ol and not ol_re.match(line):
        print "\t</ol>"
        in_ul = False

    if not in_slide:
        continue

    if line.startswith("# "):
        line = line[2:].strip()
        print "\t<h1>%s</h1>" % line
    elif line.startswith("## "):
        line = line[2:].strip()
        print "\t<h2>%s</h2>" % line
    elif line.startswith("* "):
        if not in_ul:
            print "\t<ul>"
            in_ul = True
        line = line[2:].strip()
        print "\t\t<li>%s</li>" % line
    elif line.startswith("** "):
        if not in_2ul:
            print "\t\t<ul>"
            in_2ul = True
        line = line[3:].strip()
        print "\t\t\t<li>%s</li>" % line
    elif ol_re.match(line):
        m = ol_re.match(line)
        if not in_ol:
            print "\t<ol>"
            in_ol = True
        print "\t\t<li>%s</li>" % m.group(1)
    else:
        #sys.stderr.write("UNKNOWN LINE: %s\n" % line)
        print "\t<p>%s</p>" % line.strip()

if in_2ul:
    print "\t\t</ul>"
    in_2ul = False
if in_ul:
    print "\t</ul>"
    in_ul = False

print '</section>'
# done
