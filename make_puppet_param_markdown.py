#!/usr/bin/env python
#
# Python script to generate MarkDown docblock fragment
# for all parameters of a Puppet parameterized class
# or define.
#
# Simple, naive regex matching. Assumes you style your manifests properly.
#

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

lines = []
in_params = False
with open(fname, 'r') as fh:
    for line in fh:
        line = line.strip()
        if not in_params and start_re.match(line):
            in_params = True
        elif in_params and end_re.match(line):
            break
        elif in_params:
            lines.append(line)

if len(lines) < 1:
    sys.stderr.write("ERROR: did not find any params in %s\n" % fname)
    sys.exit(1)

line_re = re.compile(r'\s*\$(?P<varname>\S+)(\s+=\s*(\S+))?,?$')
for line in lines:
    print line
    foo = line_re.match(line)
    print foo.groupdict()

