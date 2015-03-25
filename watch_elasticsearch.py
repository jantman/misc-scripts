#!/usr/bin/env python
"""
Python script to watch an ElasticSearch cluster's status
and exit/notify when the status changes

requirements:
pip install elasticsearch
pip install python-pushover (optional)

for pushover configuration, see the section on ~/.pushoverrc in the Configuration section:
http://pythonhosted.org/python-pushover/#configuration

##################

Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/watch_elasticsearch.py

CHANGELOG:

2015-02-04 jantman:
- initial script

2015-03-25 jantman:
- add unassigned shard count to output
"""

import sys
import optparse
import logging
import re
import time
import os
import datetime

from elasticsearch import Elasticsearch

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.ERROR, format=FORMAT)
logger = logging.getLogger(__name__)

try:
    from pushover import init, Client, get_sounds
    have_pushover = True
except ImportError:
    logger.warning("Pushover support disabled; `pip install python-pushover` to enable it")
    have_pushover = False

def main(host, port, sleeptime=10, pushover=False):
    if pushover and not have_pushover:
        raise SystemExit("ERROR: to use pushover notifications, please `pip install python-pushover` and configure it.")

    es = Elasticsearch([{'host': host, 'port': port}])
    if not es.ping():
        logger.critical("Unable to ping ES cluster at {h}:{p}".format(
            h=self.host,
            p=self.port
        ))
        raise SystemExit(1)

    status = cluster_status(es)
    while True:
        try:
            s = cluster_status(es)
        except Exception as ex:
            logger.error("Exception getting ES cluster health")
            logger.exception(ex)
            time.sleep(sleeptime)
            continue
        logger.debug("Got cluster status: status={s} timed_out={t} "
                     "initializing_shards={i} relocating_shards={r}"
                     " unassigned_shards={u}".format(
                         s=s['status'],
                         t=s['timed_out'],
                         i=s['initializing_shards'],
                         r=s['relocating_shards'],
                         u=s['unassigned_shards']))
        if s['timed_out'] != status['timed_out']:
            change = "Cluster timed_out changed from {o} to {n}".format(
                o=status['timed_out'],
                n=s['timed_out'])
            logger.info(change)
            break
        if s['status'] != status['status']:
            change = "Cluster status changed from {o} to {n}".format(
                o=status['status'],
                n=s['status'])
            logger.info(change)
            break
        status = s
        time.sleep(sleeptime)

    msg = '{h}:{p} {c} (shards: {i} initializing, {r} relocating, {u} unassigned)'.format(h=host,
                                                                                          p=port,
                                                                                          c=change,
                                                                                          i=s['initializing_shards'],
                                                                                          r=s['relocating_shards'],
                                                                                          u=s['unassigned_shards'])
    if s['status'] == 'green' and not s['timed_out']:
        # I got better!
        logger.info(msg)
        if pushover:
            notify_pushover(True, msg)
        raise SystemExit(0)
    else:
        # health got worse
        logger.error(msg)
        if pushover:
            notify_pushover(False, msg)
        raise SystemExit(1)

def cluster_status(es):
    """ get cluster status """
    h = es.cluster.health()
    # {u'status': u'yellow', u'number_of_nodes': 1, u'unassigned_shards': 315, u'timed_out': False, u'active_primary_shards': 315, u'cluster_name': u'elasticsearch', u'relocating_shards': 0, u'active_shards': 315, u'initializing_shards': 0, u'number_of_data_nodes': 1}
    return {
        'initializing_shards': h['initializing_shards'],
        'relocating_shards': h['relocating_shards'],
        'timed_out': h['timed_out'],
        'status': h['status'],
        'unassigned_shards': h['unassigned_shards'],
    }

def notify_pushover(is_success, msg):
    """ send notification via pushover """
    if is_success:
        req = Client().send_message(msg, priority=0)
    else:
        req = Client().send_message(msg, priority=0, sound='falling')
    
def parse_args(argv):
    """ parse arguments/options """
    p = optparse.OptionParser(usage="usage: %prog [options] stack_name")

    p.add_option('-v', '--verbose', dest='verbose', action='store_true', default=False,
                 help='verbose (debugging) output')
    p.add_option('-s', '--sleep-time', dest='sleeptime', action='store', type=int, default=10,
                 help='time in seconds to sleep between status checks; default 10')
    p.add_option('-H', '--host', dest='host', action='store', type=str, default='127.0.0.1',
                 help="ElasticSearch cluster host IP or DNS (default: 127.0.0.1)")
    p.add_option('-P', '--port', dest='port', action='store', type=int, default=9200,
                 help='ElasticSearch cluster port (default: 9200)')
    push_default = False
    if os.path.exists(os.path.expanduser('~/.watch_jenkins_pushover')):
        push_default = True
    p.add_option('-p', '--pushover', dest='pushover', action='store_true', default=push_default,
                 help='notify on completion via pushover (default {p}; touch ~/.watch_jenkins_pushover to default to True)'.format(p=push_default))

    options, args = p.parse_args(argv)

    return options, args


if __name__ == "__main__":
    opts, args = parse_args(sys.argv[1:])

    if opts.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    main(opts.host, opts.port, sleeptime=opts.sleeptime, pushover=opts.pushover)
