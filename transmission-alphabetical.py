#!/usr/bin/env python
"""
transmission-alphabetical.py
============================

Python script (using the transmission-rpc package) to adjust files in the
Transmission bittorrent client so they download in alphabetical order. Intended
to be run via a cron job, or some other method of running on a set interval.

Uses transmission-rpc <https://github.com/Trim21/transmission-rpc> to connect
to Transmission's RPC interface, list all non-paused torrents, and then set the
lexicographically first N non-complete files to high priority.

Canonical Source:

https://github.com/jantman/misc-scripts/blob/master/transmission-alphabetical.py

Dependencies
------------

* Python >= 3.6 (tested up to 3.9)
* transmission-rpc 3.2.2 (``pip install transmission-rpc==3.2.2``)
* humanize

License
-------

Copyright 2018-2025 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG
---------

2025-01-28 Jason Antman <jason@jasonantman.com>:
  - Update to use transmission-rpc 7.0.11 for python3.13 compatibility

2021-08-25 Jason Antman <jason@jasonantman.com>:
  - Require Python >= 3.6 for f-strings and humanize package
  - Add support for identifying stalled torrents and removing them

2021-07-27 Jason Antman <jason@jasonantman.com>:
  - Add support for asking for more peers on any torrent with 0 peers connected

2021-04-11 Jason Antman <jason@jasonantman.com>:
  - Division by zero fix

2021-01-07 Jason Antman <jason@jasonantman.com>:
  - Fix for transmission-rpc 3.2.2 on Python 3.9

2019-04-22 Jason Antman <jason@jasonantman.com>:
  - Add -R option to remove finished/seeding torrents

2018-12-05 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging
from datetime import datetime, timedelta
from humanize import naturaldelta

from transmission_rpc import Client

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class TransmissionPrioritizer(object):

    def __init__(self, host, port, user, passwd):
        self._host = host
        self._port = port
        self._user = user
        self._pass = passwd
        logger.debug(
            'Connecting to Transmission at %s:%s as user %s',
            host, port, user
        )
        self._client = Client(
            host=host, port=port, username=user, password=passwd
        )
        logger.debug('Connected to Transmission')

    def run(
        self, batch=2, rm_finished=False, reannounce=False, stalled_days=7,
        prune_stalled_pct=25
    ):
        logger.debug('Getting current torrents...')
        torrents = self._get_active_torrents()
        logger.info('Found %d active torrent(s)...', len(torrents))
        for t in torrents:
            self._set_file_priority(t, batch)
            if reannounce and t.fields['peersConnected'] < 1:
                logger.debug(
                    'Reannounce (ask for more peers) torrent %s (%s)',
                    t.id, t.name
                )
                res = self._client._request(
                    'torrent-reannounce', {}, [t.id], True
                )
                logger.info(
                    'Reannounce (ask for more peers) torrent %s (%s); '
                    'result: %s',
                    t.id, t.name, res.get('result', 'unknown')
                )
        logger.info('Done.')
        if rm_finished:
            self._rm_finished_torrents()
        self._find_stalled_downloads(
            stalled_days=stalled_days, prune_stalled_pct=prune_stalled_pct
        )

    def _set_file_priority(self, torrent, batch):
        t_id = torrent.fields['id']
        logger.info(
            'Checking files in torrent %d (%s)', t_id,
            torrent.name
        )
        files = torrent.get_files()
        logger.debug('Torrent has %d files: %s', len(files), files)
        incomplete = []
        for file in sorted(files, key=lambda x: x.name):
            if file.size == 0:
                logger.debug('File %s has zero size', file.name)
                incomplete.append(file.id)
                continue
            pct = (file.completed / file.size) * 100
            logger.debug(
                'File %d: %s - %.2f%% complete - %s, priority %s', file.id,
                file.name, pct,
                'selected' if file.selected else 'unselected',
                file.priority
            )
            if pct < 100:
                incomplete.append(file.id)
        logger.debug('%d files in torrent are incomplete', len(incomplete))
        if len(incomplete) > batch:
            selected = incomplete[:batch]
        else:
            selected = incomplete
        logger.debug('First %d incomplete files: %s', len(selected), selected)
        data = {t_id: {}}
        for _id in files:
            data[t_id][_id] = {
                'selected': files[_id].selected,
                'priority': 'high' if _id in selected else 'normal'
            }
        logger.info(
            'Ensuring high priority on first %d incomplete files: %s',
            len(selected), ', '.join([
                '%d (%s)' % (x, files[x].name) for x in selected
            ])
        )
        logger.debug('set_files: %s', data)
        self._client.set_files(data)

    def _find_stalled_downloads(self, stalled_days=7, prune_stalled_pct=25):
        now = datetime.now()
        threshold = now - timedelta(days=stalled_days)
        r = self._client.get_torrents()
        stalled = []
        for t in r:
            if t.status in ['seeding']:
                continue
            if t.rateDownload > 0 or t.rateUpload > 0:
                continue
            if t.date_done is not None:
                continue
            try:
                eta = t.eta
            except ValueError:
                eta = ''
            if t.date_active >= threshold or t.date_added >= threshold:
                continue
            logger.debug(
                'Torrent %s (%s) - %s, %.2f%% complete; eta=%s '
                'rateUp=%s rateDown=%s; added=%s started=%s '
                'active=%s done=%s',
                t.fields['id'], t.name,
                t.status, t.progress, eta, t.rateUpload,
                t.rateDownload, t.date_added, t.date_started, t.date_active,
                t.date_done
            )
            active = 'NEVER'
            if t.date_active.year > 1971:
                active = naturaldelta(now - t.date_active) + ' ago'
            print(
                f'STALLED: Torrent {t.fields["id"]} '
                f'({t.name}): '
                f'{t.progress:.2f}% complete, '
                f'added {naturaldelta(now - t.date_added)} ago, '
                f'started {naturaldelta(now - t.date_started)} ago, '
                f'active {active}'
            )
            stalled.append(t)
            if t.progress < prune_stalled_pct:
                logger.info(
                    'PRUNING Stalled torrent: %s (%s)',
                    t.fields['id'], t.name
                )
                self._client.remove_torrent(
                    t.fields['id'], delete_data=True
                )
        logger.debug('%d of %d torrents stalled', len(stalled), len(r))
        return stalled

    def _get_active_torrents(self):
        r = self._client.get_torrents()
        active = []
        for t in r:
            try:
                eta = t.eta
            except ValueError:
                eta = ''
            logger.debug(
                'Torrent %s (%s) - %s, %.2f%% complete; eta=%s '
                'queue_position=%s rateUp=%s rateDown=%s',
                t.fields['id'], t.name,
                t.status, t.progress, eta, t.queue_position, t.rate_upload,
                t.rate_download
            )
            if t.status in ['downloading', 'download pending']:
                active.append(t)
        logger.debug('%d of %d torrents active', len(active), len(r))
        return active

    def _rm_finished_torrents(self):
        logger.debug('Looking for finished torrents to remove...')
        r = self._client.get_torrents()
        active = []
        for t in r:
            logger.debug(
                'Torrent %s (%s) - %s, %.2f%% complete',
                t.fields['id'], t.name,
                t.status, t.progress
            )
            if t.status != 'seeding' or t.progress != 100:
                continue
            logger.info(
                'Removing finished/seeding torrent: %s (%s)',
                t.fields['id'], t.name
            )
            self._client.remove_torrent(t.fields['id'])


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Prioritize files in active Transmission downloads in '
                    'lexicographic order.'
    )
    p.add_argument('-H', '--host', dest='host', action='store', type=str,
                   default='127.0.0.1',
                   help='Transmission host/ip (default: 127.0.0.1)')
    p.add_argument('-p', '--port', dest='port', action='store', type=int,
                   default=9091, help='Transmission port (default: 9091)')
    p.add_argument('-u', '--username', dest='user', action='store', type=str,
                   default=None, help='Transmission username (default: None)')
    p.add_argument('-P', '--password', dest='passwd', action='store', type=str,
                   default=None, help='Transmission password (default: None)')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-n', '--batch-size', dest='batch', action='store', type=int,
                   default=2,
                   help='Number of files to set at high priority at a time, '
                        'per torrent. (default: 2)')
    p.add_argument('-R', '--remove-complete', dest='rm_finished',
                   action='store_true', default=False,
                   help='Also remove seeding / 100%% complete torrents ('
                        'remove only the torrent, not data).')
    p.add_argument('-r', '--reannounce', dest='reannounce', action='store_true',
                   default=False,
                   help='If no peers, reannounce (ask tracker for more)')
    p.add_argument('-s', '--stalled-days', dest='stalled_days', action='store',
                   type=int, default=7,
                   help='Consider torrents stalled after no activity for this '
                        'number of days (default: 7)')
    p.add_argument('-S', '--prune-stalled-pct', dest='prune_stalled_pct',
                   action='store', type=float, default=25,
                   help='Prune stalled torrents less than this percent '
                        'complete (default: 25)')
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
    if args.verbose > 1:
        set_log_debug()
    elif args.verbose == 1:
        set_log_info()

    TransmissionPrioritizer(
        args.host, args.port, args.user, args.passwd
    ).run(args.batch, rm_finished=args.rm_finished, reannounce=args.reannounce)
