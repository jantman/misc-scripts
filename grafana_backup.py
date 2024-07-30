#!/usr/bin/env python
"""
Script to dump backups of all Grafana dashboards and alerts, retrieved via API.

MIT license. Copyright 2023-2024 Jason Antman.

Canonical source:

https://github.com/jantman/misc-scripts/blob/master/grafana_backup.py
"""

import sys
import argparse
import logging
import requests
import os
from urllib.parse import urljoin
from typing import List, Dict
import json

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class GrafanaBackup:

    def __init__(self, base_url: str, outdir: str = './'):
        self.outdir: str = os.path.abspath(outdir)
        logger.info('Writing output to: %s', self.outdir)
        self._base_url: str = base_url
        logger.info('Running against: %s', self._base_url)
        self.sess: requests.Session = requests.Session()
        self.sess.headers.update({
            'Authorization': f'Bearer {os.environ["GRAFANA_KEY"]}'
        })

    def _get_paginated_json_list(
        self, path: str, limit: int = 1000
    ) -> List[dict]:
        result: list = []
        page_num = 1
        while True:
            url: str = urljoin(
                self._base_url, f'{path}&limit={limit}&page={page_num}'
            )
            logger.debug('GET %s', url)
            r = self.sess.get(url)
            logger.debug('HTTP %d: %d bytes', r.status_code, len(r.content))
            r.raise_for_status()
            tmp: list = r.json()
            result.extend(tmp)
            logger.debug('Got %d items; %d items total', len(tmp), len(result))
            if len(tmp) < limit:
                return result
            page_num += 1
        return result

    def _get(self, path: str) -> Dict:
        url: str = urljoin(self._base_url, path)
        logger.debug('GET %s', url)
        r = self.sess.get(url)
        logger.debug('HTTP %d: %d bytes', r.status_code, len(r.content))
        r.raise_for_status()
        return r.json()

    def _get_dashboards(self):
        items: List[dict] = self._get_paginated_json_list('/api/search?query=')
        folder_paths: Dict[int, str] = {
            0: os.path.join(self.outdir, 'dashboards')  # General (default)
        }
        logger.debug('makedirs: %s', folder_paths[0])
        os.makedirs(folder_paths[0], exist_ok=True)
        for folder in sorted(items, key=lambda x: x['id']):
            if folder['type'] != 'dash-folder':
                continue
            if folder.get('folderId'):
                folder_paths[folder['id']] = os.path.join(
                    folder_paths[folder['folderId']], folder['title']
                )
            else:
                folder_paths[folder['id']] = os.path.join(
                    self.outdir, 'dashboards', folder['title']
                )
            logger.debug('makedirs: %s', folder_paths[folder['id']])
            os.makedirs(folder_paths[folder['id']], exist_ok=True)
        for dash in items:
            if dash['type'] != 'dash-db':
                continue
            db = self._get(f'/api/dashboards/uid/{dash["uid"]}')
            path: str = os.path.join(
                folder_paths[dash.get('folderId', 0)],
                f'{dash["title"]}.json'
            )
            logger.info('Write dashboard %s to %s', dash['uid'], path)
            with open(path, 'w') as fh:
                json.dump(db, fh, sort_keys=True, indent=4)

    def _get_alert_rules(self):
        alerts = self._get(f'/api/ruler/grafana/api/v1/rules?subtype=cortex')
        rulecount: int = 0
        for foldername, groups in alerts.items():
            for group in groups:
                groupname = group['name']
                for rule in group['rules']:
                    outdir = os.path.join(
                        self.outdir, 'alert_rules', foldername, groupname
                    )
                    logger.debug('makedirs: %s', outdir)
                    os.makedirs(outdir, exist_ok=True)
                    path = os.path.join(
                        outdir, f'{rule["grafana_alert"]["title"]}.json'
                    )
                    logger.info('Write: %s', path)
                    with open(path, 'w') as fh:
                        json.dump(rule, fh, sort_keys=True, indent=4)
                    rulecount += 1
        logger.info('Saved %d rules', rulecount)

    def _get_to_json_file(self, path: str, filename: str):
        data = self._get(path)
        p: str = os.path.join(self.outdir, f'{filename}.json')
        logger.info('Write: %s', p)
        with open(p, 'w') as fh:
            json.dump(data, fh, sort_keys=True, indent=4)

    def run(self):
        self._get_dashboards()
        self._get_alert_rules()
        self._get_to_json_file(
            '/api/v1/provisioning/contact-points', 'contact-points'
        )
        self._get_to_json_file(
            '/api/v1/provisioning/policies', 'notification-policies'
        )
        self._get_to_json_file(
            '/api/v1/provisioning/mute-timings', 'mute-timings'
        )
        self._get_to_json_file(
            '/api/v1/provisioning/templates', 'templates'
        )


def parse_args(argv):
    p = argparse.ArgumentParser(description='Grafana backup')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='debug-level output.')
    p.add_argument('-o', '--outdir', dest='outdir', action='store',
                   type=str, default='./',
                   help='Output directory; default: ./')
    p.add_argument('URL', action='store', type=str,
                   default='http://localhost:3000',
                   help='Grafana URL; default: http://localhost:3000')
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
    if args.verbose:
        set_log_debug()
    else:
        set_log_info()
    GrafanaBackup(args.URL, outdir=args.outdir).run()
