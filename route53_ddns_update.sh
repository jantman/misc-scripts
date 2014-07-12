#!/bin/bash

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
