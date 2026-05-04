#!/usr/bin/env python
"""
Script to report on OS/distribution updates for hosts known to GLPI.

Using an installation of GLPI <https://glpi-project.org/> that is running
FusionInventory Agent <https://fusioninventory.org/> 2.6 or later for inventory
collection, connect to the GLPI API and retrieve the operating system /
distribution and its version for every host that has reported in within the
last 30 days. Then query endoflife.date <https://endoflife.date/> to determine
the newest cycle/version of each distribution and its EOL date. Generate an
HTML report, optionally emailing it via SMTP.

Authentication
--------------

Same as ``glpi_docker_update_report.py``: set the ``GLPI_API_URL`` and
``GLPI_API_TOKEN`` environment variables.

Source
------

https://github.com/jantman/misc-scripts/blob/master/glpi_os_update_report.py

Dependencies
------------

Python 3.11 or newer (tested with 3.12)
requests (tested with 2.32.3)
python-dateutil (tested with 2.9.0)
humanize (tested with 4.9.0)

License
-------

MIT license. Copyright 2026 Jason Antman.
"""

import os
import sys
import argparse
import logging
import json
import html as html_lib
from typing import Optional, Dict, List, Union
from datetime import datetime, timezone, timedelta
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from dateutil.parser import parse
from humanize import naturaldelta


logging.basicConfig(
    level=logging.WARNING,
    format="[%(asctime)s %(levelname)s] %(message)s"
)
logger: logging.Logger = logging.getLogger()

NOW: datetime = datetime.now(tz=timezone.utc)

# Hosts whose last_inventory_update is older than this are excluded.
MAX_INVENTORY_AGE: timedelta = timedelta(days=30)


class OperatingSystem:
    """OS distribution data from endoflife.date."""

    # GLPI OS-name (lowercased) -> endoflife.date product slug. Longer keys
    # win in slug_for() to disambiguate prefixes.
    PRODUCT_MAP: Dict[str, str] = {
        'ubuntu': 'ubuntu',
        'debian gnu/linux': 'debian',
        'debian': 'debian',
        'fedora linux': 'fedora',
        'fedora': 'fedora',
        'centos stream': 'centos-stream',
        'centos linux': 'centos',
        'centos': 'centos',
        'red hat enterprise linux': 'rhel',
        'rhel': 'rhel',
        'alpine linux': 'alpine',
        'alpine': 'alpine',
        'almalinux': 'almalinux',
        'rocky linux': 'rocky-linux',
        'amazon linux': 'amazon-linux',
        'opensuse leap': 'opensuse',
        'opensuse': 'opensuse',
        'raspberry pi os': 'raspberry-pi-os',
        'raspbian': 'raspbian',
        'linux mint': 'linuxmint',
    }

    # Rolling distros — no meaningful "newest version" to report.
    ROLLING_DISTROS: set = {'arch linux', 'gentoo', 'manjaro linux', 'manjaro'}

    def __init__(self, product_slug: str):
        self.product_slug: str = product_slug
        self.cycles: List[dict] = []
        self.cycles_by_name: Dict[str, dict] = {}

    @classmethod
    def is_rolling(cls, name: Optional[str]) -> bool:
        if not name:
            return False
        n = name.lower().strip()
        return any(n.startswith(r) for r in cls.ROLLING_DISTROS)

    @classmethod
    def slug_for(cls, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        name_lower = name.lower().strip()
        if name_lower in cls.PRODUCT_MAP:
            return cls.PRODUCT_MAP[name_lower]
        # Longest-prefix match to handle e.g. "Debian GNU/Linux 12 (bookworm)".
        best: Optional[str] = None
        best_len: int = 0
        for key, slug in cls.PRODUCT_MAP.items():
            if name_lower.startswith(key) and len(key) > best_len:
                best = slug
                best_len = len(key)
        return best

    @property
    def newest(self) -> Optional[dict]:
        return self.cycles[0] if self.cycles else None

    def update(self) -> None:
        url = f'https://endoflife.date/api/{self.product_slug}.json'
        logger.info('Fetching OS data: %s', url)
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        self.cycles = r.json()
        for c in self.cycles:
            self.cycles_by_name[str(c['cycle'])] = c

    def cycle_for_version(self, version: Optional[str]) -> Optional[dict]:
        if not version:
            return None
        if version in self.cycles_by_name:
            return self.cycles_by_name[version]
        if m := re.match(r'(\d+\.\d+)', version):
            if (mm := m.group(1)) in self.cycles_by_name:
                return self.cycles_by_name[mm]
        if m := re.match(r'(\d+)', version):
            if (major := m.group(1)) in self.cycles_by_name:
                return self.cycles_by_name[major]
        return None


def _parse_eol_date(val) -> Optional[Union[datetime, bool]]:
    """Parse endoflife.date eol/releaseDate fields (date string, True, or False)."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        try:
            return parse(val).replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


class Computer:

    def __init__(self, _id: int, name: str, last_checkin: datetime):
        self._id: int = _id
        self.name: str = name
        self.last_checkin: datetime = last_checkin
        self.os_name: Optional[str] = None
        self.os_version: Optional[str] = None
        self.os_kernel: Optional[str] = None


def th(s):
    return '<th style="border: 1px solid black;">%s</th>' % s


def td(s):
    return '<td style="border: 1px solid black; padding: 1em;">%s</td>' % s


def _json_default(o):
    if isinstance(o, datetime):
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


class GlpiOsReport:

    TOKEN_FILE: str = '.glpi_token.json'

    CR_HEADER: re.Pattern = re.compile(r'^(\d+)-(\d+)/(\d+)$')

    def __init__(self):
        if (api_url := os.environ.get('GLPI_API_URL')) is None:
            raise RuntimeError(
                'ERROR: You must set the GLPI_API_URL environment variable '
                'to the root URL for GLPI, i.e. something like '
                'http://127.0.0.1:8088/'
            )
        if (api_token := os.environ.get('GLPI_API_TOKEN')) is None:
            raise RuntimeError(
                'ERROR: You must set the GLPI_API_TOKEN environment variable '
                'to your GLPI API user token.'
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
        self.operating_systems: Dict[str, OperatingSystem] = {}
        self.old_computers: List[str] = []

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
        """Get JSON from GLPI API, paginating list responses if needed."""
        url = self._api_url + path
        logger.debug('GET: %s', url)
        r = self._sess.get(url)
        logger.debug(
            'Got HTTP %d with %d bytes content; headers=%s',
            r.status_code, len(r.content), r.headers
        )
        r.raise_for_status()
        data = r.json()

        if m := self.CR_HEADER.match(r.headers.get('Content-Range', '')):
            start = int(m.group(1))
            end = int(m.group(2))
            total = int(m.group(3))
            logger.debug('Content-Range: %d-%d/%d', start, end, total)
            if end + 1 >= total:
                return data
            if not isinstance(data, list):
                raise RuntimeError(
                    f'ERROR: Expected list for paginated response, got {type(data)}'
                )
            all_data = data
            current_end = end
            while current_end + 1 < total:
                next_start = current_end + 1
                next_end = min(next_start + (end - start), total - 1)
                separator = '&' if '?' in path else '?'
                next_url = (
                    f'{self._api_url}{path}{separator}'
                    f'range={next_start}-{next_end}'
                )
                logger.debug('GET (pagination): %s', next_url)
                r = self._sess.get(next_url)
                r.raise_for_status()
                page_data = r.json()
                if not isinstance(page_data, list):
                    raise RuntimeError(
                        f'ERROR: Expected list for paginated response, got '
                        f'{type(page_data)}'
                    )
                all_data.extend(page_data)
                if m := self.CR_HEADER.match(r.headers.get('Content-Range', '')):
                    current_end = int(m.group(2))
                else:
                    current_end = next_end
            logger.info(
                'Completed paginated request: fetched %d items', len(all_data)
            )
            return all_data
        return data

    def _send_email(self, html: str) -> None:
        addr = os.environ['EMAIL_ADDR']
        message = MIMEMultipart("alternative")
        message["Subject"] = "GLPI OS Update Report"
        message["From"] = addr
        message["To"] = addr
        message.attach(MIMEText(html, "html"))
        host, port = os.environ['SMTP_HOST'].split(':')
        port = int(port)
        logger.debug('Connecting to SMTP on %s:%d as %s', host, port, addr)
        s = smtplib.SMTP(host, port)
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(addr, os.environ['SMTP_PASSWORD'])
        logger.info('Sending mail From=%s To=%s', addr, addr)
        s.sendmail(addr, addr, message.as_string())
        logger.info('EMail sent.')
        s.quit()

    def run(self, html_file_only: bool = False, skip_names: List[str] = []):
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
        self._update_operating_systems()
        rows = self._build_rows()
        html = self._generate_html(rows, skip_names)
        logger.info('Writing report to: glpi_os_update_report.html')
        with open('glpi_os_update_report.html', 'w') as fh:
            fh.write(html)
        if html_file_only:
            return
        self._send_email(html)

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
                    'Skip template computer %d (%s)',
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
            if NOW - last_checkin > MAX_INVENTORY_AGE:
                logger.info(
                    'Ignoring computer %d (%s) with last update at %s',
                    comp['id'], comp['name'], comp['last_inventory_update']
                )
                self.old_computers.append(comp['name'])
                continue
            logger.info('Computer %d (%s)', comp['id'], comp['name'])
            self._do_computer(comp['id'], comp['name'], last_checkin)

    def _do_computer(
        self, comp_id: int, comp_name: str, last_checkin: datetime
    ):
        comp = Computer(comp_id, comp_name, last_checkin)
        self.computers[comp_name] = comp
        try:
            os_data = self._api_get_json(
                f'Computer/{comp_id}/Item_OperatingSystem/'
                '?expand_dropdowns=true'
            )
        except Exception as ex:
            logger.error(
                'Could not fetch OS info for computer %s: %s', comp_name, ex
            )
            return
        if not os_data or not isinstance(os_data, list):
            logger.debug('No OS info for computer %s', comp_name)
            return
        entry = os_data[0]
        comp.os_name = entry.get('operatingsystems_id') or None
        comp.os_version = entry.get('operatingsystemversions_id') or None
        comp.os_kernel = entry.get('operatingsystemkernelversions_id') or None
        logger.debug(
            'Computer %s OS: %s / %s', comp_name, comp.os_name, comp.os_version
        )

    def _update_operating_systems(self):
        slugs: set = set()
        for comp in self.computers.values():
            if (slug := OperatingSystem.slug_for(comp.os_name)) is not None:
                slugs.add(slug)
            elif comp.os_name and not OperatingSystem.is_rolling(comp.os_name):
                logger.warning(
                    'No endoflife.date product mapping for OS %r '
                    '(computer %s); add it to OperatingSystem.PRODUCT_MAP',
                    comp.os_name, comp.name
                )
        for slug in sorted(slugs):
            os_obj = OperatingSystem(slug)
            try:
                os_obj.update()
            except Exception as ex:
                logger.error(
                    'Failed to fetch endoflife.date data for %s: %s', slug, ex
                )
            self.operating_systems[slug] = os_obj

    def _build_rows(self) -> List[Dict]:
        """Build one dict per computer; consumed by both HTML render and JSON dump."""
        rows: List[Dict] = []
        for name in sorted(self.computers.keys()):
            comp = self.computers[name]
            slug = OperatingSystem.slug_for(comp.os_name)
            is_rolling = OperatingSystem.is_rolling(comp.os_name)
            os_obj = self.operating_systems.get(slug) if slug else None
            cycle_data = (
                os_obj.cycle_for_version(comp.os_version) if os_obj else None
            )
            row: Dict = {
                'Host': comp.name,
                'LastInventory': comp.last_checkin,
                'Distribution': comp.os_name,
                'OsVersion': comp.os_version,
                'OsKernel': comp.os_kernel,
                'EndoflifeProduct': slug,
                'IsRolling': is_rolling,
                'CurrentCycle': None,
                'CurrentCycleReleased': None,
                # CurrentCycleEol: ISO datetime if a date is set; True if
                # explicitly EOL with no date; False if open-ended (no EOL);
                # None if unknown.
                'CurrentCycleEol': None,
                'NewestCycle': None,
                'NewestVersion': None,
                'NewestCycleReleased': None,
            }
            if cycle_data:
                row['CurrentCycle'] = cycle_data.get('cycle')
                rel = _parse_eol_date(cycle_data.get('releaseDate'))
                if isinstance(rel, datetime):
                    row['CurrentCycleReleased'] = rel
                row['CurrentCycleEol'] = _parse_eol_date(cycle_data.get('eol'))
            if os_obj and os_obj.newest:
                row['NewestCycle'] = os_obj.newest.get('cycle')
                row['NewestVersion'] = os_obj.newest.get('latest')
                nrel = _parse_eol_date(os_obj.newest.get('releaseDate'))
                if isinstance(nrel, datetime):
                    row['NewestCycleReleased'] = nrel
            rows.append(row)
        return rows

    def _generate_html(self, rows: List[Dict], skip_names: List[str]) -> str:
        html = ('<html><head>'
                '<title>GLPI OS Update Report</title>'
                '</head>\n')
        html += '<body>\n'
        html += '<h1>GLPI OS Update Report</h1>\n'
        html += '<h2>Generated at '
        html += datetime.now(timezone.utc).astimezone().strftime('%c %Z')
        html += '</h2>\n'
        html += (
            f'<p>Including hosts that have reported in within the last '
            f'{MAX_INVENTORY_AGE.days} days.</p>\n'
        )
        if self.old_computers:
            html += (
                f'<p>Ignored the following hosts with last update over '
                f'{MAX_INVENTORY_AGE.days} days ago: '
                f'{", ".join(sorted(self.old_computers))}</p>\n'
            )
        if skip_names:
            html += (
                '<p>Skipped the following hosts based on command line argument:'
                f' {", ".join(sorted(skip_names))}</p>\n'
            )
        html += ('<table style="border: 1px solid black; '
                 'border-collapse: collapse;">\n')
        html += '<thead><tr>'
        html += th('Host')
        html += th('Last Inventory')
        html += th('Distribution')
        html += th('Current Version')
        html += th('Current Cycle Released')
        html += th('Current Cycle EOL')
        html += th('Newest Cycle')
        html += th('Newest Version')
        html += th('Newest Released')
        html += '</tr></thead>\n<tbody>\n'
        for row in rows:
            html += '<tr>'
            html += td(row['Host'])
            li = row['LastInventory']
            html += td(
                f'{li.date().isoformat()} '
                f'({naturaldelta(NOW - li)} ago)'
            )
            if not row['Distribution']:
                html += td('unknown') * 7
                html += '</tr>\n'
                continue
            html += td(row['Distribution'])
            html += td(row['OsVersion'] or 'unknown')
            if row['IsRolling']:
                html += td('rolling release') * 5
                html += '</tr>\n'
                continue
            if not row['EndoflifeProduct'] or row['CurrentCycle'] is None:
                # Couldn't resolve cycle data (no mapping or no matching cycle)
                if row['NewestCycle'] is None:
                    html += td('unknown') * 5
                    html += '</tr>\n'
                    continue
                html += td('unknown') * 2
            else:
                rel = row['CurrentCycleReleased']
                if isinstance(rel, datetime):
                    html += td(
                        f'{rel.date().isoformat()} '
                        f'({naturaldelta(NOW - rel)} ago)'
                    )
                else:
                    html += td('unknown')
                eol = row['CurrentCycleEol']
                if isinstance(eol, datetime):
                    delta = eol - NOW
                    if delta.total_seconds() < 0:
                        html += td(
                            f'{eol.date().isoformat()} '
                            f'(EOL {naturaldelta(-delta)} ago)'
                        )
                    else:
                        html += td(
                            f'{eol.date().isoformat()} '
                            f'(in {naturaldelta(delta)})'
                        )
                elif eol is True:
                    html += td('EOL')
                elif eol is False:
                    html += td('no EOL set')
                else:
                    html += td('unknown')
            html += td(str(row['NewestCycle'] or 'unknown'))
            html += td(str(row['NewestVersion'] or 'unknown'))
            ncr = row['NewestCycleReleased']
            if isinstance(ncr, datetime):
                html += td(
                    f'{ncr.date().isoformat()} '
                    f'({naturaldelta(NOW - ncr)} ago)'
                )
            else:
                html += td('unknown')
            html += '</tr>\n'
        html += '</tbody>\n</table>\n'
        html += _json_block(rows)
        html += '</body></html>\n'
        return html


def parse_args(argv):
    p = argparse.ArgumentParser(description='GLPI OS Update Report')
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
    return p.parse_args(argv)


def set_log_info(l: logging.Logger):
    set_log_level_format(
        l,
        logging.INFO,
        '%(asctime)s %(levelname)s:%(name)s:%(message)s'
    )


def set_log_debug(l: logging.Logger):
    set_log_level_format(
        l,
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(lgr: logging.Logger, level: int, fmt: str):
    formatter = logging.Formatter(fmt=fmt)
    lgr.handlers[0].setFormatter(formatter)
    lgr.setLevel(level)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.verbose:
        set_log_debug(logger)
    else:
        set_log_info(logger)
    GlpiOsReport().run(
        html_file_only=args.html,
        skip_names=args.skip_names,
    )
