#!/usr/bin/env python
"""
aws_delete_user.py
==================

Script using boto3 to delete an IAM User, including all of the associated
resources and attachments that need to be deleted first. Includes dry-run option.

If you have ideas for improvements, or want the latest version, it's at:
<https://github.com/jantman/misc-scripts/blob/master/aws_delete_user.py>

License
-------

Copyright 2019 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG
---------

2019-01-04 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import argparse
import logging

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    sys.stderr.write('ERROR: You must "pip install boto3"\n')
    raise SystemExit(1)

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger()

# suppress boto3 internal logging below WARNING level
boto3_log = logging.getLogger("boto3")
boto3_log.setLevel(logging.WARNING)
boto3_log.propagate = True

# suppress botocore internal logging below WARNING level
botocore_log = logging.getLogger("botocore")
botocore_log.setLevel(logging.WARNING)
botocore_log.propagate = True


class IamUserDeleter(object):

    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        logger.debug('Connecting to IAM as service resource...')
        self._iam = boto3.resource('iam')

    def run(self, username):
        logger.debug('Getting IAM User: %s', username)
        user = self._iam.User(username)
        try:
            # see if the user exists
            if self.dry_run:
                logger.info(
                    'DRY RUN for deletion of IAM User %s (%s)',
                    username, user.user_id
                )
            else:
                logger.info(
                    'Preparing to delete IAM User %s (%s)',
                    username, user.user_id
                )
        except ClientError as ex:
            if ex.response.get('Error', {}).get('Code', '') == 'NoSuchEntity':
                logger.info(
                    'User %s does not exist or was already deleted', username
                )
                raise SystemExit(0)
            raise
        self._access_keys(user)
        self._certificates(user)
        self._login_profile(user)
        self._mfa(user)
        self._attached_user_policies(user)
        self._inline_policies(user)
        self._group_memberships(user)
        self._ssh_public_keys(user)
        self._service_specific_creds(user)
        if self.dry_run:
            logger.info(
                'DRY RUN - Would Delete IAM User %s (%s)', username,
                user.user_id
            )
            return
        logger.info('Deleting IAM User "%s" (%s)', username, user.user_id)
        user.delete()

    def _format_call_log(self, clsname, del_meth, del_kwargs):
        if del_meth == 'delete' and del_kwargs == {}:
            return ''
        s = ' by calling %s.%s(' % (clsname, del_meth)
        if del_kwargs == {}:
            return '%s)' % s
        return '%s**%s)' % (s, del_kwargs)

    def _loop_and_delete(self, user, collection_attr, title,
                         id_attr='id', del_meth='delete', del_kwargs={}):
        collection = getattr(user, collection_attr)
        items = list(collection.all())
        if len(items) == 0:
            logger.info('User has zero %ss.', title)
            return
        for i in items:
            _id = getattr(i, id_attr)
            if self.dry_run:
                logger.info(
                    'DRY RUN - Would Delete %s %s%s', title, _id,
                    self._format_call_log(
                        i.__class__.__name__, del_meth, del_kwargs
                    )
                )
                continue
            logger.info('Deleting %s %s', title, _id)
            deleter = getattr(i, del_meth)
            deleter(**del_kwargs)

    def _access_keys(self, user):
        self._loop_and_delete(user, 'access_keys', 'Access Key')

    def _certificates(self, user):
        self._loop_and_delete(
            user, 'signing_certificates', 'Signing Certificate'
        )

    def _login_profile(self, user):
        lp = user.LoginProfile()
        try:
            logger.debug('Found LoginProfile created on %s', lp.create_date)
        except ClientError as ex:
            if ex.response.get('Error', {}).get('Code', '') == 'NoSuchEntity':
                logger.info('User has no Login Profile.')
                return
        if self.dry_run:
            logger.info(
                'DRY RUN - Would Delete Login Profile created on %s',
                lp.create_date
            )
            return
        logger.info('Deleting Login Profile created on %s', lp.create_date)
        lp.delete()

    def _mfa(self, user):
        self._loop_and_delete(
            user, 'mfa_devices', 'MFA Device', id_attr='serial_number',
            del_meth='disassociate'
        )

    def _attached_user_policies(self, user):
        self._loop_and_delete(
            user, 'attached_policies', 'Attached Policy', id_attr='arn',
            del_meth='detach_user', del_kwargs={'UserName': user.name}
        )

    def _inline_policies(self, user):
        self._loop_and_delete(
            user, 'policies', 'Inline Policy', id_attr='name'
        )

    def _group_memberships(self, user):
        self._loop_and_delete(
            user, 'groups', 'Group Membership', id_attr='name',
            del_meth='remove_user', del_kwargs={'UserName': user.name}
        )

    def _ssh_public_keys(self, user):
        client = self._iam.meta.client
        resp = client.list_ssh_public_keys(UserName=user.name)['SSHPublicKeys']
        if len(resp) == 0:
            logger.info('User has zero SSH Public Keys')
            return
        for k in resp:
            if self.dry_run:
                logger.info(
                    'DRY RUN - Would Delete SSH Public Key %s',
                    k['SSHPublicKeyId']
                )
                continue
            logger.info(
                'Deleting SSH Public Key %s for user %s',
                k['SSHPublicKeyId'], user.name
            )
            client.delete_ssh_public_key(
                UserName=user.name, SSHPublicKeyId=k['SSHPublicKeyId']
            )

    def _service_specific_creds(self, user):
        client = self._iam.meta.client
        resp = client.list_service_specific_credentials(
            UserName=user.name
        )['ServiceSpecificCredentials']
        if len(resp) == 0:
            logger.info('User has zero Service Specific Credentials')
            return
        for k in resp:
            if self.dry_run:
                logger.info(
                    'DRY RUN - Would Delete Service Specific Credential %s'
                    '(Service=%s ServiceUserName=%s)',
                    k['ServiceSpecificCredentialId'],
                    k['ServiceName'], k['ServiceUserName']
                )
                continue
            logger.info(
                'Deleting Service Specific Credential %s'
                '(Service=%s ServiceUserName=%s) for user %s',
                k['ServiceSpecificCredentialId'],
                k['ServiceName'], k['ServiceUserName'], user.name
            )
            client.delete_service_specific_credential(
                UserName=user.name,
                ServiceSpecificCredentialId=k['ServiceSpecificCredentialId']
            )


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(
        description='Delete an IAM user and all its dependencies'
    )
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False, help='verbose output')
    p.add_argument('USER_NAME', action='store', type=str,
                   help='Name of IAM User to delete')
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

    IamUserDeleter(dry_run=args.dry_run).run(args.USER_NAME)
