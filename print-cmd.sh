#!/bin/bash
#
# Simple script to log environment variables and original command for forced ssh commands
#
# by Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
#
# $HeadURL$
# $LastChangedRevision$
#

echo "============`date`================\n" >> print-cmd.log
env >> print-cmd.log
