#!/usr/bin/env python
"""
Test of using the LibVirt Python bindings to gather
information about libvirt (qemu/KVM) guests.

test on opskvmtie13

##################
Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/libvirt_csv.py>

CHANGELOG:
- initial script
"""

import libvirt
import sys

if len(sys.argv) > 1:
    hostname = sys.argv[1]
else:
    print("USAGE: test_libvirt.py <hostname> <...>")
    sys.exit(1)

DOM_STATES = {
    libvirt.VIR_DOMAIN_NOSTATE: 'no state',
    libvirt.VIR_DOMAIN_RUNNING: 'running',
    libvirt.VIR_DOMAIN_BLOCKED: 'blocked on resource',
    libvirt.VIR_DOMAIN_PAUSED: 'paused by user',
    libvirt.VIR_DOMAIN_SHUTDOWN: 'being shut down',
    libvirt.VIR_DOMAIN_SHUTOFF: 'shut off',
    libvirt.VIR_DOMAIN_CRASHED: 'crashed',
    libvirt.VIR_DOMAIN_PMSUSPENDED: 'suspended by guest power mgmt',
}

# bitwise or of all possible flags to virConnectListAllDomains
ALL_OPTS = 16383

def bool(a):
    if a == 0:
        return False
    return True

def get_domains(conn):
    """
    Takes a libvirt connection object,
    returns a list of all domains, each element
    being a dict with items "name", "ID", "UUID", 
    """
    domains = conn.listAllDomains(ALL_OPTS)
    ret = []
    for d in domains:
        foo = {}
        foo['name'] = d.name()
        foo['ID'] = d.ID()
        foo['UUID'] = d.UUIDString().upper()
        [state, maxmem, mem, ncpu, cputime] = d.info()
        foo['state'] = DOM_STATES.get(state, state)
        ret.append(foo)
    return ret

hosts = sys.argv
hosts.pop(0)

print("host,name,ID,state,UUID")

for h in hosts:
    uri = "qemu+ssh://%s/system" % h
    #print("Using hostname: %s (URI: %s)" % (h, uri))

    try:
        conn = libvirt.openReadOnly(uri)
    except libvirt.libvirtError as e:
        print("ERROR connecting to %s: %s" % (uri, e.message))
        continue

    # some code examples imply that older versions
    # returned None instead of raising an exception
    if conn is None:
        print("ERROR connecting to %s: %s" % (uri, e.message))
        continue

    doms = get_domains(conn)
    for d in doms:
        print("{host},{name},{ID},{state},{UUID}".format(host=h, name=d['name'], ID=d['ID'], UUID=d['UUID'], state=d['state']))
