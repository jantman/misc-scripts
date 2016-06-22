#!/usr/bin/env python
"""
Script using skew (https://github.com/scopely-devops/skew) to list ALL
resources in an AWS account.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/list_all_aws_resources_skew.py>

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG:
2016-06-22 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys

try:
    from skew.arn import ARN
    from skew.exception import ConfigNotFoundError
    from skew import scan
except ImportError:
    raise Exception('You must "pip install skew" before using this script.')


try:
    arn = ARN()
except ConfigNotFoundError as ex:
    sys.stderr.write("Please create your skew config file per "
                     "<https://github.com/scopely-devops/skew>\n")
    raise ex

services=arn.service.choices()
services.sort()
print('Enumerating all resources in the following services: ' +
      ' '.join(services) + '\n')
for service in services:
    print('******' + service + '******')
    if service in ['iam', 'route53']:
        uri = 'arn:aws:%s::*:*' % service
    else:
        uri = 'arn:aws:%s:*:*:*/*' % service
    try:
        arn = scan(uri)
        for i in arn:
            id_str = None
            if hasattr(i, 'tags'):
                id_str = 'tags: %s' % i.tags
            print('%s %s' % (i.arn, id_str))
    except:
        print("=> Error scanning service: %s" % service)
