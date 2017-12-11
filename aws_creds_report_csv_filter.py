#!/usr/bin/env python
"""
Script to iterate over an AWS IAM Credentials Report CSV file, and output
a similar file containing only entries with a credential older than the
--older-than-days option and/or last used more than --last-used-days ago.

Requirements:

* Python >= 3.2
* ``python-dateutil`` package
* ``humanize`` package

"""
import sys
import os
import csv
import argparse
try:
    from datetime import datetime, timedelta, timezone
except ImportError:
    sys.stderr.write("ERROR: Requires python >= 3.2\n")
    raise SystemExit(1)
try:
    from humanize import naturaltime
except ImportError:
    sys.stderr.write("Please 'pip install humanize'\n")
    raise SystemExit(1)
try:
    from dateutil.parser import parse
except ImportError:
    sys.stderr.write("Please 'pip install python-dateutil'\n")
    raise SystemExit(1)


class AwsCredsReportFilter(object):

    def __init__(self, csv_path):
        if not os.path.exists(csv_path):
            raise RuntimeError('CSV_PATH does not exist: %s' % csv_path)
        self._csv_path = csv_path
        self.now = datetime.utcnow().replace(tzinfo=timezone.utc)

    def nt(self, dt):
        if not isinstance(dt, datetime):
            dt = dt_for_field(dt)
        if dt is None:
            return None
        return naturaltime(self.now - dt)

    def run(self, older_than=None, last_used=None, summary=False):
        if older_than is not None:
            older_than = self.now - timedelta(days=older_than)
        if last_used is not None:
            last_used = self.now - timedelta(days=last_used)
        results = []
        with open(self._csv_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                dt_min_created, dt_min_used = self._min_dates_for_row(row)
                if older_than is not None:
                    if (
                        dt_min_created is not None and
                        dt_min_created > older_than
                    ):
                        continue
                    if dt_min_created is None:
                        continue
                if last_used is not None:
                    if (
                        dt_min_used is not None and
                        dt_min_used > last_used
                    ):
                        continue
                    if dt_min_used is None:
                        continue
                results.append(row)
        if not summary:
            fieldnames = list(results[0].keys())
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow(r)
            return
        # else we want a summary
        for row in results:
            print('%s (%s) created %s (%s)' %(
                row['user'], row['arn'], self.nt(row['user_creation_time']),
                row['user_creation_time']
            ))
            if row['password_enabled'] == 'true':
                print('\tPassword enabled; last changed %s (%s) last used %s '
                      '(%s)' % (
                    self.nt(row['password_last_changed']),
                    row['password_last_changed'],
                    self.nt(row['password_last_used']),
                    row['password_last_used']
                ))
            for key_num in [1, 2]:
                if row['access_key_%d_active' % key_num] != 'true':
                    continue
                print(
                    '\tAccess Key %d created %s (%s) last used %s (%s) with %s in '
                    '%s' % (
                        key_num,
                        self.nt(row['access_key_%d_last_rotated' % key_num]),
                        row['access_key_%d_last_rotated' % key_num],
                        self.nt(row['access_key_%d_last_used_date' % key_num]),
                        row['access_key_%d_last_used_date' % key_num],
                        row['access_key_%d_last_used_service' % key_num],
                        row['access_key_%d_last_used_region' % key_num]
                    )
                )
            for cert_num in [1, 2]:
                if row['cert_%d_active' % cert_num] != 'true':
                    continue
                print('\tCert %d last rotated %s (%s)' % (
                    cert_num,
                    self.nt(row['cert_%d_last_rotated' % cert_num]),
                    row['cert_%d_last_rotated' % cert_num]
                ))

    def _min_dates_for_row(self, row):
        min_create = None
        min_used = None
        creation_fields = [
            'password_last_changed',
            'cert_1_last_rotated',
            'access_key_1_last_rotated',
            'access_key_2_last_rotated',
            'cert_2_last_rotated'
        ]
        used_fields = [
            'password_last_used',
            'access_key_1_last_used_date',
            'access_key_2_last_used_date'
        ]
        for fname in creation_fields:
            f_dt = dt_for_field(row[fname])
            if f_dt is None:
                continue
            if min_create is None:
                min_create = f_dt
            elif f_dt < min_create:
                min_create = f_dt
        for fname in used_fields:
            f_dt = dt_for_field(row[fname])
            if f_dt is None:
                continue
            if min_used is None:
                min_used = f_dt
            elif f_dt < min_used:
                min_used = f_dt
        return min_create, min_used


def dt_for_field(f):
    if f == 'N/A':
        return None
    try:
        return parse(f)
    except Exception:
        return None


if __name__ == "__main__":
    p = argparse.ArgumentParser(description='filter AWS credential report CSV')
    p.add_argument('--older-than-days', '-o', dest='older_than_days', type=int,
                   action='store', default=None,
                   help='filter to users with password or creds older than '
                        'this number of days')
    p.add_argument('--last-used-days', '-l', dest='last_used_days', type=int,
                   action='store', default=None,
                   help='filter to users with password or creds last used '
                        'more than this number of days ago')
    p.add_argument('--summary', '-s', dest='summary', action='store_true',
                   default=False,
                   help='instead of outputting CSV, output a per-user summary')
    p.add_argument('CSV_PATH', type=str, action='store', help='CSV file path')
    args = p.parse_args(sys.argv[1:])
    AwsCredsReportFilter(args.CSV_PATH).run(
        older_than=args.older_than_days, last_used=args.last_used_days,
        summary=args.summary
    )
