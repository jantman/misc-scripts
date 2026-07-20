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
import json
import html as html_lib
from typing import Optional, Dict, List, Union, Tuple
from time import time, sleep
from datetime import datetime, timezone, timedelta
import re
from collections import defaultdict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from dateutil.parser import parse
from humanize import naturaldelta
from github3 import GitHub


logging.basicConfig(
    level=logging.WARNING,
    format="[%(asctime)s %(levelname)s] %(message)s"
)
logger: logging.Logger = logging.getLogger()

# --- Version parsing, comparison & severity -------------------------------

#: Tags that are pre-release / dev / beta / rc builds and must never be
#: treated as the "newest version". Matches word markers delimited by a
#: separator/boundary, plus the CalVer/semver beta form (e.g. "2026.5.0b1",
#: "1.2.3a4" -> "0b1"/"3a4").
PRERELEASE_RE: re.Pattern = re.compile(
    r'(?:^|[-._+/])'
    r'(?:dev|devel|develop|alpha|beta|rc|pre|preview|nightly|snapshot|'
    r'canary|edge|unstable|insider|insiders)'
    r'(?:[-._/]|\d|$)'
    r'|\d+[ab]\d+$',
    re.IGNORECASE
)

#: OS / flavor / build-variant markers that indicate a non-canonical image
#: (e.g. "1.30.0-trixie-perl", "8.0.21-windowsservercore-ltsc2025",
#: "13.1.0-25295570271-ubuntu", "v3.11.3-distroless").
VARIANT_RE: re.Pattern = re.compile(
    r'(?:^|[-._])'
    r'(?:alpine|ubuntu|debian|jammy|noble|focal|bionic|bookworm|bullseye|'
    r'trixie|buster|slim|perl|distroless|otel|fpm|apache|ubi\d*|'
    r'windowsservercore|nanoserver|servercore|ltsc\d*|mainline|windows|'
    r'amd64|arm64|arm32|armv7|armhf|x86[-_]64|s390x|ppc64le|'
    r'jre\d*|jdk\d*|openjdk|corretto|zulu|graal|temurin|oracle)'
    r'(?:[-._]|\d|$)',
    re.IGNORECASE
)

#: Signature / attestation / bare-digest tags that are not runnable versions
#: (e.g. "sha256-....sig", a bare 40/64-char git/image digest).
SIG_RE: re.Pattern = re.compile(
    r'\.sig$|\.att$|^sha256[-:]|^[0-9a-f]{40}$|^[0-9a-f]{64}$',
    re.IGNORECASE
)

#: Extracts the first dotted-number run (the version core) from a tag.
VERSION_CORE_RE: re.Pattern = re.compile(r'(\d+(?:\.\d+)+)')

#: Severity level -> background color (email-safe pastels, black text
#: readable), ordered least -> most severe.
SEVERITY_COLORS: Dict[str, str] = {
    'current': '#c8e6c9',   # green
    'patch': '#dcedc8',     # yellow-green
    'minor': '#fff9c4',     # yellow
    'major': '#ffe0b2',     # orange
    'critical': '#ffcdd2',  # red
    'unknown': '#eceff1',   # gray
}

#: (level, human description) pairs for the report legend.
SEVERITY_LEGEND: List[Tuple[str, str]] = [
    ('current', 'Up to date'),
    ('patch', 'Patch version behind'),
    ('minor', 'Minor version behind'),
    ('major', 'One major version (or ~6-12 months) behind'),
    ('critical', 'Multiple major versions (or over a year) behind'),
    ('unknown', 'Could not determine'),
]


def is_signature_tag(tag: Optional[str]) -> bool:
    """True if `tag` is a signature/attestation/bare-digest, not a real tag."""
    return bool(tag and SIG_RE.search(tag))


def is_clean_version_tag(tag: Optional[str]) -> bool:
    """True if `tag` looks like a stable, non-variant release version."""
    if not tag:
        return False
    if is_signature_tag(tag):
        return False
    if PRERELEASE_RE.search(tag):
        return False
    if VARIANT_RE.search(tag):
        return False
    return bool(VERSION_CORE_RE.search(tag))


def parse_version_tag(tag: Optional[str]) -> Optional[Tuple[int, ...]]:
    """Return the numeric version core of `tag` as a tuple of ints, or None.

    Tolerates a leading ``v``/``version-`` and trailing build/flavor text by
    extracting the first dotted-number run, e.g. ``v0.22.1275-ls648`` ->
    ``(0, 22, 1275)`` and CalVer ``2026.2.4`` -> ``(2026, 2, 4)``.
    """
    if not tag:
        return None
    m = VERSION_CORE_RE.search(tag)
    if not m:
        return None
    try:
        return tuple(int(x) for x in m.group(1).split('.'))
    except ValueError:
        return None


def version_distance_severity(
    cur: Tuple[int, ...], new: Tuple[int, ...]
) -> Tuple[str, str]:
    """Severity level + human label from comparing two version tuples.

    The first differing component decides the tier: index 0 is "major" (year
    for CalVer), index 1 is "minor" (month for CalVer), the rest are "patch".
    """
    n = max(len(cur), len(new))
    cur = cur + (0,) * (n - len(cur))
    new = new + (0,) * (n - len(new))
    if cur >= new:
        return 'current', 'up to date'
    idx = next(i for i in range(n) if cur[i] != new[i])
    if idx == 0:
        majors = new[0] - cur[0]
        if majors >= 2:
            return 'critical', f'{majors} major versions behind'
        return 'major', '1 major version behind'
    if idx == 1:
        return 'minor', 'minor version(s) behind'
    return 'patch', 'patch version(s) behind'


def age_severity(delta: timedelta) -> Tuple[str, str]:
    """Severity level + label from how far behind (by time) something is.

    Used as a fallback when the running and newest tags are not both parseable
    as comparable version numbers.
    """
    label = f'{naturaldelta(delta)} behind'
    days = delta.days
    if days < 30:
        return 'current', label
    if days < 182:
        return 'minor', label
    if days < 365:
        return 'major', label
    return 'critical', label


def severity_legend_html() -> str:
    """Render the color-key legend shared by both reports."""
    cells = ''.join(
        f'<span style="display:inline-block; padding:2px 8px; margin:2px; '
        f'border:1px solid #999; background-color:{SEVERITY_COLORS[key]};">'
        f'{label}</span>'
        for key, label in SEVERITY_LEGEND
    )
    return f'<p><strong>Legend:</strong> {cells}</p>\n'


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
                # Skip signature/attestation tags (e.g. "sha256-....sig")
                # which sort to the top but are not runnable images.
                for tag in resp['results']:
                    if is_signature_tag(tag['name']):
                        continue
                    self.newest_tag = tag['name']
                    self.tag_dates[tag['name']] = parse(tag['tag_last_pushed'])
                    logger.info(
                        'Found newest tag as: %s at %s',
                        self.newest_tag, self.tag_dates[self.newest_tag]
                    )
                    break
            if not self.newest_version_tag:
                for tag in resp['results']:
                    if is_clean_version_tag(tag['name']):
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

    def __str__(self) -> str:
        return (
            f'GhcrContainer(id={self._id}, created_at={self.created_at}, '
            f'updated_at={self.updated_at}, tags={self.tags})'
        )


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
                # Skip signature/attestation tags; pick the first real tag.
                for tag in cont.tags:
                    if not is_signature_tag(tag):
                        self.newest_tag = tag
                        break
            for tag in cont.tags:
                if is_clean_version_tag(tag) and not self.newest_version_tag:
                    self.newest_version_tag = tag
                self.tag_dates[tag] = cont.date
                if tag in self.image_versions:
                    self.image_versions[tag].tag_date = cont.date
        if self.newest_tag:
            logger.info(
                'Found newest tag as: %s at %s',
                self.newest_tag, self.tag_dates.get(self.newest_tag)
            )
        logger.debug(
            'Image %s newest_tag=%s tag_dates=%s tagged_versions=%s',
            self.name, self.newest_tag, self.tag_dates,
            [str(x) for x in tagged_versions]
        )


class LscrImage(GhcrImage):

    BASE_URL = "https://hub.linuxserver.io/v2"

    @property
    def link(self) -> str:
        return f'https://docs.linuxserver.io/images/docker-{self.repository}/'

    def link_for_tag(self, tag: str) -> str:
        return f'https://github.com/{self.namespace}/docker-{self.repository}/releases/tag/{tag}'


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
    if name.startswith('lscr.io/'):
        cls = LscrImage
        name = name[8:]
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


def td(s, bg: Optional[str] = None):
    style = 'border: 1px solid black; padding: 1em;'
    if bg:
        style += f' background-color: {bg};'
    return f'<td style="{style}">{s}</td>'


def _json_default(o):
    """JSON serializer for datetime objects; UNKNOWN_DATE becomes null."""
    if isinstance(o, datetime):
        if o == UNKNOWN_DATE:
            return None
        return o.isoformat()
    raise TypeError(f'Object not JSON serializable: {type(o)}')


def _json_block(rows: List[Dict]) -> str:
    """Embed `rows` as JSON inside a parseable <pre id="report-data"> element."""
    payload = html_lib.escape(
        json.dumps(rows, indent=2, default=_json_default)
    )
    return (
        '<details><summary>Report data (JSON)</summary>\n'
        f'<pre id="report-data">{payload}</pre>\n'
        '</details>\n'
    )


class GlpiDockerReport:

    TOKEN_FILE: str = '.glpi_token.json'

    CR_HEADER: re.Pattern = re.compile(r'^(\d+)-(\d+)/(\d+)$')

    def __init__(self, cache: bool = False):
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
        # image caching, for development
        self._cache_images: bool = False
        self._cache_ttl_hours: int = 23
        self._cache_cutoff: float = time() - (self._cache_ttl_hours * 3600)
        self._cache_path: str = '.glpi_image_cache.pkl'
        self._image_cache: Dict[str, Tuple[float, Image]] = {}
        if cache:
            self._cache_images = True
            logger.warning('Caching of image registry data ENABLED!')
            try:
                import pickle
                with open(self._cache_path, 'rb') as fh:
                    self._image_cache = pickle.load(fh)
                logger.debug(
                    'Loaded image cache from %s: %s',
                    self._cache_path,
                    {k: v[0] for k, v in self._image_cache.items()}
                )
            except Exception as ex:
                logger.error('ERROR: Could not load image cache from %s: %s',
                             self._cache_path, ex)
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

    def _get_cached_image(self, name: str) -> Optional[Image]:
        if not self._cache_images:
            return None
        if name in self._image_cache:
            ts, img = self._image_cache[name]
            if ts > self._cache_cutoff:
                logger.debug('Using cached image data for: %s', name)
                return img
            else:
                logger.debug('Cached image data for %s is too old', name)
        return None

    def _cache_image(self, img: Image) -> None:
        if not self._cache_images:
            return
        self._image_cache[img.name] = (time(), img)
        logger.debug('Cached image data for: %s', img.name)
        try:
            import pickle
            with open(self._cache_path, 'wb') as fh:
                pickle.dump(self._image_cache, fh)
            logger.debug('Wrote image cache to: %s', self._cache_path)
        except Exception as ex:
            logger.error('ERROR: Could not write image cache to %s: %s',
                         self._cache_path, ex)

    def _get_image(self, name: str) -> Image:
        if name in self.images:
            return self.images[name]
        if (img := self._get_cached_image(name)) is not None:
            self.images[name] = img
            return img
        self.images[name] = get_image(name)
        if self._cache_images:
            self._cache_image(self.images[name])
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

    def _api_get_json(self, path: str) -> Union[dict, list]:
        """
        Get JSON data from GLPI API with pagination support.
        
        Returns either a dict (for single item responses) or a list (for
        collections that may be paginated).
        """
        url = self._api_url + path
        logger.debug('GET: %s', url)
        r = self._sess.get(url)
        logger.debug(
            'Got HTTP %d with %d bytes content; headers=%s',
            r.status_code, len(r.content), r.headers
        )
        r.raise_for_status()
        data = r.json()
        
        # Check if response is paginated
        if m := self.CR_HEADER.match(r.headers.get('Content-Range', '')):
            start = int(m.group(1))
            end = int(m.group(2))
            total = int(m.group(3))
            logger.debug(
                'Content-Range: %d-%d/%d', start, end, total
            )
            
            # If we have all the data, return it
            if end + 1 >= total:
                return data
            
            # Need to paginate - data should be a list
            if not isinstance(data, list):
                raise RuntimeError(
                    f'ERROR: Expected list for paginated response, got {type(data)}'
                )
            
            all_data = data
            current_end = end
            
            # Fetch remaining pages
            while current_end + 1 < total:
                next_start = current_end + 1
                next_end = min(next_start + (end - start), total - 1)
                
                # Add range parameter to URL
                separator = '&' if '?' in path else '?'
                next_url = f'{self._api_url}{path}{separator}range={next_start}-{next_end}'
                
                logger.debug('GET (pagination): %s', next_url)
                r = self._sess.get(next_url)
                logger.debug(
                    'Got HTTP %d with %d bytes content; headers=%s',
                    r.status_code, len(r.content), r.headers
                )
                r.raise_for_status()
                page_data = r.json()
                
                if not isinstance(page_data, list):
                    raise RuntimeError(
                        f'ERROR: Expected list for paginated response, got {type(page_data)}'
                    )
                
                all_data.extend(page_data)
                
                # Update current_end from the Content-Range header
                if m := self.CR_HEADER.match(r.headers.get('Content-Range', '')):
                    current_end = int(m.group(2))
                    logger.debug(
                        'Fetched through item %d of %d', current_end + 1, total
                    )
                else:
                    # No Content-Range header, assume we got what we asked for
                    current_end = next_end
            
            logger.info(
                'Completed paginated request: fetched %d items', len(all_data)
            )
            return all_data
        
        return data

    def _send_email(self, html: str) -> None:
        addr = os.environ['EMAIL_ADDR']
        message = MIMEMultipart("alternative")
        message["Subject"] = "GLPI Docker Report"
        message["From"] = addr
        message["To"] = addr
        message.attach(MIMEText(html, "html"))
        host, port = os.environ['SMTP_HOST'].split(':')
        port = int(port)
        smtp_user = os.environ['SMTP_USER']
        logger.debug('Connecting to SMTP on %s:%d as %s', host, port, smtp_user)
        s = smtplib.SMTP(host, port)
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(smtp_user, os.environ['SMTP_PASSWORD'])
        logger.info('Sending mail From=%s To=%s', smtp_user, addr)
        s.sendmail(smtp_user, addr, message.as_string())
        logger.info('EMail sent.')
        s.quit()

    def run(self, html_file_only: bool = False, skip_names: List[str] = [], skip_images: List[str] = []):
        if not html_file_only:
            email_vars = [
                "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_ADDR"
            ]
            if not set(email_vars).issubset(set(os.environ.keys())):
                raise RuntimeError(
                    f'ERROR: --html not specified, but not all email env vars '
                    f'are set. To send email, please set: {email_vars}'
                )
        self._get_glpi_data(skip_names=skip_names)
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
            if img.name in skip_images:
                logger.info('Skipping image: %s', img.name)
                continue
            try:
                img.update()
            except Exception as ex:
                logger.error(
                    'Failed to update registry data for image %s: %s; '
                    'continuing without newest-tag info for this image',
                    img.name, ex
                )
            rows.extend(self._rows_for_image(img))
        html = self._generate_html(rows, skip_names)
        logger.info('Writing report to: glpi_docker_update_report.html')
        with open('glpi_docker_update_report.html', 'w') as fh:
            fh.write(html)
        if html_file_only:
            return
        self._send_email(html)

    def _rows_for_image(self, img: Image) -> List[Dict]:
        result = []
        iver: ImageVersion
        for iver in sorted(img.image_versions.values(),
                           key=lambda x: x.tag_date):
            hosts = defaultdict(list)
            vm: VirtualMachine
            for vm in iver.vms:
                hosts[vm.computer.name].append(vm.name)
            row = {
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
            }
            row['Severity'], row['Status'] = self._severity_for_row(row)
            result.append(row)
        return result

    @staticmethod
    def _severity_for_row(row: Dict) -> Tuple[str, str]:
        """Determine (severity_level, human status) for one image/tag row.

        Prefers version-number distance between the running tag and the newest
        stable version; falls back to how far behind (by time) the running
        image is when the tags are not both parseable as versions.
        """
        cur = parse_version_tag(row['Tag'])
        new = (
            parse_version_tag(row['ImageNewestVer'])
            if row['ImageNewestVer'] else None
        )
        if cur and new:
            return version_distance_severity(cur, new)
        run_date = row['Date']
        new_date = row['ImageNewestVerDate']
        if run_date and run_date != UNKNOWN_DATE:
            if new_date and new_date > run_date:
                return age_severity(new_date - run_date)
            return age_severity(NOW - run_date)
        return 'unknown', 'unknown'

    @staticmethod
    def _newest_cell(
        tag: Optional[str], link: Optional[str], date: Optional[datetime]
    ) -> str:
        """Render a 'newest tag/version' cell with a link and relative age."""
        if not tag:
            return 'unknown'
        label = f'<a href="{link}">{tag}</a>' if link else tag
        if date and date != UNKNOWN_DATE:
            return f'{label} ({naturaldelta(NOW - date)} ago)'
        return f'{label} (unknown age)'

    def _generate_html(self, rows: List[Dict], skip_names: List[str]) -> str:
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
        if skip_names:
            html += (
                '<p>Skipped the following hosts based on command line argument:'
                f' {", ".join(sorted(skip_names))}</p>\n'
            )
        html += severity_legend_html()
        html += ('<table style="border: 1px solid black; '
                 'border-collapse: collapse;">\n')
        html += '<thead><tr>'
        html += th('Image')
        html += th('Tag')
        html += th('Status')
        html += th('Age')
        html += th('Hosts')
        html += th('Newest Tag')
        html += th('Newest Version')
        html += '</tr></thead>\n'
        html += '<tbody>\n'
        curr_name = ''
        for row in rows:
            bg = SEVERITY_COLORS.get(row['Severity'], SEVERITY_COLORS['unknown'])
            html += '<tr>'
            if curr_name != row['Image']:
                html += td(
                    f'<a href="{row["ImageLink"]}">{row["Image"]}</a>', bg
                )
                curr_name = row['Image']
            else:
                html += td('&nbsp;', bg)
            html += td(f'<a href="{row["TagLink"]}">{row["Tag"]}</a>', bg)
            html += td(row['Status'], bg)
            if row['Date'] == UNKNOWN_DATE:
                html += td('unknown', bg)
            else:
                html += td(naturaldelta(NOW - row['Date']), bg)
            html += td(
                '; '.join([
                    f'{x} ({", ".join(sorted(row["Hosts"][x]))})'
                    for x in sorted(row['Hosts'].keys())
                ]),
                bg
            )
            html += td(self._newest_cell(
                row['ImageNewestTag'], row['ImageNewestTagLink'],
                row['ImageNewestTagDate']
            ), bg)
            html += td(self._newest_cell(
                row['ImageNewestVer'], row['ImageNewestVerLink'],
                row['ImageNewestVerDate']
            ), bg)
            html += '</tr>\n'
        html += '</tbody>\n'
        html += '</table>\n'
        html += _json_block(rows)
        html += '</body></html>\n'
        return html

    def _get_glpi_data(self, skip_names: List[str]):
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
            if comp['name'] in skip_names:
                logger.info(
                    'Skip computer based on argument %d (%s)',
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
    p.add_argument(
        '-S', '--skip', dest='skip_names', action='append',
        default=[], help='Skip these computer names (can be specified '
                         'multiple times)'
    )
    p.add_argument(
        '-I', '--skip-image', dest='skip_images', action='append',
        default=[], help='Skip these image names (can be specified multiple times)'
    )
    p.add_argument(
        '-C', '--cache', dest='cache', action='store_true',
        default=False, help='Cache image registry data for 23h (for development)'
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

    GlpiDockerReport(cache=args.cache).run(
        html_file_only=args.html,
        skip_names=args.skip_names,
        skip_images=args.skip_images
    )
