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
import logging
from copy import deepcopy
from ssl import _create_unverified_context

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

def debug_response(response):
    logger.debug("Response status {s}".format(s=response.status))
    logger.debug("Response: {d}".format(d=response.read()))
    logger.debug("Headers: \n{h}".format(
        h='\n'.join(['{k}: {v}\n'.format(k=i[0], v=i[1]) for i in response.getheaders()])
    ))

def gist_write(name, content, token=None, prefix=False, no_verify=False):
    if prefix:
        name = '{n}_{name}'.format(n=platform.node(), name=name)
        logger.debug("Setting name to: {n}".format(n=name))

    data = {
        'public': False,
        'files': {
            name: {
                'content': content
            }
        }
    }

    # data debug
    d = deepcopy(data)
    if len(d['files'][name]['content']) > 800:
        tmp = d['files'][name]['content']
        d['files'][name]['content'] = tmp[:200] + "\n...\n" + tmp[-200:]
    logger.debug("POST data: {d}".format(d=d))
    headers = {'User-Agent': 'https://github.com/jantman/misc-scripts/blob/master/gist.py'}
    if token is not None:
        headers['Authorization'] = 'token {t}'.format(t=token)
        logger.debug("Setting Authorization header to: {h}".format(h=headers['Authorization']))

    if no_verify:
        conn = httplib.HTTPSConnection("api.github.com", context=_create_unverified_context())
    else:
        conn = httplib.HTTPSConnection("api.github.com")
    logger.debug("Opened connection to https://api.github.com")
    logger.debug("POSTing to /gists")
    conn.request("POST", "/gists", json.dumps(data), headers)
    response = conn.getresponse()
    debug_response(response)
    if response.status == 201:
        data = response.read()
        conn.close()
        try:
            d = json.loads(data)
            return(d['html_url'])
        except:
            pass
        logger.error("Got 201 status but no JSON response")
        logger.debug("Response: \n{d}".format(d=data))
        h = response.getheaders()
        for header in h:
            if header[0] == 'location':
                url = header[1].replace('api.github.com/gists/', 'gist.github.com/')
                return url
        return ''
    logger.error("ERROR - got response code {s}".format(s=response.status))
    conn.close()
    raise SystemExit(1)

usage = 'USAGE: gist.py [options] filename'
parser = OptionParser(usage=usage)
parser.add_option('-d', '--description', dest='description', action='store',
                  type=str, help='Gist description')
parser.add_option('-p', '--prefix', dest='prefix', action='store_false',
                  default=True,
                  help='prefix gist filename with hostname')
parser.add_option('-v', '--verbose', dest='verbose', action='store_true',
                  help='verbose output')
parser.add_option('-V', '--no-verify', dest='no_verify', action='store_true',
                  default=False, help='do not verify SSL')
(options, args) = parser.parse_args()

if options.verbose:
    logger.setLevel(logging.DEBUG)

if len(args) < 1:
    sys.stderr.write(usage + "\n")
    raise SystemExit(1)

if not os.path.exists(args[0]):
    logger.error("ERROR: {f} does not exist".format(f=args[0]))
    raise SystemExit(1)

token = raw_input("GitHub API Token: ").strip()
if token == '':
    logger.error("ERROR: empty token")
    raise SystemExit(1)

with open(args[0], 'r') as fh:
    content = fh.read()

name = args[0]
url = gist_write(name, content, token=token, prefix=options.prefix, no_verify=options.no_verify)
logger.info("Created: {u}".format(u=url))
