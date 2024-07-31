#!/usr/bin/env python
"""
Script to report on updated Docker images, using data from GLPI and FusionInventory.

NOTE: This requires my GLPI Docker image <https://github.com/jantman/docker-glpi>
or for you to patch GLPI's src/Inventory/Inventory.php as I do in that image.

Using an installation of GLPI <https://glpi-project.org/> that is running
FusionInventory Agent <https://fusioninventory.org/> 2.6 or later for inventory
collection, connect to the GLPI API and retrieve information on all discovered
Docker containers and their image versions. When possible, find the age of the
running image and the age of the newest image and their comparative versions.
Generate a report with all of this information, optionally emailing it via SES.

Tested Versions
---------------

Tested with GLPI 10.0.9 using v0.1.0 of my Docker image <https://github.com/jantman/docker-glpi>,
and FusionInventory Agent 2.6.1.

Authentication
--------------

If you have not yet set up API access aside from the default (localhost):

    1. Log in as a super-admin (default creds glpi/glpi)
    2. In the left menu browse to Setup -> General
    3. Click the "Add API client" button
    4. Add a new client, making sure to set Active to Yes and Regenerate under
       Application token is NOT checked.

Then, for your user:

1. Log in to GLPI as your user
2. Click your user icon in the top right and then "My settings"
3. If you don't already have an API token, click the "Regenerate" checkbox and then Save.
4. Copy the value of the "API token" box, and export it as the ``GLPI_API_TOKEN`` environment variable while running this script.

Source
------

https://github.com/jantman/misc-scripts/blob/master/glpi_docker_update_report.py

Dependencies
------------

Python 3+
requests

License
-------

MIT license. Copyright 2024 Jason Antman.
"""

import os
import sys
import argparse
import logging
from typing import Optional, Dict
import json

import requests

logging.basicConfig(
    level=logging.WARNING,
    format="[%(asctime)s %(levelname)s] %(message)s"
)
logger: logging.Logger = logging.getLogger()


class GlpiDockerReport:

    TOKEN_FILE: str = '.glpi_token.json'

    def __init__(self):
        if (api_url := os.environ.get('GLPI_API_URL')) is None:
            raise RuntimeError(
                'ERROR: You must set the GLPI_API_URL environment variable '
                'to the root URL for GLPI, i.e. something like '
                'http://127.0.0.1:8088/; to confirm this: log in to '
                'GLPI as a super-admin, browse to Setup -> General in the left '
                'menu, and copy the value in the "URL of the API" text box '
                'WITHOUT anything after the port number.'
            )
        if (api_token := os.environ.get('GLPI_API_TOKEN')) is None:
            raise RuntimeError(
                'ERROR: You must set the GLPI_API_TOKEN environment variable '
                'to your GLPI API user token. See the docstring at the top of '
                'this script for details.'
            )
        self._api_url: str = api_url
        if not self._api_url.endswith('/'):
            self._api_url += '/'
        self._api_url += 'apirest.php/'
        logger.debug('API URL: %s', self._api_url)
        self._api_token: str = api_token
        self._session_token: str = ''
        self._sess: requests.Session = requests.Session()
        self._login()

    def _login(self, once: bool = False):
        sess_token: Optional[str] = self._load_token()
        if not sess_token:
            url = self._api_url + 'initSession'
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'user_token {self._api_token}'
            }
            logger.debug('GET %s with headers %s', url, headers)
            r = requests.get(url, headers=headers)
            logger.debug(
                'API returned HTTP %d headers=%s body=%s',
                r.status_code, r.headers, r.text
            )
            r.raise_for_status()
            sess_token = r.json()['session_token']
        self._sess.headers.update({
            'Session-Token': sess_token,
            'Content-Type': 'application/json'
        })
        url = self._api_url + 'getMyProfiles'
        logger.debug('GET %s', url)
        r = self._sess.get(url)
        if r.status_code != 200:
            logger.debug(
                'Returned HTTP %d: headers=%s body=%s',
                r.status_code, r.headers, r.text
            )
            if once:
                raise RuntimeError('ERROR: re-login failed!')
            os.unlink(self.TOKEN_FILE)
            self._login(once=True)
        self._save_token()
        self._session_token = sess_token
        self._computer_names: Dict[int, str] = {}  # computer ID to name
        #: Computer ID: { Container Name: Image}
        self._containers_by_comp: Dict[int, Dict[str, str]] = {}

    def _load_token(self) -> Optional[str]:
        try:
            with open(self.TOKEN_FILE, 'r') as fh:
                logger.debug('Loading session token from: %s', self.TOKEN_FILE)
                return fh.read().strip()
        except Exception as ex:
            logger.debug(
                'Could not load session token from %s: %s',
                self.TOKEN_FILE, ex
            )
        return None

    def _save_token(self):
        with open(self.TOKEN_FILE, 'w') as fh:
            fh.write(self._api_token)
        logger.debug('Wrote session token to: %s', self.TOKEN_FILE)

    def _api_get_json(self, path: str) -> dict:
        url = self._api_url + path
        logger.debug('GET: %s', url)
        r = self._sess.get(url)
        r.raise_for_status()
        return r.json()

    def run(self):
        self._get_glpi_data()
        print(json.dumps(
            {
                self._computer_names[x]: self._containers_by_comp[x]
                for x in sorted(self._containers_by_comp.keys())
            },
            sort_keys=True, indent=4
        ))

    def _get_glpi_data(self):
        comp: dict
        for comp in self._api_get_json('Computer/?expand_dropdowns=true'):
            if comp.get('is_deleted', 0) == 1:
                logger.info(
                    'Skip deleted computer %d (%s)',
                    comp['id'], comp['name']
                )
                continue
            if comp.get('is_template', 0) == 1:
                logger.debug(
                    'Skip deleted computer %d (%s)',
                    comp['id'], comp['name']
                )
                continue
            logger.info('Computer %d (%s)', comp['id'], comp['name'])
            self._computer_names[comp['id']] = comp['name']
            self._containers_by_comp[comp['id']] = {}
            self._do_computer(comp['id'])

    def _do_computer(self, comp_id: int):
        vm: dict
        for vm in self._api_get_json(f'Computer/{comp_id}/ComputerVirtualMachine/?expand_dropdowns=true'):
            if vm.get('virtualmachinetypes_id') != 'docker':
                logger.debug(
                    'Skip VM with type %s: %d name=%s (comment %s)',
                    vm.get('virtualmachinetypes_id'),
                    vm['id'], vm['name'], vm['comment']
                )
                continue
            if vm.get('is_deleted', 0) == 1:
                logger.debug(
                    'Skip deleted VM %d name=%s (comment %s)',
                    vm['id'], vm['name'], vm['comment']
                )
                continue
            if vm.get('virtualmachinestates_id') != 'running':
                logger.debug(
                    'Skip VM %d name=%s (comment %s) in state %s',
                    vm['id'], vm['name'], vm['comment'],
                    vm.get('virtualmachinestates_id')
                )
                continue
            self._containers_by_comp[comp_id][vm['name']] = vm['comment']
        logger.info(
            'Found %d containers on Computer %s',
            len(self._containers_by_comp[comp_id]), comp_id
        )


def parse_args(argv):
    p = argparse.ArgumentParser(description='GLPI Docker Images Report')
    p.add_argument(
        '-v', '--verbose', dest='verbose', action='store_true',
        default=False, help='verbose output'
    )
    args = p.parse_args(argv)
    return args


def set_log_info(l: logging.Logger):
    """set logger level to INFO"""
    set_log_level_format(
        l,
        logging.INFO,
        '%(asctime)s %(levelname)s:%(name)s:%(message)s'
    )


def set_log_debug(l: logging.Logger):
    """set logger level to DEBUG, and debug-level output format"""
    set_log_level_format(
        l,
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(lgr: logging.Logger, level: int, fmt: str):
    """Set logger level and format."""
    formatter = logging.Formatter(fmt=fmt)
    lgr.handlers[0].setFormatter(formatter)
    lgr.setLevel(level)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose:
        set_log_debug(logger)
    else:
        set_log_info(logger)

    GlpiDockerReport().run()
