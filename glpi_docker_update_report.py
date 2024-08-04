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

Python 3.11 or newer (tested with 3.12)
requests (tested with 2.32.3)
python-dateutil (tested with 2.9.0)
humanize (tested with 4.9.0)
github3.py (tested with 4.0.1)

License
-------

MIT license. Copyright 2024 Jason Antman.
"""

import os
import sys
import argparse
import logging
from typing import Optional, Dict, List, Union
from time import time, sleep
from datetime import datetime, timezone, timedelta
import re
from collections import defaultdict
import json

import requests
from dateutil.parser import parse
from humanize import naturaldelta
from github3 import GitHub


logging.basicConfig(
    level=logging.WARNING,
    format="[%(asctime)s %(levelname)s] %(message)s"
)
logger: logging.Logger = logging.getLogger()

SEMVER_ANYWHERE_RE: re.Pattern = re.compile(r'^.*\d+\.\d+\.\d+.*$')

UNKNOWN_DATE: datetime = datetime.fromtimestamp(1, tz=timezone.utc)

NOW: datetime = datetime.now(tz=timezone.utc)

GH: GitHub = GitHub(token=os.environ['GITHUB_TOKEN'])


class Image:

    def __init__(self, name: str, namespace: str, repository: str):
        self.name: str = name
        self.namespace: str = namespace
        self.repository: str = repository
        self.image_versions: Dict[str, 'ImageVersion'] = {}
        self.tag_dates: Dict[str, datetime] = {}
        self.newest_tag: Optional[str] = None
        self.newest_version_tag: Optional[str] = None

    def version(self, tag: str) -> 'ImageVersion':
        if tag not in self.image_versions:
            self.image_versions[tag] = ImageVersion(self, tag)
        return self.image_versions[tag]

    @property
    def link(self) -> str:
        return ''

    def link_for_tag(self, tag: str) -> str:
        return ''

    def update(self):
        raise NotImplementedError()


class DockerHubImage(Image):

    def _do_get(self, url: str) -> requests.Response:
        logger.debug('GET %s', url)
        r = requests.get(url)
        if r.status_code == 429:
            logger.debug(
                'Rate limited (429). Headers: %s', r.headers
            )
            retry_after = r.headers['Retry-After']
            logger.error(
                'Docker rate limiting; GET returned HTTP 429, '
                'X-Retry-After %s',
                retry_after
            )
            retry_ts = int(retry_after)
            now = time()
            duration = retry_ts - now
            logger.error(
                'Rate limiting: sleeping for %s seconds', duration
            )
            sleep(duration)
            return self._do_get(url)
        r.raise_for_status()
        return r

    @property
    def link(self) -> str:
        return ('https://hub.docker.com/repository/docker'
                f'/{self.namespace}/{self.repository}/')

    def link_for_tag(self, tag: str) -> str:
        return (f'https://hub.docker.com/r/{self.namespace}/{self.repository}'
                f'/tags?name={tag}')

    def update(self):
        logger.info(
            'Finding newest tag info for Docker Hub image: %s',
            self.name
        )
        url = (f'https://hub.docker.com/v2/namespaces/{self.namespace}/'
               f'repositories/{self.repository}/tags?page_size=100')
        # The Docker API returns tags in order, newest to oldest. Page through
        # tags 100 at a time until we find the newest tag AND the newest
        # semver-looking tag, or until we run out...
        while True:
            resp = self._do_get(url).json()
            if not self.newest_tag:
                self.newest_tag = resp['results'][0]['name']
                self.tag_dates[resp['results'][0]['name']] = parse(
                    resp['results'][0]['tag_last_pushed']
                )
                logger.info(
                    'Found newest tag as: %s at %s',
                    self.newest_tag, self.tag_dates[self.newest_tag]
                )
            if not self.newest_version_tag:
                for tag in resp['results']:
                    if SEMVER_ANYWHERE_RE.match(tag['name']):
                        self.newest_version_tag = tag['name']
                        self.tag_dates[tag['name']] = parse(tag['tag_last_pushed'])
                        logger.info(
                            'Found newest semver tag as: %s at %s',
                            self.newest_version_tag,
                            self.tag_dates[self.newest_version_tag]
                        )
                        break
            if self.newest_tag and self.newest_version_tag:
                break
            if not resp['next']:
                break
            url = resp['next']
        # ok, we should have newest tag and newest version tag if they exist
        logger.info(
            'Updating in-use tag info for Docker Hub image: %s',
            self.name
        )
        # now we fill in data for the tags we have in use
        iver: ImageVersion
        for iver in self.image_versions.values():
            url = (
                f'https://hub.docker.com/v2/namespaces/{self.namespace}/'
                f'repositories/{self.repository}/tags/{iver.tag}'
            )
            resp = self._do_get(url).json()
            self.tag_dates[iver.tag] = parse(resp['tag_last_pushed'])
            iver.tag_date = self.tag_dates[iver.tag]


class GhcrContainer:

    def __init__(self, data: dict):
        self._raw: dict = data
        self._id: int = data['id']
        self.created_at: datetime = parse(data['created_at'])
        self.updated_at: datetime = parse(data['updated_at'])
        self.date: datetime = max(self.created_at, self.updated_at)
        self.package_html_url: str = data['package_html_url']
        self.html_url: str = data['html_url']
        self.tags: List[str] = data['metadata']['container']['tags']


class GhcrImage(Image):

    @property
    def link(self) -> str:
        return (f'https://github.com/{self.namespace}/{self.repository}/'
                f'pkgs/container/{self.repository}')

    def link_for_tag(self, tag: str) -> str:
        return (f'https://github.com/{self.namespace}/{self.repository}/'
                f'releases/tag/{tag}')

    def _gh_json(self, *url_parts, status_code: int = 200) -> Union[Dict, List]:
        url = GH._build_url(*url_parts)
        logger.debug('GHCR GET: %s', url)
        j = json = GH._json(GH._get(url), status_code)
        return j

    def _get_tagged_containers(self, ownertype) -> List[GhcrContainer]:
        result: List[GhcrContainer] = []
        url = GH._build_url(
            ownertype, self.namespace, 'packages', 'container',
            self.repository, 'versions'
        )
        logger.debug('GHCR Iterate GET: %s', url)
        count: int = 0
        cont: GhcrContainer
        for cont in GH._iter(
            -1, url, GhcrContainer,
            params={"sort": None, "direction": None},
            etag=None
        ):
            if cont.tags:
                result.append(cont)
            count += 1
        logger.info(
            'Found tags on %d of %d versions', len(result), count
        )
        return result

    def update(self):
        logger.info('Updating GHCR package: %s', self.name)
        pkg: dict = self._gh_json(
            'users', self.namespace, 'packages', 'container', self.repository
        )
        logger.debug(
            'Package %s (ID %s) updated at %s; has %s versions',
            pkg['name'], pkg['id'], pkg['updated_at'], pkg['version_count']
        )
        ownertype: str = pkg['owner']['type']
        logger.debug(
            'GHCR %s/%s owner is a %s',
            self.namespace, self.repository, ownertype
        )
        stub: str
        if ownertype == 'Organization':
            stub = 'orgs'
        elif ownertype == 'User':
            stub = 'users'
        else:
            raise RuntimeError(
                f'ERROR: Unknown repository owner type: {ownertype}'
            )
        tagged_versions: List[GhcrContainer] = self._get_tagged_containers(stub)
        cont: GhcrContainer
        for cont in sorted(tagged_versions, key=lambda x: x.date, reverse=True):
            if not self.newest_tag:
                self.newest_tag = cont.tags[0]
            for tag in cont.tags:
                if SEMVER_ANYWHERE_RE.match(tag) and not self.newest_version_tag:
                    self.newest_version_tag = tag
                self.tag_dates[tag] = cont.date


class GcrImage(Image):

    def update(self):
        logger.error('ERROR: gcr.io support not implemented!')
        pass


def get_image(name: str) -> Image:
    orig_name = name
    cls = DockerHubImage
    if name.startswith('ghcr.io/'):
        cls = GhcrImage
        name = name[8:]
    if name.startswith('gcr.io/'):
        cls = GcrImage
        name = name[7:]
    if '/' in name:
        try:
            namespace, repository = name.split('/')
        except ValueError:
            logger.error('Unable to parse image name: %s', name)
            raise
    else:
        namespace = 'library'
        repository = name
    return cls(orig_name, namespace, repository)


class ImageVersion:

    def __init__(self, image: Image, tag: str):
        self.image: Image = image
        self.tag: str = tag
        self.tag_date: datetime = UNKNOWN_DATE
        self.vms: List['VirtualMachine'] = []

    def __repr__(self):
        return f'<ImageVersion(image="{self.image.name}", tag="{self.tag}">'


class Computer:

    def __init__(self, _id: int, name: str):
        self._id: int = _id
        self.name: str = name
        self.vms: Dict[str, 'VirtualMachine'] = {}

    def add_vm(self, name: str, imgver: ImageVersion):
        self.vms[name] = VirtualMachine(
            self, name, imgver
        )
        imgver.vms.append(self.vms[name])


class VirtualMachine:

    def __init__(self, computer: Computer, vm_name: str, imgver: ImageVersion):
        self.computer: Computer = computer
        self.name: str = vm_name
        self.imgver: ImageVersion = imgver

    def __str__(self) -> str:
        return f'<VirtualMachine(name="{self.name}",ImageVersion={self.imgver}>'


def th(s):
    return '<th style="border: 1px solid black;">%s</th>' % s


def td(s):
    return '<td style="border: 1px solid black; padding: 1em;">%s</td>' % s


class GlpiDockerReport:

    TOKEN_FILE: str = '.glpi_token.json'

    CR_HEADER: re.Pattern = re.compile(r'^(\d+)-(\d+)/(\d+)$')

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
        if os.environ.get('DOCKER_HUB_TOKEN') is None:
            raise RuntimeError(
                'ERROR: You must set the DOCKER_HUB_TOKEN environment variable '
                'to your Docker Hub API token.'
            )
        if os.environ.get('GITHUB_TOKEN') is None:
            raise RuntimeError(
                'ERROR: You must set the GITHUB_TOKEN environment variable '
                'to your GitHub API token.'
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
        self.computers: Dict[str, Computer] = {}
        self.images: Dict[str, Image] = {}
        self.old_computers: List[str] = []

    def _get_image(self, name: str) -> Image:
        if name not in self.images:
            self.images[name] = get_image(name)
        return self.images[name]

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
        logger.debug(
            'Got HTTP %d with %d bytes content; headers=%s',
            r.status_code, len(r.content), r.headers
        )
        if m := self.CR_HEADER.match(r.headers.get('Content-Range', '')):
            if int(m.group(2)) + 1 != int(m.group(3)):
                raise NotImplementedError(
                    f'ERROR: GLPI API responded with Content-Range of '
                    f'{r.headers.get("Content-Range")}; pagination not '
                    f'implemented!'
                )
        r.raise_for_status()
        return r.json()

    def run(self, html_file_only: bool = False):
        self._get_glpi_data()
        name: str
        comp: Computer
        for name in sorted(self.computers.keys()):
            comp = self.computers[name]
            if not comp.vms:
                continue
            print(name)
            vmname: str
            imgver: ImageVersion
            for vmname, imgver in sorted(comp.vms.items()):
                print(f'\t{vmname}\t{imgver}')
        img: Image
        rows: List[Dict] = []
        for img in sorted(self.images.values(), key=lambda x: x.name):
            img.update()
            rows.extend(self._rows_for_image(img))
        html = self._generate_html(rows)
        logger.info('Writing report to: glpi_docker_update_report.html')
        with open('glpi_docker_update_report.html', 'w') as fh:
            fh.write(html)
        if html_file_only:
            return
        raise NotImplementedError()

    def _rows_for_image(self, img: Image) -> List[Dict]:
        result = []
        iver: ImageVersion
        for iver in sorted(img.image_versions.values(),
                           key=lambda x: x.tag_date):
            hosts = defaultdict(list)
            vm: VirtualMachine
            for vm in iver.vms:
                hosts[vm.computer.name].append(vm.name)
            result.append({
                'Image': img.name,
                'ImageLink': img.link,
                'ImageNewestTag': img.newest_tag,
                'ImageNewestTagLink': img.link_for_tag(img.newest_tag),
                'ImageNewestTagDate': img.tag_dates.get(img.newest_tag),
                'ImageNewestVer': img.newest_version_tag,
                'ImageNewestVerLink': img.link_for_tag(img.newest_version_tag),
                'ImageNewestVerDate': img.tag_dates.get(img.newest_version_tag),
                'Tag': iver.tag,
                'TagLink': img.link_for_tag(iver.tag),
                'Date': iver.tag_date,
                'Hosts': dict(hosts),
            })
        return result

    def _generate_html(self, rows: List[Dict]) -> str:
        html = ('<html><head>'
                '<title>GLPI Docker Update Report</title>'
                '</head>\n')
        html += '<body>\n'
        html += '<h1>GLPI Docker Update Report</h1>\n'
        html += '<h2>Generated at '
        html += datetime.now(timezone.utc).astimezone().strftime('%c %Z')
        html += '</h2>\n'
        if self.old_computers:
            html += (
                '<p>Ignored the following hosts with last update over '
                f'7 days ago: {", ".join(sorted(self.old_computers))}</p>\n'
            )
        html += ('<table style="border: 1px solid black; '
                 'border-collapse: collapse;">\n')
        html += '<thead><tr>'
        html += th('Image')
        html += th('Tag')
        html += th('Age')
        html += th('Hosts')
        html += th('Newest Tag')
        html += th('Newest SemVer Tag')
        html += '</tr></thead>\n'
        html += '<tbody>\n'
        curr_name = ''
        for row in rows:
            html += '<tr>'
            if curr_name != row['Image']:
                html += td(f'<a href="{row["ImageLink"]}">{row["Image"]}</a>')
                curr_name = row['Image']
            else:
                html += td('&nbsp;')
            html += td(f'<a href="{row["TagLink"]}">{row["Tag"]}</a>')
            if row['Date'] == UNKNOWN_DATE:
                html += td('unknown')
            else:
                html += td(naturaldelta(NOW - row['Date']))
            html += td(
                '; '.join([
                    f'{x} ({", ".join(sorted(row["Hosts"][x]))})'
                    for x in sorted(row['Hosts'].keys())
                ])
            )
            if row["ImageNewestTagDate"]:
                html += td(
                    f'<a href="{row["ImageNewestTagLink"]}">{row["ImageNewestTag"]}</a>'
                    f' ({naturaldelta(NOW - row["ImageNewestTagDate"])} ago)'
                )
            else:
                html += td(
                    f'<a href="{row["ImageNewestTagLink"]}">{row["ImageNewestTag"]}</a>'
                    ' (unknown age)'
                )
            if row["ImageNewestVerDate"]:
                html += td(
                    f'<a href="{row["ImageNewestVerLink"]}">{row["ImageNewestVer"]}</a>'
                    f' ({naturaldelta(NOW - row["ImageNewestVerDate"])} ago)'
                )
            else:
                html += td(
                    f'<a href="{row["ImageNewestVerLink"]}">{row["ImageNewestVer"]}</a>'
                    ' (unknown age)'
                )
            html += '</tr>\n'
        html += '</tbody>\n'
        html += '</table></body></html>\n'
        return html

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
            last_checkin: datetime = parse(comp['last_inventory_update'])
            last_checkin = last_checkin.replace(tzinfo=NOW.tzinfo)
            if NOW - last_checkin > timedelta(days=7):
                logger.error(
                    'Ignoring computer %d (%s) with last update at %s',
                    comp['id'], comp['name'], comp['last_inventory_update']
                )
                self.old_computers.append(comp['name'])
                continue
            logger.info('Computer %d (%s)', comp['id'], comp['name'])
            self._do_computer(comp['id'], comp['name'])

    def _do_computer(self, comp_id: int, comp_name: str):
        comp = Computer(comp_id, comp_name)
        self.computers[comp_name] = comp
        vms = self._api_get_json(
            f'Computer/{comp_id}/ComputerVirtualMachine/'
            f'?expand_dropdowns=true&range=0-1000'
        )
        vm: dict
        for vm in vms:
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
            name: str
            tag: str
            name, tag = vm['comment'].split(':')
            img: Image = self._get_image(name)
            ver: ImageVersion = img.version(tag)
            comp.add_vm(vm['name'], ver)
        logger.info(
            'Done with computer %s (%d)', comp_name, comp_id
        )


def parse_args(argv):
    p = argparse.ArgumentParser(description='GLPI Docker Images Report')
    p.add_argument(
        '-v', '--verbose', dest='verbose', action='store_true',
        default=False, help='verbose output'
    )
    p.add_argument(
        '-H', '--html', dest='html', action='store_true',
        default=False, help='Just write local HTML report and exit'
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

    GlpiDockerReport().run(html_file_only=args.html)
