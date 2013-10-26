#!/bin/bash
#
# This is a very simple script to use Linode's HTTP API to update
# dynamic DNS. I use it on my Vyatta CE router to maintain dynamic
# dns for my home (dynamic IP) internet connection.
#
# Credit for this script goes to "Guspaz" on the Linode forums, who published it
# in his post at: <https://forum.linode.com/viewtopic.php?p=53727&sid=481e147062078fe2f9728de24baabc37#p53727>
#
# The most recent version of this script is available at:
# <https://github.com/jantman/misc-scripts/blob/master/linode_ddns_update.sh>
#
# Please read the inline comments for configuration.
#
# Running the script:
# the nicest way would be to run it via a hook for your WAN interface,
# or dhcp client. Personally I just cron it every 15 minutes and consider
# that to be acceptable enough. The script caches the current WAN IP on disk,
# so it will only call out to Linode's API when it changes.
#

# this command should return a string of only your WAN IP. I currently use a 
# simple PHP script on my web server, but you can modify as needed (or use this
# service of mine, so long as it doesn't become too popular...)
WAN_IP=`wget -O - -U wget/linode_ddns.sh/iponly http://whatismyip.jasonantman.com`

# Set LINODE_API_KEY to your API key, found on the Linode Manager site -
# click "my profile" at the top right, scroll down to "API Key"
LINODE_API_KEY="Put your API key here"

# the following are the domain and resource IDs for the record you want to update,
# as used in Linode's API. You can get these using the linode_list_records.py script
# in my same git repo, <https://github.com/jantman/misc-scripts/blob/master/linode_list_records.py>
DOMAIN_ID=0
RESOURCE_ID=0

# Get your old WAN IP
OLD_WAN_IP=`cat /var/CURRENT_WAN_IP.txt`

# See if the new IP is the same as the old IP.
if [ "$WAN_IP" = "$OLD_WAN_IP" ]; then
    echo "IP Unchanged"
    # Don't do anything if th eIP didn't change
else
    # The IP changed. Update Linode's DNS to show the new IP
    echo $WAN_IP > /var/CURRENT_WAN_IP.txt
    wget -qO- https://api.linode.com/?api_key="$LINODE_API_KEY"\&api_action=domain.resource.update\&DomainID="$DOMAIN_ID"\&ResourceID="$RESOURCE_ID"\&Target="$WAN_IP"
fi

