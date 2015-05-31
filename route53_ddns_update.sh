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
#
# * 2015-05-31 Jason Antman <jason@jasonantman.com>
# - update for new whatismyip.jasonantman.com
#
# * 2015-05-20 Jason Antman <jason@jasonantman.com>
# - fix bug in WAN_IP
# - add logging
#
# * 2014-12-26 Jason Antman <jason@jasonantman.com>
# - initial script
#
#################################################

# CONFIGURATION
ZONE=<SET THIS TO YOUR ROUTE53 ZONE ID>
RR=<SET THIS TO YOUR RR NAME>
# END CONFIGURATION

LOG_TAG=$(basename "$0")

log () {
    logger -p local7.info -t $LOG_TAG "$1"
}

log_err () {
    logger -p local7.notice -t $LOG_TAG "$1"
}

log "Running with ZONE=${ZONE} RR=${RR}"

WAN_IP=$(wget -O - -U wget/route53_ddns_update.sh/iponly 'http://whatismyip.jasonantman.com/?format=plain&only=ip')
log "Found current WAN IP as ${WAN_IP}"

# Get your old WAN IP
OLD_WAN_IP=$(cat /var/CURRENT_WAN_IP.txt)
log "Found old WAN IP as ${OLD_WAN_IP}"

# See if the new IP is the same as the old IP.
if [ "$WAN_IP" = "$OLD_WAN_IP" ]; then
    echo "IP Unchanged"
    log "IP is unchanged - exiting"
    # Don't do anything if th eIP didn't change
else
    # The IP changed
    log "Deleting current A record"
    set -o pipefail
    cli53 rrdelete $ZONE $RR A 2>&1 | logger -p local7.info -t "${LOG_TAG}-rrdelete" || logger -p local7.notice -t $LOG_TAG "cli53 rrdelete FAILED."
    cli53 rrcreate $ZONE $RR A $WAN_IP 2>&1 | logger -p local7.info -t "${LOG_TAG}-rrcreate" && echo $WAN_IP > /var/CURRENT_WAN_IP.txt || logger -p local7.notice -t $LOG_TAG "cli53 rrcreate FAILED."
fi
