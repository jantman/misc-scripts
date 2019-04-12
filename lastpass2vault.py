#!/usr/bin/env python
"""
lastpass2vault
==============

Interactive script to copy your saved passwords and other information from
LastPass to a HashiCorp Vault server.

Requirements
------------

Python 2.7 or >= 3.4

hvac==0.2.17
lastpass-python==0.3.1

License
-------

Copyright 2017-2019 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

Usage
-----

1. Ensure ``VAULT_ADDR`` is exported in the environment.
2. Ensure that a valid Vault token is either exported as the ``VAULT_TOKEN``
  environment variable, or in a token file specified with
  ``-f`` / ``--token-file`` (default ``~/.vault-token``).
3. ``lastpass2vault.py [-v] LASTPASS_USERNAME``

CHANGELOG
---------

2019-04-12 Jason Antman <jason@jasonantman.com>:
  - Bump recommended lastpass-python version to 0.3.1 since my PR has been merged
  - Python 3 compatibility

2017-10-22 Jason Antman <jason@jasonantman.com>:
  - Add support for notes field using my fork of lastpass-python (PR pending)

2017-03-05 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import argparse
import logging
from getpass import getpass
from copy import deepcopy

import hvac
import lastpass

if sys.version_info[0] >= 3:
    input_func = input
else:
    input_func = raw_input

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

# suppress logging from requests
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)
requests_log.propagate = True

class LastpassToVault(object):
    """main class"""

    def __init__(self, vault_token_file, lp_user):
        """
        init method, run at class creation

        :param token_file: path to Vault token file
        :type token_file: str
        :param lp_user: LastPass username
        :type lp_user: str
        """
        self.vault = self._connect_vault(vault_token_file)
        self.lp = self._connect_lp(lp_user)

    def _connect_vault(self, token_file):
        """
        Connect to Vault; return the connection object

        :param token_file: path to Vault token file
        :type token_file: str
        :returns: connected HVAC Client object
        :rtype: :py:obj:`hvac.Client`
        """
        if 'VAULT_ADDR' not in os.environ:
            raise RuntimeError('Please export VAULT_ADDR')
        url = os.environ['VAULT_ADDR']
        token = self._get_vault_token(token_file)
        logger.info('Connecting to Vault at: %s', url)
        client = hvac.Client(url=url, token=token)
        assert client.is_authenticated()
        return client

    def _get_vault_token(self, token_file):
        """
        Find and return the Vault token

        :param token_file: path to Vault token file
        :type token_file: str
        :returns: Vault token
        :rtype: str
        """
        token_file = os.path.abspath(os.path.expanduser(token_file))
        if 'VAULT_TOKEN' in os.environ:
            logger.info('Using vault token from VAULT_TOKEN environment var')
            return os.environ['VAULT_TOKEN']
        if os.path.exists(token_file):
            logger.info('Using Vault token from %s', token_file)
            with open(token_file, 'r') as fh:
                return fh.read().strip()
        raise RuntimeError('Could not find Vault token; please export '
                           'VAULT_TOKEN or write to ~/.vault-token')

    def _connect_lp(self, lp_user):
        """
        Connect to LastPass; return the connection.

        :param lp_user: LastPass username
        :type lp_user: str
        :returns: connected LastPass Vault object
        :rtype: lastpass.vault.Vault
        """
        logger.debug('Authenticating to LastPass with username: %s', lp_user)
        passwd = getpass('LastPass Password: ').strip()
        mfa = input_func(
            'LastPass MFA (OTP or YubiKey; Return for no MFA): '
        ).strip()
        if mfa == '':
            logger.info('Authenticating to LastPass without MFA')
            lp = lastpass.Vault.open_remote(lp_user, passwd)
        else:
            logger.info('Authenticating to LastPass with MFA code %s', mfa)
            lp = lastpass.Vault.open_remote(
                lp_user, passwd, multifactor_password=mfa)
        return lp

    def run(self, prefix, no_prune=False):
        """
        Begin running the copy.

        :param prefix: prefix to write under in Vault
        :type prefix: str
        :param no_prune: do not prune removed LastPass accounts from Vault
        :type no_prune: bool
        """
        if prefix.endswith('/'):
            prefix = prefix[:-1]
        data = self._lp_get()
        logger.warning('Writing to Vault under prefix: %s', prefix)
        paths = self._vault_write(prefix, data)
        if no_prune:
            logger.warning('Not pruning deleted LastPass entries from Vault')
            return
        self._prune_vault(prefix, paths)

    def _vault_write(self, prefix, data):
        """
        Write the LastPass data to Vault

        :param prefix: prefix to write under in Vault
        :type prefix: str
        :param data: lastpass data, as returned by ``_lp_get()``
        :type data: dict
        :returns: list of all paths written under prefix
        :rtype: list
        """
        all_paths = []
        group_count = 0
        secret_count = 0
        for group in sorted(data.keys()):
            group_count += 1
            for name, acct_data in data[group].items():
                path = self._path_for_secret(prefix, group, name)
                all_paths.append(path)
                logger.debug('Writing secret to: %s', path)
                self.vault.write(path, **acct_data)
                secret_count += 1
        logger.warning('Wrote %d secrets in %d groups to Vault',
                       secret_count, group_count)
        return all_paths

    def _prune_vault(self, prefix, paths):
        """
        Prune any secrets under prefix that aren't in paths

        :param prefix: Vault prefix for lastpass secrets
        :type prefix: str
        :param paths: list of paths written from LastPass
        :type paths: list
        """
        logger.info('Pruning removed LastPass entries from Vault')
        all_keys = self._list_vault_path_recursive(
            os.path.join('secret', prefix)
        )
        pruned = 0
        for k in all_keys:
            if k not in paths:
                logger.debug('Pruning: %s', k)
                self.vault.delete(k)
                pruned += 1
        logger.warning('Pruned %d removed LastPass entries from Vault',
                       pruned)

    def _list_vault_path_recursive(self, path):
        """
        Return a list of all keys under the specified Vault path.

        :param path: path in vault to list
        :return: list of keys under path
        :rtype: list
        """
        keys = []
        for k in self.vault.list(path)['data']['keys']:
            p = os.path.join(path, k)
            if not k.endswith('/'):
                keys.append(p)
                continue
            # it's a directory
            keys.extend(self._list_vault_path_recursive(p))
        return keys

    def _path_for_secret(self, prefix, group, name):
        """
        Return a Vault path for the specified secret.

        :param prefix: prefix to write under in Vault
        :type prefix: str
        :param group: group name the secret is in (can be empty string)
        :type group: str
        :param name: name of the secret in LastPass
        :type name: str
        :return: path to write secret at in Vault
        :rtype: str
        """
        if group.strip() == '':
            return 'secret/%s/%s' % (prefix, name)
        return 'secret/%s/%s/%s' % (prefix, group, name)

    def _lp_get(self):
        """
        Get all accounts from LastPass; return a dict of account name/path
        to data.

        :return: lastpass data, dict of Group (path) to dict of per-account
          name to dict of data for that account name
        :rtype: dict
        """
        d = {}
        for acct in self.lp.accounts:
            if acct.group not in d:
                d[acct.group] = {}
            a = deepcopy(vars(acct))
            if a['name'].strip() == '':
                a['name'] = a['id']
            del a['group']
            del a['id']
            d[acct.group][a['name']] = a
            logger.debug('Got secret "%s" in group "%s" (id %s)',
                         acct.name, acct.group, acct.id)
        return d

def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='copy LastPass data to Vault')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-P', '--vault-prefix', dest='prefix', action='store',
                   type=str, default='lastpass',
                   help='prefix to store under in vault; default: lastpass/')
    p.add_argument('-f', '--token-file', dest='token_file', action='store',
                   type=str, default=os.path.expanduser('~/.vault-token'),
                   help='Vault token file (default: ~/.vault-token)')
    p.add_argument('-p', '--no-prune', dest='no_prune', action='store_true',
                   default=False,
                   help='do not prune deleted LastPass entries from Vault')
    p.add_argument('LASTPASS_USER', action='store', type=str,
                   help='LastPass username')
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

    script = LastpassToVault(args.token_file, args.LASTPASS_USER)
    script.run(args.prefix, no_prune=args.no_prune)
