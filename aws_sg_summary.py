#!/usr/bin/env python
"""
Python script to print a summary of all SGs in the current account/region,
their rules, and what's in them. Output in markdown.

Should work with python 2.7-3.6. Requires ``boto3``from pypi.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/aws_sg_summary.py

Copyright 2018 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2018-03-26 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
import re

try:
    import boto3
except ImportError:
    raise SystemExit("This script requires boto3. Please 'pip install boto3'")
from botocore.exceptions import ClientError

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - " \
         "%(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger(__name__)


DEFAULT_EGRESS = [
    {
        'IpProtocol': '-1',
        'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
        'Ipv6Ranges': [],
        'PrefixListIds': [],
        'UserIdGroupPairs': []
    }
]


class AWSSgSummary:
    """AWS Security Group Summary"""

    def __init__(self):
        """connect to AWS API"""
        logger.debug("Connecting to AWS API")
        self.ec2 = boto3.client('ec2')
        self.ec2_res = boto3.resource('ec2')
        logger.info("Connected to AWS API")
        self.interfaces = {}
        self.acct_id = None
        self._acct_info()

    def _acct_info(self):
        try:
            iam = boto3.client('iam')
            alias = iam.list_account_aliases()['AccountAliases'][0]
        except Exception:
            alias = ''
        sts = boto3.client('sts')
        self.acct_id = sts.get_caller_identity()['Account']
        print('## %s (%s) %s\n' % (
            self.acct_id, alias, sts._client_config.region_name
        ))

    def run(self):
        sgs = {}
        for sg in self.ec2_res.security_groups.all():
            sgs[sg.id] = {
                'id': sg.id,
                'name': sg.group_name,
                'description': sg.description,
                'ip_permissions': sg.ip_permissions,
                'ip_permissions_egress': sg.ip_permissions_egress,
                'vpc_id': sg.vpc_id,
                'tags': sg.tags,
                'interfaces': []
            }
        for ni in self.ec2_res.network_interfaces.all():
            self.interfaces[ni.id] = {
                'id': ni.id,
                'description': ni.description,
                'vpc_id': ni.vpc_id,
                'attachment': ni.attachment,
                'interface_type': ni.interface_type,
                'groups': ni.groups
            }
            for sg in ni.groups:
                if sg['GroupId'] in sgs:
                    sgs[sg['GroupId']]['interfaces'].append(ni.id)
                else:
                    logger.warning(
                        '%s has unknown SG %s', ni.id, sg
                    )
        for sg_id, sg in sgs.items():
            self.sg_markdown(sg)

    def sg_markdown(self, sg):
        print('### %s - %s ("%s") %s\n' % (
            sg['id'], sg['name'], sg['description'], sg['vpc_id']
        ))
        if sg['tags'] is not None:
            print('Tags:\n')
            for t in sorted(sg['tags'], key=lambda x: x['Key']):
                print('* "%s": "%s"' % (t['Key'], t['Value']))
            print('')
        print('#### Ingress\n')
        for r in sg['ip_permissions']:
            self.sg_rule_markdown(r, 'from')
        print('')
        print('#### Egress\n')
        if sg['ip_permissions_egress'] == DEFAULT_EGRESS:
            print('* DEFAULT (allow all egress)')
        else:
            for r in sg['ip_permissions_egress']:
                self.sg_rule_markdown(r, 'to')
        print('')
        print('#### Network Interfaces\n')
        for i in sg['interfaces']:
            print('* %s - %s (%s)' % (
                self.interfaces[i]['id'],
                self.interfaces[i].get('description', ''),
                self.interfaces[i].get(
                    'attachment', {}
                ).get('InstanceOwnerId', '')
            ))
        print('')

    def sg_rule_markdown(self, rule, direction):
        if 'FromPort' not in rule:
            rule['FromPort'] = 'ALL'
        if 'ToPort' not in rule:
            rule['ToPort'] = 'ALL'
        to = []
        for i in rule.get('IpRanges', []):
            if 'Description' in i:
                to.append('%s (%s)' % (i['CidrIp'], i['Description']))
            else:
                to.append(i['CidrIp'])
        for i in rule.get('Ipv6Ranges', []):
            if 'Description' in i:
                to.append('%s (%s)' % (i['CidrIpv6'], i['Description']))
            else:
                to.append(i['CidrIpv6'])
        for i in rule.get('PrefixListIds', []):
            if 'Description' in i:
                to.append('%s (%s)' % (i['PrefixListId'], i['Description']))
            else:
                to.append(i['PrefixListId'])
        for i in rule.get('UserIdGroupPairs', []):
            to.append(self.sg_useridgroup_str(i))
        s = '* %s port %s to port %s ' % (
            rule['IpProtocol'] if rule['IpProtocol'] != '-1' else 'ALL',
            rule['FromPort'] if rule['FromPort'] != '-1' else 'ALL',
            rule['ToPort'] if rule['ToPort'] != '-1' else 'ALL'
        )
        if len(to) == 1:
            print(s + direction + ' ' + to[0])
            return
        s += direction + ':\n'
        s += '\n'.join(
            ['  * %s' % x for x in to]
        )
        print(s)

    def sg_useridgroup_str(self, g):
        suffix = ''
        if 'Description' in g:
            suffix = ' (%s)' % g['Description']
        if g['UserId'] == self.acct_id:
            return g['GroupId'] + suffix
        return '%s/%s%s' % (g['UserId'], g['UserId'], suffix)


def parse_args(argv):
    """parse arguments/options"""
    p = argparse.ArgumentParser(description='AWS Security Group Summary')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='verbose output.')
    args = p.parse_args(argv)
    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    AWSSgSummary().run()
