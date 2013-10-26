#!/usr/bin/env python
#
# Simple script to list all records in Linode DNS via API,
# along with their Domain ID and Record ID
#
# Copyright 2013 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
#
# This requires the requests and json packages.
#
#

import sys
import requests
import json

if len(sys.argv) < 2 or sys.argv[1] == "-h" or sys.argv[1] == "--help":
    print("USAGE: linode_list_records.py <API Key>")
    sys.exit(1)

API_Key = sys.argv[1]
sys.stderr.write("Using API Key: %s\n" % API_Key)

URL_BASE = "https://api.linode.com/?api_key=%s" % API_Key

r = requests.get("%s&api_action=domain.list" % URL_BASE)
if r.status_code != 200:
    sys.stderr.write("ERROR: API Request for domain.list failed with HTTP code %s\n" % r.status_code)
    sys.exit(2)
domains = r.json()

print("domain,resource,type,DomainID,ResourceID")

for domain in domains['DATA']:
    d_name = domain['DOMAIN']
    d_id = domain['DOMAINID']

    r = requests.get("%s&api_action=domain.resource.list&DomainID=%d" % (URL_BASE, d_id))
    if r.status_code != 200:
        sys.stderr.write("ERROR: API Request for domain.resource.list with DomainID %d failed with HTTP code %s\n" % (d_id, r.status_code))
        sys.exit(2)
    resources = r.json()
    for res in resources['DATA']:
        print ("%s,%s,%s,%d,%d" % (d_name, res['NAME'], res['TYPE'], d_id, res['RESOURCEID']))
