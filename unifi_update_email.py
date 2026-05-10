#!/usr/bin/env python3
"""
Companion to ``unifi_backup.py``: email a firmware-update report when any
UniFi devices have updates available.

Reads the JSON output from ``unifi_backup.py`` (``db.gz.json``) and, if any
devices have firmware updates available, sends an HTML email listing them
with their current and available versions. Exits silently with 0 if no
updates are pending or the JSON file is missing.

Reads SMTP config from env: ``SMTP_HOST`` (``host:port``), ``SMTP_USER``,
``SMTP_PASSWORD``, ``EMAIL_ADDR``.

MIT license. Copyright 2026 Jason Antman.

Canonical source:

https://github.com/jantman/misc-scripts/blob/master/unifi_update_email.py
"""

import html as html_lib
import json
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

UPGRADE_SUFFIX = ' (upgrade available)'


def main(json_path):
    if not os.path.exists(json_path):
        print(f'UniFi JSON not found at {json_path}; skipping update email.')
        return 0

    with open(json_path) as f:
        data = json.load(f)

    pending = []
    for key, dev in data.get('__devices', {}).items():
        avail = dev.get('available', '')
        if not avail.endswith(UPGRADE_SUFFIX):
            continue
        pending.append((
            key,
            dev.get('model', ''),
            dev.get('version', ''),
            avail[:-len(UPGRADE_SUFFIX)].strip(),
        ))

    if not pending:
        print('No UniFi device firmware updates available.')
        return 0

    pending.sort(key=lambda r: r[0].lower())

    rows = '\n'.join(
        '<tr><td>{n}</td><td>{m}</td><td>{c}</td><td>{a}</td></tr>'.format(
            n=html_lib.escape(n),
            m=html_lib.escape(m),
            c=html_lib.escape(c),
            a=html_lib.escape(a),
        )
        for n, m, c, a in pending
    )
    body = (
        '<html><body>\n'
        '<p>The following UniFi devices have firmware updates available:</p>\n'
        '<table border="1" cellpadding="4" cellspacing="0">\n'
        '<tr><th>Device</th><th>Model</th>'
        '<th>Current Version</th><th>Available Version</th></tr>\n'
        f'{rows}\n'
        '</table>\n'
        '</body></html>\n'
    )

    addr = os.environ['EMAIL_ADDR']
    host, port = os.environ['SMTP_HOST'].split(':')
    port = int(port)

    msg = MIMEMultipart('alternative')
    plural = 's' if len(pending) != 1 else ''
    msg['Subject'] = f'UniFi firmware updates available ({len(pending)} device{plural})'
    msg['From'] = addr
    msg['To'] = addr
    msg.attach(MIMEText(body, 'html'))

    s = smtplib.SMTP(host, port)
    s.ehlo()
    s.starttls()
    s.ehlo()
    s.login(addr, os.environ['SMTP_PASSWORD'])
    s.sendmail(addr, addr, msg.as_string())
    s.quit()

    print(f'Emailed UniFi firmware update report: {len(pending)} device(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'unifi/db.gz.json'))
