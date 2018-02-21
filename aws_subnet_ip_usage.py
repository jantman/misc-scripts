#!/usr/bin/env python
"""
Python script to find IP address usage in an AWS Subnet, and then estimate
usage with all resources scaled-out.

Currently calculates scale-out for:

* ASGs
* ELBs

Should work with python 2.7-3.6. Requires ``boto3`` and ``netaddr`` from pypi.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/aws_subnet_ip_usage.py

Copyright 2018 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2018-02-21 Jason Antman <jason@jasonantman.com>:
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
    raise SystemExit("This script requires boto3. Please 'pip install netaddr'")

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger(__name__)


ELB_MAX_IPS = 8
ENI_ELB_RE = re.compile(r'^eni-[a-f0-9]+ / ELB (.+)$')


class AWSIPUsage:
    """Find AWS IP usage by subnet"""

    def __init__(self):
        """connect to AWS API"""
        logger.debug("Connecting to AWS API")
        self.ec2 = boto3.client('ec2')
        self.ec2_res = boto3.resource('ec2')
        self.autoscaling = boto3.client('autoscaling')
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
        used_ips = {}
        eni_ips = self._find_used_eni(
            subnet['SubnetId'], subnet['CidrBlock'], ips
        )
        used_ips.update(eni_ips)
        ec2_ips = self._find_used_ec2_instances(
            subnet['SubnetId'], subnet['CidrBlock'], ips
        )
        used_ips.update(ec2_ips)
        print(
            "%d IP addresses used, out of %d total" % (len(used_ips), len(ips))
        )
        elb_count, elb_curr, elb_max = self._handle_elbs(
            used_ips, subnet['SubnetId']
        )
        print('Found %d ELBs currently using %d IPs; max IP usage is %d' % (
            elb_count, elb_curr, elb_max
        ))
        asg_count, asg_curr, asg_max = self._handle_asgs(
            used_ips, subnet['SubnetId'], ec2_ips
        )
        print(
            'Found %d ASGs with %d total instances in the subnet. Maximum '
            'total instances: %s' % (asg_count, asg_curr, asg_max)
        )
        if len(used_ips) != (len(ips) - avail_ips):
            print("WARNING: number of available IPs found does not match the "
                  "number reported by the API. Other IPs may be in used by "
                  "services not checked by this script!")
        print('Subnet has %d usable IPs, %d IPs in use. Theoretical '
              'maximum with all ELBs and ASGs fully scaled: %d' % (
                  len(ips), len(used_ips), len(used_ips) + elb_max + asg_max
              )
        )

    def _handle_elbs(self, ips, subnet_id):
        """
        Figure out the current number, and maximum number, of IPs for
        ELBs in the subnet.

        :returns: number of ELBs in subnet, count of ELB IPs currently in use
          in subnet, count of maximum ELB IPs in subnet
        :rtype: tuple
        """
        curr_ips = 0
        max_ips = 0
        elbnames = set()
        for ip, desc in ips.items():
            m = ENI_ELB_RE.match(desc)
            if m is None:
                continue
            elbname = m.group(1)
            logger.debug('IP %s is ENI (%s) for ELB "%s"', ip, desc, elbname)
            elbnames.add(elbname)
        for elbname in elbnames:
            elb_enis = list(self.ec2_res.network_interfaces.filter(Filters=[
                {'Name': 'description', 'Values': ['ELB %s' % elbname]},
                {'Name': 'subnet-id', 'Values': [subnet_id]}
            ]))
            logger.debug(
                'ELB "%s" appears to have %d ENIs currently',
                elbname, len(elb_enis)
            )
            curr_ips += len(elb_enis)
            max_ips += ELB_MAX_IPS
        return len(elbnames), curr_ips, max_ips

    def _handle_asgs(self, ips, subnet_id, ec2_ip_to_id):
        """
        Figure out the current number, and maximum number, of IPs for
        ASG instances in the subnet.

        :returns: Count of ASGs with instances in subnet, count of ASG instances
          currently in subnet, maximum number of ASG instances in subnet
        :rtype: tuplr
        """
        curr_ips = 0
        max_ips = 0
        count = 0
        paginator = self.autoscaling.get_paginator(
            'describe_auto_scaling_groups'
        )
        for page in paginator.paginate():
            for asg in page['AutoScalingGroups']:
                subnets = asg['VPCZoneIdentifier'].split(',')
                if subnet_id not in subnets:
                    continue
                for inst in asg['Instances']:
                    if inst['InstanceId'] in ec2_ip_to_id.values():
                        curr_ips += 1
                max_ips += asg['MaxSize'] - len(asg['Instances'])
                count += 1
        return count, curr_ips, max_ips

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
    finder.show_subnet_usage(args.SUBNET_ID_OR_BLOCK)
