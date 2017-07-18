#!/usr/bin/env python
"""
aws_find_duplicate_sgs.py
==========================

Script using boto3 to identify duplicate Security Groups in EC2.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/aws_find_duplicate_sgs.py>

License
-------

Copyright 2017 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG
---------

2017-07-18 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import boto3
from datetime import datetime
import json
from collections import defaultdict

__author__ = 'jason@jasonantman.com'
__src_url__ = 'https://github.com/jantman/misc-scripts/blob/master' \
              '/aws_find_duplicate_sgs.py'

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

# suppress boto3 internal logging below WARNING level
boto3_log = logging.getLogger("boto3")
boto3_log.setLevel(logging.WARNING)
boto3_log.propagate = True

# suppress botocore internal logging below WARNING level
botocore_log = logging.getLogger("botocore")
botocore_log.setLevel(logging.WARNING)
botocore_log.propagate = True


class SGWrapper(object):
    """Class to wrap a boto3 ec2.SecurityGroup, for comparing based on rules"""

    def __init__(self, sg):
        """
        :param sg: boto3 EC2 SecurityGroup object
        :type sg: boto3.resources.factory.ec2.SecurityGroup
        """
        self._sg_obj = sg
        self.id = sg.id
        self.name = sg.group_name
        self.vpc_id = sg.vpc_id
        self.owner_id = sg.owner_id
        self.ip_permissions = self._sort_perms(sg.ip_permissions)
        self.ip_permissions_egress = self._sort_perms(sg.ip_permissions_egress)

    def _sort_perms(self, perms):
        """sort IP Permissions lists for comparison"""
        result = []
        for item in perms:
            res = {}
            for k in item.keys():
                if k in [
                    'IpRanges', 'Ipv6Ranges', 'PrefixListIds', 'UserIdGroupPairs'
                ]:
                    res[k] = sorted(item[k])
                else:
                    res[k] = item[k]
            result.append(res)
        return sorted(result)

    def comp_repr(self):
        d = {
            'vpc_id': self.vpc_id,
            'owner_id': self.owner_id,
            'IpPermissions': self.ip_permissions,
            'IpPermissionsEgress': self.ip_permissions_egress
        }
        return json.dumps(d, sort_keys=True, indent=4, separators=(',', ': '))

    def equals(self, other):
        if other.vpc_id != self.vpc_id:
            logger.debug('%s != %s (vpc_id)', self.id, other.id)
            return False
        if other.owner_id != self.owner_id:
            logger.debug('%s != %s (owner_id)', self.id, other.id)
            return False
        if other.ip_permissions != self.ip_permissions:
            logger.debug('%s != %s (ip_permissions)', self.id, other.id)
            return False
        if other.ip_permissions_egress != self.ip_permissions_egress:
            logger.debug('%s != %s (ip_permissions_egress)', self.id, other.id)
            return False
        return True


class DupeSGFinder(object):
    """Identify duplicate Security Groups in EC2"""


    def __init__(self):
        self._rules = []

    def run(self, vpc_id=None):
        groups = self._get_groups(vpc_id)
        dupes = defaultdict(set)
        print('Output generated at %s by: %s' % (
            datetime.now().strftime('%c'), __src_url__
        ))
        for k1, v1 in groups.items():
            for k2, v2 in groups.items():
                if k1 == k2:
                    continue
                if v1.equals(v2):
                    dupes[k2].add(k1)
                    dupes[k1].add(k2)
        # remove dupes in the list itself
        result = {}
        for k, v in dupes.items():
            l = sorted(list(v) + [k])
            if l[0] not in result:
                result[l[0]] = l[1:]
        print('Found %d Security Groups with at least 1 '
              'duplicate.' % len(result.keys()))
        num_dupes = sum([len(v) for v in result.values()])
        print('De-duplication would remove %d SGs' % num_dupes)
        print('Duplicated SGs:')
        for k, v in sorted(
            result.items(), key=lambda (k, v): len(v), reverse=True
        ):
            print("%s: %d dupes: %s" % (k, len(result[k]), list(result[k])))
            print(groups[k].comp_repr())

    def _get_groups(self, vpc_id=None):
        groups = {}
        logger.debug('Connecting to EC2 API')
        ec2 = boto3.resource('ec2')
        if vpc_id is None:
            _suffix = 'account'
            sg_iter = ec2.security_groups.all()
        else:
            _suffix = 'VPC %s' % vpc_id
            sg_iter = ec2.security_groups.filter(Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]}
            ])
        logger.debug('Listing all EC2 SGs in %s', _suffix)
        num_groups = 0
        for g in sg_iter:
            num_groups += 1
            groups[g.id] = SGWrapper(g)
        logger.info('Found %d SGs in %s', num_groups, _suffix)
        return groups

def parse_args(argv):
    p = argparse.ArgumentParser(description='Identify duplicate EC2 SGs')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-V', '--vpc-id', dest='vpc_id', action='store', type=str,
                   default=None, help='Single VPC ID to limit to')
    args = p.parse_args(argv)
    return args

def set_log_info():
    """set logger level to INFO"""
    set_log_level_format(logging.INFO,
                         '%(asctime)s %(levelname)s:%(name)s:%(message)s')


def set_log_debug():
    """set logger level to DEBUG, and debug-level output format"""
    set_log_level_format(
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(level, format):
    """
    Set logger level and format.

    :param level: logging level; see the :py:mod:`logging` constants.
    :type level: int
    :param format: logging formatter format string
    :type format: str
    """
    formatter = logging.Formatter(fmt=format)
    logger.handlers[0].setFormatter(formatter)
    logger.setLevel(level)

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    elif args.verbose == 1:
        set_log_info()

    DupeSGFinder().run(vpc_id=args.vpc_id)
