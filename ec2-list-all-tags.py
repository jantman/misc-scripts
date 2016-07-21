#!/usr/bin/env python
"""
Using boto3, list all distinct tag names on all EC2 instances in all regions.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/ec2-list-all-tags.py>

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2016-07-21 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

from boto3 import resource, client


def get_region_names():
    conn = client('ec2')
    res = conn.describe_regions()
    regions = []
    for r in res['Regions']:
        regions.append(r['RegionName'])
    return regions


def tags_for_region(region_name):
    tags = set()
    res = resource('ec2', region_name=region_name)
    count = 0
    for i in res.instances.all():
        count += 1
        if i.tags is None:
            continue
        for t in i.tags:
            tags.add(t['Key'])
    print('Examined %d instances in %s'% (count, region_name))
    return tags


def main():
    tags = set()
    regions = get_region_names()
    for r in regions:
        tags.update(tags_for_region(r))
    print('Found %d distinct tag names:' % len(tags))
    for t in sorted(tags):
        print(t)

if __name__ == "__main__":
    main()
