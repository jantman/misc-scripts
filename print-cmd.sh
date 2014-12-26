#!/bin/bash
#
# Simple script to log environment variables and original command for forced ssh commands
#
# Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
# Free for any use provided that patches are submitted back to me.
#
# The latest version of this script can be found at:
# <https://github.com/jantman/misc-scripts/blob/master/print-cmd.sh>
#

echo "============`date`================\n" >> print-cmd.log
env >> print-cmd.log
