#!/usr/bin/env python
"""
Python script to print a table with some statistics from each AWS region. Stats
include number of RDS instances, EC2 instances, volumes, snapshots, VPCs, and
AMIs, ECS clusters, ELBs and ASGs.

Should work with python 2.7-3.x. Requires ``boto3``from pypi.

The latest version of this script can be found at:
https://github.com/jantman/misc-scripts/blob/master/aws_region_stats.py

Copyright 2018 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2018-09-07 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys

try:
    import boto3
except ImportError:
    sys.stderr.write("ERROR: you must 'pip install boto3'.\n")
    raise SystemExit(1)

try:
    from terminaltables import AsciiTable
except ImportError:
    sys.stderr.write("ERROR: you must 'pip install terminaltables'.\n")
    raise SystemExit(1)


RESULT_KEYS = [
    'AMIs',
    'ASGs',
    'ECS Clusters',
    'ELB',
    'ELBv2',
    'Instances',
    'RDS Inst',
    'Snapshots',
    'VPCs',
    'Volumes'
]


def get_region_names():
    ec2 = boto3.client('ec2', region_name='us-east-1')
    return sorted([x['RegionName'] for x in ec2.describe_regions()['Regions']])


def get_account_id():
    client = boto3.client('sts')
    cid = client.get_caller_identity()
    return cid['Account']


def do_region(rname, acct_id):
    print('Checking region: %s' % rname)
    res = {x: 0 for x in RESULT_KEYS}
    # RDS
    rds = boto3.client('rds', region_name=rname)
    for r in rds.get_paginator('describe_db_instances').paginate():
        res['RDS Inst'] += len(r['DBInstances'])
    # ELBv2
    elbv2 = boto3.client('elbv2', region_name=rname)
    for r in elbv2.get_paginator('describe_load_balancers').paginate():
        res['ELBv2'] += len(r['LoadBalancers'])
    # ELB
    elb = boto3.client('elb', region_name=rname)
    for r in elb.get_paginator('describe_load_balancers').paginate():
        res['ELB'] += len(r['LoadBalancerDescriptions'])
    # ECS
    ecs = boto3.client('ecs', region_name=rname)
    for r in ecs.get_paginator('list_clusters').paginate():
        res['ECS Clusters'] += len(r['clusterArns'])
    # EC2
    ec2 = boto3.resource('ec2', region_name=rname)
    res['VPCs'] = len(list(ec2.vpcs.all()))
    res['Volumes'] = len(list(ec2.volumes.all()))
    res['Snapshots'] = len(list(ec2.snapshots.filter(OwnerIds=[acct_id])))
    res['Instances'] = len(list(ec2.instances.all()))
    res['AMIs'] = len(list(ec2.images.filter(Owners=['self'])))
    # AutoScaling
    autoscaling = boto3.client('autoscaling', region_name=rname)
    for r in autoscaling.get_paginator('describe_auto_scaling_groups').paginate():
        res['ASGs'] += len(r['AutoScalingGroups'])
    return res

headers = [k for k in RESULT_KEYS]
headers.insert(0, 'REGION')
tdata = [headers]
acct_id = get_account_id()
print('Found Account ID as: %s' % acct_id)
for rname in get_region_names():
    res = do_region(rname, acct_id)
    tmp = [rname]
    for k in RESULT_KEYS:
        tmp.append(res[k])
    tdata.append(tmp)
table = AsciiTable(tdata)
print(table.table)
