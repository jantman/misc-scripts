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

* Python >= 3.4
* transmission-rpc 1.0.0 (``pip install transmission-rpc==1.0.0``)

License
-------

Copyright 2018 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG
---------


2019-04-22 Jason Antman <jason@jasonantman.com>:
  - Add -R option to remove finished/seeding torrents

2018-12-05 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging

from transmission_rpc import Client, DEFAULT_PORT

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
            address=host, port=port, user=user, password=passwd
        )
        logger.debug('Connected to Transmission')

    def run(self, batch=2, rm_finished=False):
        logger.debug('Getting current torrents...')
        torrents = self._get_active_torrents()
        logger.info('Found %d active torrent(s)...', len(torrents))
        for t in torrents:
            self._set_file_priority(t, batch)
        logger.info('Done.')
        if rm_finished:
            self._rm_finished_torrents()

    def _set_file_priority(self, torrent, batch):
        t_id = torrent._fields['id'].value
        logger.info(
            'Checking files in torrent %d (%s)', t_id,
            torrent._get_name_string()
        )
        files = self._client.get_files(ids=[t_id])[t_id]
        logger.debug('Torrent has %d files', len(files))
        incomplete = []
        for _id in sorted(files.keys(), key=lambda x: files[x]['name']):
            pct = (files[_id]['completed'] / files[_id]['size']) * 100
            logger.debug(
                'File %d: %s - %.2f%% complete - %s, priority %s', _id,
                files[_id]['name'], pct,
                'selected' if files[_id]['selected'] else 'unselected',
                files[_id]['priority']
            )
            if pct < 100:
                incomplete.append(_id)
        logger.debug('%d files in torrent are incomplete', len(incomplete))
        if len(incomplete) > batch:
            selected = incomplete[:batch]
        else:
            selected = incomplete
        logger.debug('First %d incomplete files: %s', len(selected), selected)
        data = {t_id: {}}
        for _id in files:
            data[t_id][_id] = {
                'selected': files[_id]['selected'],
                'priority': 'high' if _id in selected else 'normal'
            }
        logger.info(
            'Ensuring high priority on first %d incomplete files: %s',
            len(selected), ', '.join([
                '%d (%s)' % (x, files[x]['name']) for x in selected
            ])
        )
        logger.debug('set_files: %s', data)
        self._client.set_files(data)

    def _get_active_torrents(self):
        r = self._client.get_torrents()
        active = []
        for t in r:
            logger.debug(
                'Torrent %s (%s) - %s, %.2f%% complete',
                t._fields['id'].value, t._get_name_string(),
                t.status, t.progress
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
                t._fields['id'].value, t._get_name_string(),
                t.status, t.progress
            )
            if t.status != 'seeding' or t.progress != 100:
                continue
            logger.info(
                'Removing finished/seeding torrent: %s (%s)',
                t._fields['id'].value, t._get_name_string()
            )
            self._client.remove_torrent(t._fields['id'].value)


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Prioritize files in active Transmission downloads in '
                    'lexicographic order.'
    )
    p.add_argument('-H', '--host', dest='host', action='store', type=str,
                   default='127.0.0.1',
                   help='Transmission host/ip (default: 127.0.0.1)')
    p.add_argument('-p', '--port', dest='port', action='store', type=int,
                   default=DEFAULT_PORT,
                   help='Transmission port (default: %d)' % DEFAULT_PORT)
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
    ).run(args.batch, rm_finished=args.rm_finished)
