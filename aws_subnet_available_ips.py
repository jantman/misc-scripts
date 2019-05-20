#!/usr/bin/env python
"""
Python script to list available IPs (or all IP usage) in a subnet.

Should work with python 2.7-3.5. Requires ``boto3`` and ``netaddr`` from pypi.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/aws_subnet_available_ips.py

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2018-02-21 Jason Antman <jason@jasonantman.com>:
  - update to take ENIs into account
2016-02-22 Jason Antman <jason@jasonantman.com>:
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

try:
    from netaddr import IPNetwork
except ImportError:
    raise SystemExit("This script requires netaddr. Please 'pip install netaddr'")

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger(__name__)


class AWSIPUsage:
    """Find AWS IP usage by subnet"""

    def __init__(self):
        """connect to AWS API"""
        logger.debug("Connecting to AWS API")
        self.ec2 = boto3.client('ec2')
        self.ec2_res = boto3.resource('ec2')
        logger.info("Connected to AWS API")

    def show_subnet_usage(self, query):
        """main entry point"""
        subnet = self._find_subnet(query)
        print("Found matching subnet: %s (%s) %s %s (%s IPs available)" % (
                    subnet['SubnetId'],
                    subnet['CidrBlock'],
                    subnet['AvailabilityZone'],
                    subnet.get('VpcId', ''),
                    subnet['AvailableIpAddressCount']
        ))
        avail_ips = int(subnet['AvailableIpAddressCount'])
        ips = self._ips_for_subnet(subnet['CidrBlock'])
        logger.debug("Network has %d IPs", len(ips))
        used_ips = self._find_used_ips(
            subnet['SubnetId'], subnet['CidrBlock'], ips
        )
        for ip in ips:
            print("%s\t%s" % (ip, used_ips.get(ip, '<unused>')))
        if len(used_ips) != (len(ips) - avail_ips):
            print("WARNING: number of available IPs found does not match the "
                  "number reported by the API. Other IPs may be in used by "
                  "services not checked by this script!")

    def _find_used_ips(self, subnet_id, cidr_block, ips):
        """given a CIDR block and a list of IPs in the subnet, return a dict
        of any used IPs, to the ID of the resource using them"""
        res = {}
        res.update(self._find_used_eni(subnet_id, cidr_block, ips))
        res.update(self._find_used_ec2(subnet_id, cidr_block, ips))
        return res

    def _find_used_ec2(self, subnet_id, cidr_block, ips):
        """find IPs in use by EC2 things"""
        res = {}
        res.update(self._find_used_ec2_instances(subnet_id, cidr_block, ips))
        return res

    def _find_used_eni(self, subnet_id, _, ips):
        """find IPs in use by ENIs"""
        res = {}
        logger.debug('Querying ENIs within the subnet')
        for eni in self.ec2_res.network_interfaces.filter(
            Filters=[{'Name': 'subnet-id', 'Values': [subnet_id]}]
        ):
            for ipaddr in eni.private_ip_addresses:
                res[ipaddr['PrivateIpAddress']] = '%s / %s' % (
                    eni.id, eni.description
                )
        return res

    def _find_used_ec2_instances(self, subnet_id, _, ips):
        """find IPs in use by EC2 instances"""
        res = {}
        logger.debug("Querying EC2 Instances within the subnet")
        paginator = self.ec2.get_paginator('describe_instances')
        # by network-interface.subnet-id
        resp = paginator.paginate(
            Filters=[{
                'Name': 'network-interface.subnet-id',
                'Values': [subnet_id]
            }]
        )
        for r in resp:
            for reservation in r['Reservations']:
                for inst in reservation['Instances']:
                    if inst['PrivateIpAddress'] in ips:
                        res[inst['PrivateIpAddress']] = inst['InstanceId']
                    elif inst['PublicIpAddress'] in ips:
                        res[inst['PublicIpAddress']] = inst['InstanceId']
                    else:
                        for ni in inst['NetworkInterfaces']:
                            if ni['PrivateIpAddress'] in ips:
                                res[inst['PrivateIpAddress']] = inst[
                                    'InstanceId'] + '/' + inst[
                                        'NetworkInterfaceId']
        # by subnet-id
        resp = paginator.paginate(
            Filters=[{
                'Name': 'subnet-id',
                'Values': [subnet_id]
            }]
        )
        for r in resp:
            for reservation in r['Reservations']:
                for inst in reservation['Instances']:
                    if inst['PrivateIpAddress'] in ips:
                        res[inst['PrivateIpAddress']] = inst['InstanceId']
                    elif inst['PublicIpAddress'] in ips:
                        res[inst['PublicIpAddress']] = inst['InstanceId']
                    else:
                        for ni in inst['NetworkInterfaces']:
                            if ni['PrivateIpAddress'] in ips:
                                res[inst['PrivateIpAddress']] = inst[
                                    'InstanceId'] + '/' + inst[
                                        'NetworkInterfaceId']
        return res

    def _ips_for_subnet(self, cidr):
        """return a list of all IPs in the subnet"""
        net = IPNetwork(cidr)
        ips = [str(x) for x in list(net[4:-1])]
        return ips

    def _find_subnet(self, query):
        """find a subnet by query (subnet ID or CIDR block)"""
        if re.match(r'^subnet-[a-fA-F0-9]+$', query):
            subnet = self._find_subnet_by_id(query)
        elif re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}', query):
            subnet = self._find_subnet_by_block(query)
        else:
            raise SystemExit(
                "ERROR: %s does not look like a subnet ID or CIDR block" % subnet
            )
        return subnet

    def _find_subnet_by_id(self, subnet_id):
        """find a subnet by subnet ID"""
        kwargs = {
            'SubnetIds': [subnet_id]
        }
        return self._find_classic_subnet(kwargs)

    def _find_subnet_by_block(self, cidr):
        """find a subnet by CIDR block"""
        kwargs = {
            'Filters': [
                {
                    'Name': 'cidrBlock',
                    'Values': [cidr]
                }
            ]
        }
        return self._find_classic_subnet(kwargs)

    def _find_classic_subnet(self, kwargs):
        """call describe_subnets passing kwargs"""
        logger.info("Querying for subnet")
        logger.debug("calling ec2.describe_subnets with args: %s", kwargs)
        try:
            subnets = self.ec2.describe_subnets(**kwargs)['Subnets']
        except ClientError:
            logger.debug("No Classic subnet found matching query.")
            return None
        logger.debug("Result: %s", subnets)
        if len(subnets) < 1:
            raise SystemExit("Error: 0 subnets found matching: %s" % kwargs)
        if len(subnets) > 1:
            raise SystemExit("Error: %s subnets found matching: %s" % (
                len(subnets), kwargs
            ))
        return subnets[0]

def parse_args(argv):
    """parse arguments/options"""
    p = argparse.ArgumentParser(description='Find AWS IP usage by subnet')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='verbose output.')
    p.add_argument('SUBNET_ID_OR_BLOCK', help='subnet_id or CIDR netmask')
    args = p.parse_args(argv)
    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    finder = AWSIPUsage()
    print(finder.show_subnet_usage(args.SUBNET_ID_OR_BLOCK))
