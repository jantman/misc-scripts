#!/usr/bin/env python3
"""
Script to back up UniFi Network Application (controller) config locally, and also
decrypt and write markdown and JSON summaries of some of the more useful bits.

MIT license. Copyright 2021-2024 Jason Antman.

Canonical source:

https://github.com/jantman/misc-scripts/blob/master/unifi_backup.py
"""

import sys
import os
import requests
from urllib.parse import urljoin
from dateutil.parser import parse
from datetime import datetime, timedelta, date
from tzlocal import get_localzone
import urllib3
import argparse
try:
    from Crypto.Cipher import AES
except ImportError:
    from Cryptodome.Cipher import AES
from binascii import unhexlify
from zipfile import ZipFile
from tempfile import mkstemp
import subprocess
import gzip
import bson
import json
from json import JSONEncoder
from time import mktime
from tabulate import tabulate
from typing import List, Optional, Tuple
from socket import inet_aton
import logging
from ipaddress import IPv4Address

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MagicJSONEncoder(JSONEncoder):
    """
    Customized JSONEncoder class that uses ``as_dict`` properties on objects
    to encode them.
    """

    def default(self, o):
        if hasattr(o, 'as_dict') and isinstance(type(o).as_dict, property):
            d = o.as_dict
            d['class'] = o.__class__.__name__
            return d
        if isinstance(o, datetime):
            return mktime(o.timetuple())
        if isinstance(o, date):
            return {
                'class': 'date',
                'str': o.strftime('%Y-%m-%d'),
                'ts': mktime(o.timetuple()),
                'year': o.year,
                'month': o.month,
                'date': o.day
            }
        if isinstance(o, bson.objectid.ObjectId):
            return str(o)
        if isinstance(o, type(b'')):
            return None
        if isinstance(o, IPv4Address):
            return str(o)
        return super(MagicJSONEncoder, self).default(o)


class UniFiBackup:

    # from: https://github.com/zhangyoufu/unifi-backup-decrypt
    KEY = unhexlify('626379616e676b6d6c756f686d617273')
    IV = unhexlify('75626e74656e74657270726973656170')

    IGNORE_COLLECTIONS = [
        'admin_access_log', 'alarm', 'alert', 'alert_setting',
        'diagnostics_config', 'event', 'rogue', 'user', 'user_session_log'
    ]

    MARKDOWN_SUMMARY_TABLES = [
        {
            'title': 'Admins',
            'collection': 'admin',
            'sort': 'name',
            'fields': ['name', 'email', '_id']
        },
        {
            'title': 'Device List',
            'collection': '__devices',
            'sort': 'sortkey',
            'fields': ['name', 'ip', 'type', 'model', 'mac']
        },
        {
            'title': 'Switch Ports',
            'collection': '__ports',
            'sort': 'sortkey',
            'fields': [
                'Device / Port', 'Name', 'VLAN(s)', 'Speed', 'PoE Enabled',
                'PoE Active'
            ]
        },
        {
            'title': 'Fixed IP Leases',
            'collection': '__fixedip',
            'sort': 'ipaddr',
            'fields': ['IP', 'Name', 'MAC', 'Network', 'WLAN']
        },
        {
            'title': 'Static DNS',
            'collection': 'static_dns',
            'sort': 'key',
            'fields': ['key', 'enabled', 'record_type', 'value', 'ttl', 'weight', 'port', 'priority']
        },
        {
            'title': 'Traffic Rules',
            'collection': '__traffic_rules',
            'sort': 'description',
            'fields': ['description', 'enabled', 'action', 'sources', 'direction', 'targets']
        },
        {
            'title': 'Port Forwards',
            'collection': 'portforward',
            'sort': 'name',
            'fields': ['name', 'enabled', 'pfwd_interface', 'destination_ip', 'dst_port', 'fwd', 'fwd_port', 'proto', 'log', 'src']
        }
    ]

    def __init__(self, outdir, outfile, dump_all_collections=False):
        self.outdir: str = outdir
        self.destpath: str = outfile
        self.dump_all_collections: bool = dump_all_collections
        logger.debug('Output directory: %s', self.outdir)
        if not os.path.exists(outdir):
            logger.debug('Creating output directory')
            os.mkdir(outdir)

    def _sorted_dict_repr(
        self, d: dict, ignore_keys: Optional[List[str]] = None,
        ignore_values: Optional[List[str]] = None
    ) -> str:
        if not ignore_keys:
            ignore_keys = []
        if not ignore_values:
            ignore_values = ["", None, []]
        s: str = ''
        for x, y in sorted(
            {
                k: v for k, v in d.items()
                if k not in ignore_keys and v not in ignore_values
            }.items(), key=lambda a: str(a[0]).lower()
        ):
            if x == 'mac':
                s += f'{x}=``{y}`` '
            else:
                s += f'{x}={y} '
        return s

    def _do_traffic_rule(self, r: dict, networks: dict, client_macs: dict) -> dict:
        data = {
            'description': r['description'],
            'action': r['action'],
            'enabled': r['enabled'],
            '_targets': [],
            '_sources': [],
            'direction': r.get('traffic_direction', 'FROM/TO')
        }
        for t in r['target_devices']:
            if t['type'] == 'NETWORK':
                data['_targets'].append(networks[t['network_id']])
            elif t['type'] == 'CLIENT':
                data['_targets'].append(f'{client_macs.get(t["client_mac"], "unknown")} ({t["client_mac"]})')
            elif t['type'] == 'ALL_CLIENTS':
                data['_targets'].append('<All Clients>')
            else:
                raise NotImplementedError(
                'ERROR: traffic rule target_devices type of '
                f'"{t["type"]}" not implemented. Rule dict: {r}'
            )
        if r['matching_target'] == 'INTERNET':
            data['_sources'] = ['INTERNET']
        elif r['matching_target'] == 'LOCAL_NETWORK':
            data['_sources'] = [
                networks[x] for x in r['network_ids']
            ]
        elif r['matching_target'] == 'IP':
            for ip in r['ip_addresses']:
                tmp = ip['ip_or_subnet']
                if ip['ports'] or ip['port_ranges']:
                    tmp += '/' + ','.join([str(x) for x in ip['ports'] + ip['port_ranges']])
                data['_sources'].append(tmp)
        elif r['matching_target'] == 'DOMAIN':
            for dom in r['domains']:
                tmp = dom['domain']
                if dom['ports'] or dom['port_ranges']:
                    tmp += '/' + ','.join(
                        [str(x) for x in dom['ports'] + dom['port_ranges']])
                data['_sources'].append(tmp)
        else:
            raise NotImplementedError(
                'ERROR: traffic rule matching_target of '
                f'"{r["matching_target"]}" not implemented. Rule dict: {r}'
            )
        data['targets'] = ', '.join(data['_targets'])
        data['sources'] = ', '.join(data['_sources'])
        return data

    def _do_traffic_rules(self, rules: dict, networks: dict, client_macs: dict) -> Tuple[str, dict]:
        data = {}
        s = '\n## Traffic Rules\n\n'
        for k, r in sorted(rules.items()):
            data[str(r['_id'])] = self._do_traffic_rule(r, networks, client_macs)
            s += '* ' + f'``{r["description"]}``: (id {str(r["_id"])}) '
            s += self._sorted_dict_repr(
                data[str(r['_id'])], ignore_keys=['name', '_sources', '_targets']
            ) + '\n'
        return s, data

    def _github_anchor(self, heading: str) -> str:
        """
        Convert a markdown heading to a GitHub-compatible anchor link.
        GitHub converts headings to lowercase, replaces spaces with hyphens,
        and removes special characters.
        """
        import re
        # Convert to lowercase
        anchor = heading.lower()
        # Replace spaces with hyphens
        anchor = anchor.replace(' ', '-')
        # Remove special characters, keeping only alphanumeric and hyphens
        anchor = re.sub(r'[^a-z0-9\-]', '', anchor)
        # Remove consecutive hyphens
        anchor = re.sub(r'-+', '-', anchor)
        # Remove leading/trailing hyphens
        anchor = anchor.strip('-')
        return anchor

    def _generate_toc(self, data: dict) -> str:
        """Generate a table of contents for the markdown summary."""
        toc = '\n## Table of Contents\n\n'
        
        # Add the main summary table sections
        for conf in self.MARKDOWN_SUMMARY_TABLES:
            toc += f'- [{conf["title"]}](#{self._github_anchor(conf["title"])})\n'
        
        # Add main sections
        sections = [
            'Devices',
            'Networks',
            'Firewall Groups',
            'Firewall Rules',
            'Traffic Rules',
            'Port Profiles',
            'Port Forwarding',
            'Settings',
            'Users (Clients) with Fixed IPs',
            'WLAN Configs',
            'WLAN Groups'
        ]
        
        for section in sections:
            toc += f'- [{section}](#{self._github_anchor(section)})\n'
            
            # Add device subsections
            if section == 'Devices':
                for d in sorted(data['device'].values(), key=lambda x: x.get('name', '').lower()):
                    device_name = d.get('name', 'Unknown')
                    toc += f'  - [{device_name}](#{self._github_anchor(device_name)})\n'
        
        # Add WireGuard Users if they exist
        if 'wireguard_user' in data:
            toc += f'- [WireGuard Users](#{self._github_anchor("WireGuard Users")})\n'
        
        toc += '\n'
        return toc

    def _generate_md_summary(self, data: dict) -> str:
        data['__ports'] = {}
        data['__fixedip'] = {}
        data['__devices'] = {}
        data['__traffic_rules'] = {}
        networks = {}
        s = '\n## Devices\n'
        for d in data['device'].values():
            data['__devices'][d.get("name")] = {
                'sortkey': d.get("name", '').lower(),
                'name': f'[{d.get("name")}](#{d.get("name")})',
                'ip': d['ip'],
                'type': d['type'],
                'model': d['model'],
                'mac': '``' + d['mac'] + '``',
            }
            s += f'\n### {d.get("name")}\n\nip={d["ip"]} type={d["type"]} ' \
                 f'model={d["model"]} serial={d.get("serial")} mac=``{d["mac"]}``\n\n'
            s += f'* version={d["version"]} ' \
                 f'kernel_version={d.get("kernel_version", "n/a")}\n'
            s += f'* adopted={d["adopted"]} ' \
                 f'adoption_completed={d["adoption_completed"]} id={d["_id"]}\n'
            if 'provisioned_at' in d:
                s += f'* Provisioned at {d["provisioned_at"]}\n'
            s += f'* Network config: type={d["config_network"]["type"]} ' \
                 f'ip={d["config_network"].get("ip", "n/a")}\n'
            if 'last_uplink' in d:
                lu = d['last_uplink']
                s += f'* Last Uplink: port_idx={lu.get("port_idx", "unknown")} ' \
                     f'type={lu["type"]} uplink_mac={lu["uplink_mac"]} ' \
                     f'uplink_remote_port=' \
                     f'{lu.get("uplink_remote_port", "n/a")}\n'
            if 'ethernet_table' in d:
                s += '* Ethernet Table:\n'
                for e in sorted(d['ethernet_table'], key=lambda x: x['name']):
                    s += f'\t* {e["name"]} / port {e.get("num_port", "n/a")} ' \
                         f'/ ``{e["mac"]}``\n'
            if 'port_table' in d:
                s += '* Port Table:\n'
                for p in sorted(d['port_table'], key=lambda x: x['port_idx']):
                    s += f'\t* port_idx ``{p["port_idx"]}`` '
                    s += self._sorted_dict_repr(p, ignore_keys=['port_idx'])
                    s += '\n'
                    if d['type'] not in ['usw', 'usg', 'uxg']:
                        continue
                    try:
                        data['__ports'][f'{d["name"]} / {p["port_idx"]}'] = {
                            'Device / Port': f'{d["name"]} / {p["port_idx"]}',
                            'sortkey': f'{d["name"]} / {p["port_idx"]:04}'.lower(),
                            'PoE Enabled': 'yes' if p.get('port_poe', False) else '',
                            'PoE Active': 'yes' if p.get('poe_good', False) else '',
                            'Speed': p.get('speed'),
                            'Name': '',
                            'VLAN(s)': '',
                        }
                    except KeyError as ex:
                        logger.error(
                            'ERROR: KeyError %s while processing port %s of device: %s',
                            ex, p['port_idx'],
                            json.dumps(d, indent=4, sort_keys=True, cls=MagicJSONEncoder)
                        )
                        raise
            if 'port_overrides' in d:
                s += '* Port Overrides:\n'
                for p in sorted(d['port_overrides'], key=lambda x: x['port_idx']):
                    if 'name' not in p:
                        p['name'] = f'Port {p["port_idx"]}'
                    s += f'\t* port_idx=``{p["port_idx"]}`` name=``{p["name"]}`` '
                    if 'portconf_id' in p:
                         s += f'config=``{data["portconf"][p["portconf_id"]]["name"]}`` '
                    s += self._sorted_dict_repr(
                        p, ignore_keys=['port_idx', 'name', 'portconf_id', 'port_security_mac_address']
                    )
                    s += '\n'
                    portkey = f'{d["name"]} / {p["port_idx"]}'
                    if portkey not in data['__ports']:
                        data['__ports'][portkey] = {}
                    data['__ports'][portkey]['Name'] = p['name']
                    if d['type'] not in ['usw', 'usg']:
                        continue
                    data['__ports'][portkey]['VLAN(s)'] = ''
                    if 'portconf_id' in p:
                        data['__ports'][portkey]['VLAN(s)'] = f'Profile ``{data["portconf"][p["portconf_id"]]["name"]}``'
                    elif p.get('forward') == 'all':
                        data['__ports'][portkey]['VLAN(s)'] = 'ALL'
                    elif p.get('forward') == 'native':
                        data['__ports'][portkey]['native_networkconf_id'] = p['native_networkconf_id']
            s += '\n'
        s += '\n## Networks\n\n'
        for r in sorted(
            data['networkconf'].values(), key=lambda x: x['name']
        ):
            netname = f'``{r["name"]}``'
            if 'ip_subnet' in r:
                netname += ' ' + r['ip_subnet']
            if 'networkgroup' in r:
                netname += ' (' + r['networkgroup'] + ')'
            if 'vlan' in r:
                netname += f' VLAN {r["vlan"]}'
            networks[str(r['_id'])] = netname
            s += '* ' + netname + ': ' + self._sorted_dict_repr(
                r, ignore_keys=['name', 'ip_subnet', 'networkgroup']
            ) + '\n'
        s += '\n## Firewall Groups\n\n'
        for g in sorted(data['firewallgroup'].values(), key=lambda x: x['name']):
            s += f'* ``{g["name"]}`` {g["group_type"]} (id {g["_id"]}) ' \
                 f'members: {g["group_members"]}\n'
        s += '\n## Firewall Rules\n\n'
        for r in sorted(
            data['firewallrule'].values(),
            key=lambda x: (str(x['ruleset']), str(x['rule_index']))
        ):
            s += f'* ``{r["ruleset"]} {r["rule_index"]}`` "{r["name"]}": '
            s += self._sorted_dict_repr(
                r, ignore_keys=['ruleset', 'rule_index', 'name', 'site_id']
            ) + '\n'
        if 'traffic_rule' in data:
            client_macs = {
                x['mac']: x.get('name', x.get('hostname')) for x in data['user'].values()
            }
            tmp, data['__traffic_rules'] = self._do_traffic_rules(data['traffic_rule'], networks, client_macs)
            s += tmp
        s += '\n## Port Profiles\n\n'
        for r in sorted(
            data['portconf'].values(), key=lambda x: x['name']
        ):
            s += f'* ``{r["name"]}``'
            s += ': ' + self._sorted_dict_repr(
                r, ignore_keys=['name', 'site_id']
            ) + '\n'
        s += '\n## Port Forwarding\n\n'
        for r in sorted(
            data['portforward'].values(), key=lambda x: x['name']
        ):
            s += f'* ``{r["name"]}``'
            s += ': ' + self._sorted_dict_repr(
                r, ignore_keys=['name', 'site_id']
            ) + '\n'
        s += '\n## Settings\n\n'
        for r in sorted(
                data['setting'].values(), key=lambda x: x['key']
        ):
            s += f'* ``{r["key"]}`` ({r["_id"]}): '
            s += self._sorted_dict_repr(
                r, ignore_keys=['name', '_id']
            ) + '\n'
        s += '\n## Users (Clients) with Fixed IPs\n\n'
        users = [x for x in data['user'].values() if x.get('fixed_ip', '') != '']
        for r in sorted(users, key=lambda x: x['fixed_ip']):
            net = data["networkconf"].get(
                r.get('network_id'), {}
            ).get('name', r.get('network_id', 'unknown'))
            s += f'* ``{r["fixed_ip"]}`` "{r.get("name", r.get("hostname"))}" ' \
                 f'``{r["mac"]}`` (network={net} use_fixedip={r["use_fixedip"]}'
            tmpfixed = {
                'IP': r['fixed_ip'],
                'Name': r.get("name", r.get("hostname")),
                'MAC': '``' + r['mac'] + '``',
                'Network': net,
                'WLAN': '',
                'ipaddr': r['fixed_ip']
            }
            if 'wlanconf_id' in r:
                tmpfixed['WLAN'] = data['wlanconf'].get(
                    r['wlanconf_id'], {}
                ).get('name', r['wlanconf_id'])
                s += f' wlanconf={tmpfixed["WLAN"]}'
            s += ')\n'
            data['__fixedip'][r['fixed_ip']] = tmpfixed
        s += '\n## WLAN Configs\n\n'
        for r in sorted(
                data['wlanconf'].values(), key=lambda x: x['name']
        ):
            s += f'* ``{r["name"]}`` ({r["_id"]}): '
            s += self._sorted_dict_repr(
                r, ignore_keys=['name', '_id', 'x_passphrase', 'x_iapp_key']
            ) + '\n'
        s += '\n## WLAN Groups\n\n'
        for r in sorted(
                data['wlangroup'].values(), key=lambda x: x['name']
        ):
            s += f'* ``{r["name"]}`` ({r["_id"]}): '
            s += self._sorted_dict_repr(
                r, ignore_keys=['name', '_id']
            ) + '\n'
        if 'wireguard_user' in data:
            s += '\n## WireGuard Users\n\n'
            for r in sorted(
                data['wireguard_user'].values(), key=lambda x: x['name']
            ):
                s += f'* ``{r["name"]}`` {r["interface_ip"]} ({r["_id"]}): '
                s += self._sorted_dict_repr(
                    r, ignore_keys=['name', '_id']
                ) + '\n'
        # some of this is calculated, so we prepend it...
        prefix: str = '# UniFi controller configuration summary\n'
        
        # Add table of contents
        prefix += self._generate_toc(data)
        
        for x in data['__ports'].values():
            if 'native_networkconf_id' in x:
                x['VLAN(s)'] = networks[x['native_networkconf_id']]
        for conf in self.MARKDOWN_SUMMARY_TABLES:
            prefix += f'\n## {conf["title"]}\n\n'
            rows = []
            for item in sorted(
                data[conf['collection']].values(),
                key=lambda x: x[conf['sort']]
            ):
                rows.append([item.get(x) for x in conf['fields']])
            prefix += tabulate(
                rows, headers=conf['fields'], tablefmt='github'
            ) + '\n'
        return prefix + s

    def run(self, fpath=None):
        if fpath:
            logger.info('Using existing backup at: %s', fpath)
        else:
            fpath = self.download_backup()
        logger.debug('Decrypting broken zip file...')
        zip_bytes = self.decrypt_file(fpath)
        broken_zip_path = mkstemp(suffix='.zip')[1]
        with open(broken_zip_path, 'wb') as fh:
            fh.write(zip_bytes)
        logger.debug('Wrote broken zip file to: %s', broken_zip_path)
        try:
            fixed_zip_path = mkstemp(suffix='.zip')[1]
            logger.debug('Running zip -FF')
            proc = subprocess.run(
                [
                    'bash', '-c',
                    f'yes | zip -FF {broken_zip_path} --out {fixed_zip_path}'
                ]
            )
            logger.debug('zip -FF exited %d', proc.returncode)
            assert proc.returncode == 0
        finally:
            logger.debug('Removing %s', broken_zip_path)
            os.unlink(broken_zip_path)
        try:
            logger.debug('Opening zip file: %s', fixed_zip_path)
            with ZipFile(fixed_zip_path, 'r') as zfile:
                files = zfile.namelist()
                for f in ['system.properties', 'format', 'version']:
                    if f not in files:
                        continue
                    content = zfile.read(f)
                    logger.info(f'Read: {f}')
                    with open(
                        os.path.join(self.outdir, os.path.basename(f)), 'wb'
                    ) as fh:
                        fh.write(content)
                        logger.debug('Wrote: %s', os.path.basename(f))
                for f in ['db.gz']:
                    if f not in files:
                        continue
                    content = zfile.read(f)
                    logger.info(f'Read: {f}')
                    decompressed = gzip.decompress(content)
                    rows = bson.decode_all(decompressed)
                    result = {}
                    curr_coll = None
                    for row in rows:
                        if len(row.keys()) == 2 and 'collection' in row.keys():
                            curr_coll = row['collection']
                            result[curr_coll] = {}
                            continue
                        result[curr_coll][str(row['_id'])] = row
                    logger.debug('Decoded %d collections: %s', len(result.keys()), sorted(list(result.keys())))
                    try:
                        with open(os.path.join(self.outdir, f'{f}.md'), 'w') as fh:
                            fh.write(self._generate_md_summary(result))
                        logger.debug('Wrote: %s.md', f)
                    finally:
                        # Dump individual collection files if requested
                        if self.dump_all_collections:
                            for coll_name, coll_data in result.items():
                                if coll_name not in self.IGNORE_COLLECTIONS:
                                    coll_file = os.path.join(self.outdir, f'{coll_name}.json')
                                    with open(coll_file, 'w') as fh:
                                        fh.write(json.dumps(
                                            coll_data, cls=MagicJSONEncoder, sort_keys=True, indent=4
                                        ))
                                    logger.debug('Wrote: %s', coll_file)
                        for k in self.IGNORE_COLLECTIONS:
                            result.pop(k, None)
                        with open(os.path.join(self.outdir, f'{f}.json'), 'w') as fh:
                            fh.write(json.dumps(
                                result, cls=MagicJSONEncoder, sort_keys=True, indent=4
                            ))
                        logger.debug('Wrote: %s.json', f)
        finally:
            logger.debug('Remove %s', fixed_zip_path)
            os.unlink(fixed_zip_path)

    def decrypt_file(self, fpath):
        with open(fpath, 'rb') as in_file:
            cipher = AES.new(self.KEY, AES.MODE_CBC, self.IV)
            return cipher.decrypt(in_file.read())

    def download_backup(self):
        self._baseurl: str = os.environ['UNIFI_URL']
        self._username: str = os.environ['UNIFI_USER']
        self._passwd: str = os.environ['UNIFI_PASS']
        logger.info(
            'Got creds for user %s on %s', self._username, self._baseurl
        )
        cookies = self.get_cookies(
            self._baseurl, self._username, self._passwd
        )
        try:
            logger.info('Getting list of backups')
            r = requests.post(
                urljoin(self._baseurl, '/api/s/default/cmd/backup'),
                json={'cmd': "list-backups"},
                cookies=cookies, verify=False
            )
            logger.debug(
                'Request to /api/s/default/cmd/backup returned HTTP %d '
                'with headers %s and content: %s', r.status_code,
                r.headers, r.text
            )
            r.raise_for_status()
            j = r.json()
            assert j['meta']['rc'] == 'ok'
            assert len(j['data']) > 0
            latest = sorted(j['data'], key=lambda x: x['datetime'])[-1]
            dt = parse(latest['datetime']).replace()
            age = datetime.now(get_localzone()) - dt
            if age > timedelta(days=1, hours=5):
                logger.critical('ERROR: newest backup is %s old' % age)
                raise SystemExit(1)
            else:
                logger.debug('Newest backup is %s old' % age)
            dl_url = urljoin(
                self._baseurl, '/dl/autobackup/%s' % latest['filename']
            )
            logger.info('Downloading: %s' % dl_url)
            r = requests.get(dl_url, cookies=cookies, verify=False)
            r.raise_for_status()
            with open(self.destpath + '.tmp', 'wb') as fh:
                fh.write(r.content)
            logger.info('Written to: %s', self.destpath + '.tmp')
            fsize = os.stat(self.destpath + '.tmp').st_size
            if fsize != latest['size']:
                logger.critical(
                        'ERROR: Downloaded file size (%d) does not match '
                        'API (%d)' % (fsize, latest['size'])
                )
                raise SystemExit(1)
            logger.debug(
                'Downloaded file matches size reported by API; '
                'removing .tmp'
            )
            os.rename(self.destpath + '.tmp', self.destpath)
        finally:
            logger.debug('Logging out from controller...')
            r = requests.get(
                urljoin(self._baseurl, '/logout'), cookies=cookies, verify=False
            )
            r.raise_for_status()
        return self.destpath

    def get_cookies(self, baseurl, username, password):
        url = urljoin(baseurl, '/api/login')
        logger.info('Logging in to controller via: %s' % url)
        r = requests.post(
            url, json={'username': username, 'password': password}, verify=False
        )
        r.raise_for_status()
        return r.cookies


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
    p = argparse.ArgumentParser(description='UniFi backup')
    p.add_argument('-f', '--file', dest='fpath', type=str, default=None,
                   help='Existing file to decrypt')
    p.add_argument('-o', '--outdir', dest='outdir', type=str,
                   default=os.getcwd(),
                   help='output directory (default: PWD)')
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='debug-level output.')
    p.add_argument('-O', '--outfile', dest='outfile', type=str,
                   default='/root/unifi-autobackup.unf',
                   help='Output file; default: /root/unifi-autobackup.unf')
    p.add_argument('-D', '--dump-all-collections', dest='dump_all_collections',
                   action='store_true', default=False,
                   help='Dump each collection to a separate JSON file')
    args = p.parse_args(sys.argv[1:])
    if args.verbose:
        set_log_debug()
    else:
        set_log_info()
    UniFiBackup(args.outdir, args.outfile, args.dump_all_collections).run(fpath=args.fpath)
