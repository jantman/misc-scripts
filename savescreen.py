#!/usr/bin/env python
#
# screen history saving script - saves your current windows and their titles,
# then appends this to ~/.screenrc and writes the result to ~/.screenrc.save
#
# This is intended to be run on a regular basis; I cron it every minute.
#
# WARNING - this expects only one screen session to be running as your user.
#
# Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
# Use this however you want; send changes back to me please.
#
# The canonical version of this script is available at:
#  <https://github.com/jantman/misc-scripts/blob/master/savescreen.py>
#
# CHANGELOG:
# 2014-07-24
#   * first public version
#
# 2014-07-25
#   * restored windows should go to their last PWD, set in ~/.bashrc
#     (see <http://blog.jasonantman.com/2014/07/session-save-and-restore-with-bash-and-gnu-screen/>)
#
####################################################

import subprocess
import re
import os.path
from platform import node
from datetime import datetime
import sys

# TODO: if I change anything else in this script, switch to optparse and logging
verbose = False
if '-v' in sys.argv or '--verbose' in sys.argv:
    verbose = True

# get the window list
windowstr = subprocess.check_output(['screen', '-Q', 'windows']).decode()
#windowstr = '0$ root  1$ blog  2$ blog-venv  3$ themes  4$ plugins  5$ writing  6$ temp/rm_me/blog_logs  7-$ bash  8*$ bash'
if verbose:
    print("windowstr: ={w}=".format(w=windowstr))

windows = {}

m = True
windowre = re.compile(r'(\s?(\d+)[-\*]?\$\s+(\S+)\s*)')
max_window = 0
# loop over the window list, extract substrings matching a window specifier
while m is not None:
    if verbose:
        print("LOOP windowstr={w}=".format(w=windowstr))
    m = windowre.match(windowstr)
    if m is None:
        if len(windows) == 0:
            if verbose:
                print("no match and no windows yet; trimming windowstr and continuing")
            windowstr = windowstr[1:]
            m = True
            continue
        else:
            if verbose:
                print("no match, breaking out of loop - windowstr: {w}".format(w=windowstr))
            break
    g = m.groups()
    windowstr = windowstr[len(g[0]):]
    if verbose:
        print("found match: {a} = {b}".format(a=g[1], b=g[2]))
    windows[int(g[1])] = g[2]
    if int(g[1]) > max_window:
        max_window = int(g[1])

if verbose:
    print(windows)

# read in screenrc
with open(os.path.join(os.path.expanduser('~'), '.screenrc'), 'r') as fh:
    screenrc = fh.read()

# get rid of the first "local 0" line if it's there
screenrc = screenrc.replace("screen -t local 0\n", "")

# write it out to the save location, with the windows added
dirpath = os.path.join(os.path.expanduser('~'), '.screendirs')
with open(os.path.join(os.path.expanduser('~'), '.screenrc.save'), 'w') as fh:
    fh.write(screenrc)
    fh.write("\n\n")
    fh.write("# .screenrc.save generated on %s at %s\n" % (node(), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    for n in range(0, max_window + 1):
        if n in windows:
            fh.write("screen -t \"{name}\" {num} sh -c \"cd $(readlink -fn {dirpath}/{num}); bash\"\n".format(name=windows[n], num=n, dirpath=dirpath))
        else:
            fh.write("screen -t \"{name}\" {num} sh -c \"cd $(readlink -fn {dirpath}/{num}); bash\"\n".format(name='bash', num=n, dirpath=dirpath))
    fh.write("\n")
# done
