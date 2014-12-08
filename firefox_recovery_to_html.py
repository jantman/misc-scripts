#!/usr/bin/env python
"""
Script to convert Firefox profile sessionstore-backups/recovery.js to HTML links

Sometime in the late-20-something to early-30-something releases, Firefox stopped
writing its venerable sessionstore.js file inside profile directories, in favor
of a recovery.js file inside the sessionstore-backups/ directory. This script
parses that file and outputs HTML with a list of links for your open tabs.

Useful when sync is mishebaving.
"""

import os
import sys
import json
try:
    from html import escape  # py3
except ImportError:
    from cgi import escape  # py2

def usage():
    print("USAGE: firefox_recovery_to_html.py /path/to/profile_dir/sessionstore-backups/recovery.js")

if len(sys.argv) < 1:
    usage()
    raise SystemExit(1)

fpath = sys.argv[1]

if fpath == '--help' or fpath == '-h':
    usage()
    raise SystemExit()

if not os.path.exists(fpath):
    raise SystemExit("ERROR: file does not exist: %s" % fpath)

with open(fpath, 'r') as fh:
    raw = fh.read()

js = json.loads(raw)

"""
_closedWindows
windows
session
selectedWindow
global
"""

print('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">')
print('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>recovery.js tabs</title><meta http-equiv="Content-Type" content="text/html; charset=utf-8" />')
print('</head><body><ol>')
for i in js['windows']:
    for x in i['tabs']:
        tab = x['entries'][-1]
        print('<li><a href="{url}">{title}</a></li>'.format(title=tab['title'], url=escape(tab['url'])))
print('</ol></body></html>')
