#!/usr/bin/env python
"""
Script to list instances in an ASG

Copyright 2014 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2016-06-07 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import boto3
import logging

FORMAT = "[%(levelname)s %(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(level=logging.WARN, format=FORMAT)
logger = logging.getLogger(__name__)


class ASGInstances:

    def __init__(self):
        self.autoscale = boto3.client('autoscaling')
        self.ec2 = boto3.resource('ec2')

    def run(self, asg_name):
        instances = self.get_instances(asg_name)
        for i in instances:
            self.show_instance(i)

    def show_instance(self, asg_dict):
        inst = self.ec2.Instance(asg_dict['InstanceId'])
        pub_info = ''
        if inst.public_ip_address is not None:
            pub_info = ' %s (%s)' % (
                inst.public_ip_address, inst.public_dns_name
            )

        print('%s (%s; %s; %s) %s (%s)%s' % (
            asg_dict['InstanceId'],
            asg_dict['AvailabilityZone'],
            asg_dict['HealthStatus'],
            asg_dict['LifecycleState'],
            inst.private_ip_address,
            inst.private_dns_name,
            pub_info
        ))

    def get_instances(self, asg_name):
        res = self.autoscale.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        if 'AutoScalingGroups' not in res or len(res['AutoScalingGroups']) < 1:
            raise SystemExit("Error: ASG %s not found." % asg_name)
        asg = res['AutoScalingGroups'][0]
        print('Found ASG %s (%s)' % (asg_name, asg['AutoScalingGroupARN']))
        return asg['Instances']


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='Sample python script skeleton.')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('ASG_NAME', action='store', type=str,
                   help='ASG name')
    args = p.parse_args(argv)

    return args

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif args.verbose > 0:
        logger.setLevel(logging.INFO)
    script = ASGInstances()
    script.run(args.ASG_NAME)
