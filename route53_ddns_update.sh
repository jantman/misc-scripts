#!/bin/bash
#################################################
# Bash script to update Route53 dynamic DNS
#
# Assumes you already have cli53 (<https://github.com/barnybug/cli53>)
# installed and properly configured.
#
# Export ROUTE53_ZONE and ROUTE53_RR_NAME environment variables
# as your route53 Zone Id and Record Set name, respectively.
#
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
# * 2017-09-29 Jason Antman <jason@jasonantman.com>
# - switch from whatismyip.jasonantman.com to api.ipify.org
#
# * 2015-06-15 Jason Antman <jason@jasonantman.com>
# - get config from env vars instead of hard-coded
# - get OLD_WAN_IP from cli53 instead of local cache file
# - drop TTL to 60s
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

LOG_TAG=$(basename "$0")

log () {
    logger -p local7.info -t $LOG_TAG "$1"
}

log_err () {
    logger -p local7.notice -t $LOG_TAG "$1"
}

if [ -z ${ROUTE53_ZONE+x} ]
then
    >&2 echo "${LOG_TAG} - ERROR - ROUTE53_ZONE environment variable not set"
    log_err "ERROR - ROUTE53_ZONE environment variable not set"
    exit 1
fi

if [ -z ${ROUTE53_RR_NAME+x} ]
then
    >&2 echo "${LOG_TAG} - ERROR - ROUTE53_RR_NAME environment variable not set"
    log_err "ERROR - ROUTE53_RR_NAME environment variable not set"
    exit 1
fi

log "Running with ZONE=${ROUTE53_ZONE} RR=${ROUTE53_RR_NAME}"

WAN_IP=$(wget -q -O - --no-check-certificate https://api.ipify.org/)
log "Found current WAN IP as ${WAN_IP}"

# Get your old WAN IP
OLD_WAN_IP=$(cli53 rrlist $ROUTE53_ZONE | grep "^${ROUTE53_RR_NAME}[[:space:]]" | awk '{print $5}')
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
    cli53 rrdelete $ROUTE53_ZONE $ROUTE53_RR_NAME A 2>&1 | logger -p local7.info -t "${LOG_TAG}-rrdelete" || logger -p local7.notice -t $LOG_TAG "cli53 rrdelete FAILED."
    cli53 rrcreate $ROUTE53_ZONE $ROUTE53_RR_NAME A $WAN_IP --ttl 60 2>&1 | logger -p local7.info -t "${LOG_TAG}-rrcreate" && echo $WAN_IP > /var/CURRENT_WAN_IP.txt || logger -p local7.notice -t $LOG_TAG "cli53 rrcreate FAILED."
fi
