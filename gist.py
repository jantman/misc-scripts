#!/usr/bin/env python
"""
Python script to post a Gist of a file from
a common/shared computer. Prompts for auth
interactively.

This is largely based on Soren Bleikertz' simple
example at:
<http://bleikertz.com/blog/gist_python.html>

##################

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/gist.py>

CHANGELOG:

2015-02-05 jantman:
- initial script
"""

import httplib
import urllib
import re
import os.path
from optparse import OptionParser
import platform
import sys
import json

def gist_write(name, content, ext=None, token=None, prefix=False):
    if ext is None:
        ext = os.path.splitext(name)[1]

    if prefix:
        name = '{n}_{name}'.format(n=platform.node(), name=name)

    data = {
        'public': False,
        'files': {
            name: {
                'content': content
            }
        }
    }

    headers = {'User-Agent': 'https://github.com/jantman/misc-scripts/blob/master/gist.py'}
    if token is not None:
        headers['Authorization'] = 'token {t}'.format(t=token)

    conn = httplib.HTTPSConnection("api.github.com")
    conn.request("POST", "/gists", json.dumps(data), headers)
    response = conn.getresponse()
    ret = None
    if response.status == 403:
        sys.stderr.write("ERROR - 403\n")
        sys.stderr.write("Response:\n{d}\n".format(d=response.read()))
        sys.stderr.write("Headers:\n")
        for i in response.getheaders():
            sys.stderr.write('{k}: {v}\n'.format(k=i[0], v=i[1]))
        conn.close()
        raise SystemExit(1)
    elif response.status == 201:
        data = json.loads(response.read())
        ret = data['html_url']
    else:
        sys.stderr.write("Response status {s}\n".format(s=response.status))
        sys.stderr.write("Response:\n{d}\n".format(d=response.read()))
        sys.stderr.write("Headers:\n")
        for i in response.getheaders():
            sys.stderr.write('{k}: {v}\n'.format(k=i[0], v=i[1]))
        conn.close()
        raise SystemExit(1)
    conn.close()
    return ret 

usage = 'USAGE: gist.py [options] filename'
parser = OptionParser(usage=usage)
parser.add_option('-d', '--description', dest='description', action='store',
                  type=str, help='Gist description')
parser.add_option('-p', '--prefix', dest='prefix', action='store_false',
                  default=True,
                  help='prefix gist filename with hostname')
(options, args) = parser.parse_args()
if len(args) < 1:
    sys.stderr.write(usage + "\n")
    raise SystemExit(1)

if not os.path.exists(args[0]):
    sys.stderr.write("ERROR: {f} does not exist\n".format(f=args[0]))
    raise SystemExit(1)

token = raw_input("GitHub API Token: ").strip()
if token == '':
    sys.stderr.write("ERROR: empty token\n")
    raise SystemExit(1)

with open(args[0], 'r') as fh:
    content = fh.read()

name = args[0]
url = gist_write(name, content, token=token, prefix=options.prefix)
print("Created: {u}".format(u=url))
