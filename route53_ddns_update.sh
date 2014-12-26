#!/bin/bash
#################################################
# Bash script to update Route53 dynamic DNS
#
# Assumes you already have cli53 (<https://github.com/barnybug/cli53>)
# installed and properly configured.
#
#################################################
# Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
# Free for any use provided that patches are submitted back to me.
#
# The latest version of this script can be found at:
# <https://github.com/jantman/misc-scripts/blob/master/route53_ddns_update.sh>
#
# CHANGELOG:
# - initial script
#################################################

WAN_IP=`wget -O - -U wget/route53_ddns_update.sh/iponly http://whatismyip.jasonantman.com`

ZONE=
RR=apt

# Get your old WAN IP
OLD_WAN_IP=`cat /var/CURRENT_WAN_IP.txt`

# See if the new IP is the same as the old IP.
if [ "$WAN_IP" = "$OLD_WAN_IP" ]; then
    echo "IP Unchanged"
    # Don't do anything if th eIP didn't change
else
    # The IP changed
    cli53 rrdelete $ZONE $RR A
    cli53 rrcreate $ZONE $RR A $WAN_IP && echo $WAN_IP > /var/CURRENT_WAN_IP.txt
fi
