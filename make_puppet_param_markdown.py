#!/usr/bin/env python
#
# Python script to generate MarkDown docblock fragment
# for all parameters of a Puppet parameterized class
# or define.
#
# Simple, naive regex matching. Assumes you style your manifests properly.
#
##################
# Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
# Free for any use provided that patches are submitted back to me.
#
# The latest version of this script can be found at:
# <https://github.com/jantman/misc-scripts/blob/master/make_puppet_param_markdown.py>
#
# CHANGELOG:
# 2014-02-06 Jason Antman <jason@jasonantman.com>:
#   - initial script
##########################################################################################
    

import os.path
import re
import sys

if len(sys.argv) < 2 or len(sys.argv) > 3:
    sys.stderr.write("USAGE: make_puppet_param_markdown.py /path/to/manifest.pp\n")
    sys.exit(1)

fname = sys.argv[1]

if not os.path.exists(fname):
    sys.stderr.write("ERROR: %s does not appear to exist\n" % fname)
    sys.exit(1)

start_re = re.compile(r'^\s*(define|class).*\($')
end_re = re.compile(r'.*{$')
comment_re = re.compile(r'^\s*#')

lines = []
in_params = False
with open(fname, 'r') as fh:
    for line in fh:
        line = line.strip()
        if comment_re.match(line):
            continue
        if not in_params and start_re.match(line):
            in_params = True
        elif in_params and end_re.match(line):
            break
        elif in_params:
            lines.append(line)

if len(lines) < 1:
    sys.stderr.write("ERROR: did not find any params in %s\n" % fname)
    sys.exit(1)

line_re = re.compile(r'\s*\$(?P<varname>\S+)(\s+=\s*(?P<val>\S+.*))?,?$')
for line in lines:
    foo = line_re.match(line)
    d = foo.groupdict()
    print("# [*%s*]" % d['varname'].strip(', '))
    print("#   ()")
    if 'val' in d and d['val'] is not None:
        print("#   (optional; default: %s)" % d['val'].strip(', '))
    else:
        print("#   (required)")
    print("#")
