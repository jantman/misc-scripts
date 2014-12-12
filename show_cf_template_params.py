#!/usr/bin/env python
"""
Script to show CloudFormation template parameters and their values.

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/show_cf_template_params.py

CHANGELOG:

2014-12-05 jantman:
- initial script
"""

import json
import sys
import os

try:
    fname = sys.argv[1]
except IndexError:
    raise SystemExit("USAGE: show_cf_template_params.py /path/to/cloudformation.template")

if not os.path.exists(fname):
    raise SystemExit("ERROR: path does not exist: %s" % fname)

with open(fname, 'r') as fh:
    content = fh.read()

tmpl = json.loads(content)

params = tmpl['Parameters']

for p in sorted(params):
    if 'Default' in params[p]:
        print("{k}: {v}".format(k=p, v=params[p]['Default']))
    else:
        print("{k} (no default)".format(k=p))

