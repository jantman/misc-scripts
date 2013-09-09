#!/usr/bin/env python2
"""
simple, awful script to change markdown-like (very restricted markup set) markup to deck.js-ready html
"""

import sys

in_slide = False
in_ul = False
in_2ul = False
for line in sys.stdin:
    if line.strip() == "":
        if in_slide:
            if in_2ul:
                print "\t\t</ul>"
                in_2ul = False
            if in_ul:
                print "\t</ul>"
                in_ul = False
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
"""
	<h2>Cluster Architecture</h2>
	<object data="graphite_data2.svg" type="image/svg+xml"></object>
</section>
"""
