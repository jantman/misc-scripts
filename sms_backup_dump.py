#!/usr/bin/env python
"""
Android SMS Backup and Restore dump to HTML
===========================================

Dump the XML SMS and call logs from the
`SMS Backup and Restore <https://play.google.com/store/apps/details?id=com.
riteshsahu.SMSBackupRestore&hl=en>`_ Android app, including MMS.

Requirements
------------

lxml

License
-------

Copyright 2016 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
Free for any use provided that patches are submitted back to me.

CHANGELOG
---------

2016-09-14 Jason Antman <jason@jasonantman.com>:
  - initial version of script
"""

import sys
import os
import argparse
import logging
from datetime import datetime, timedelta
from base64 import b64decode
from textwrap import dedent

try:
    from lxml import etree
except ImportError:
    try:
        # normal cElementTree install
        import cElementTree as etree
    except ImportError:
        try:
            # normal ElementTree install
            import elementtree.ElementTree as etree
        except ImportError:
            raise SystemExit("Failed to import ElementTree from any known place")

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

CALL_TYPES = {
    '1': 'Incoming call from',
    '2': 'Outgoing call to',
    '3': 'Missed call from',
    '4': 'Voicemail from',
    '5': 'Rejected call from',
    '6': 'Refused List call from'
}

SMS_TYPES = {
    '1': 'Received from',
    '2': 'Sent to',
    '3': 'Draft to'
}

class SMSdumper(object):

    def __init__(self, outdir, sms_path, calls_path=None):
        self.sms_path = os.path.abspath(os.path.expanduser(sms_path))
        self.calls_path = None
        if calls_path is not None:
            self.calls_path = os.path.abspath(os.path.expanduser(calls_path))
        self.outdir = os.path.abspath(os.path.expanduser(outdir))
        self.mediadir = os.path.join(self.outdir, 'media')
        logger.debug("outdir=%s sms=%s calls=%s", self.outdir, self.sms_path,
                     self.calls_path)
        self.calls = {}
        self.smses = {}

    def run(self):
        """main entry point"""
        if self.calls_path is not None:
            self.calls = self.parse_calls()
            logger.debug("Calls: %s", self.calls)
        else:
            logger.warning("No calls XML path specified; do not have call logs.")
        if not os.path.exists(self.mediadir):
            os.makedirs(self.mediadir)
        self.smses = self.parse_sms()
        logger.debug("All SMSes: %s", self.smses)
        for name in set(self.calls.keys() + self.smses.keys()):
            self.write_contact_output(name)

    def parse_calls(self):
        """parse calls XML"""
        tree = etree.parse(self.calls_path)
        root = tree.getroot()
        calls = {}
        for call in root.xpath('//call'):
            name = call.attrib['number']
            if ('contact_name' in call.attrib and
                    call.attrib['contact_name'] != ''):
                name = call.attrib['contact_name']
            if name not in calls:
                calls[name] = {}
            dt = datetime.fromtimestamp(float(call.attrib['date']) / 1000.0)
            calls[name][dt] = call.attrib
        return calls

    def parse_sms(self):
        """parse SMS XML"""
        tree = etree.parse(self.sms_path,
                           parser=etree.XMLParser(huge_tree=True))
        root = tree.getroot()
        smses = {}
        for sms in root.xpath('//sms'):
            name = sms.attrib['address']
            if ('contact_name' in sms.attrib and
                        sms.attrib['contact_name'] != ''):
                name = sms.attrib['contact_name']
            if name not in smses:
                smses[name] = {}
            dt = datetime.fromtimestamp(float(sms.attrib['date']) / 1000.0)
            smses[name][dt] = sms.attrib
        # now parse MMS...
        for mms in root.xpath('//mms'):
            name = mms.attrib['address']
            if ('contact_name' in mms.attrib and
                    mms.attrib['contact_name'] != ''):
                name = mms.attrib['contact_name']
            if name not in smses:
                smses[name] = {}
            dt = datetime.fromtimestamp(float(mms.attrib['date']) / 1000.0)
            attr = {x: mms.attrib[x] for x in mms.attrib}
            parts = self.parse_mms_parts(mms, name, float(mms.attrib['date']))
            if len(parts) > 0:
                attr['mms_parts'] = parts
            addrs = []
            for addr in mms.iter('addr'):
                addrs.append(addr.attrib)
            if len(addrs) > 0:
                attr['mms_addresses'] = addrs
            smses[name][dt] = attr
        return smses

    def parse_mms_parts(self, mms, name, float_ts):
        """parse parts from MMS; write the long ones to disk"""
        parts = []
        # parse the parts
        for part in mms.iter('part'):
            seq = part.attrib['seq']
            foo = {}
            for x in part.attrib:
                if x == 'data' and len(part.attrib[x]) > 200:
                    foo[x] = 'REDACTED'
                    foo['data_file_path'] = self.write_mms_data_file(
                        part.attrib[x], seq, name, float_ts, part.attrib['cl'])
                else:
                    foo[x] = part.attrib[x]
            parts.append(foo)
        return parts

    def write_mms_data_file(self, data, seq, name, float_ts, orig_fname):
        """
        Write MMS data to a file

        :param data: data to write
        :type data: str
        :param seq: part sequence
        :type seq: str
        :param name: contact name or number
        :type name: str
        :param float_ts: message timestamp
        :type float_ts: float
        :param orig_fname: original filename
        :type orig_fname: str
        :return: path to the written file, relative to self.mediadir
        :rtype: str
        """
        fn = '%s_%f_%s_%s' % (name, float_ts, seq, orig_fname)
        fpath = os.path.join(self.mediadir, self.fs_safe_name(fn))
        logger.debug("Writing file to: %s", fpath)
        try:
            data = b64decode(data)
        except:
            pass
        with open(fpath, 'wb') as fh:
            fh.write(data)
        return os.path.join('media', self.fs_safe_name(fn))

    def write_contact_output(self, name):
        """
        Write output for one contact.

        :param name: contact name (calls/smses key)
        :type name: str
        """
        c_data = {}
        if name in self.calls:
            for dt, data in self.calls[name].iteritems():
                data['_record_type'] = 'call'
                while dt in c_data:
                    dt = dt + timedelta(microseconds=1)
                c_data[dt] = data
        if name in self.smses:
            for dt, data in self.smses[name].iteritems():
                data['_record_type'] = 'sms'
                while dt in c_data:
                    dt = dt + timedelta(microseconds=1)
                c_data[dt] = data
        html = self.contact_html(name, c_data)
        fpath = os.path.join(self.outdir, self.fs_safe_name(name + '.html'))
        with open(fpath, 'w') as fh:
            fh.write(html.encode('utf-8'))
        logger.info('HTML for %s written to: %s', name, fpath)

    def contact_html(self, name, contact_data):
        """return HTML string for the contact"""
        s = dedent("""
        <html>
        <head>
        <title>Calls and SMS for %s</title>
        <style type="text/css">
        .date {
            font-weight: bold;
        }

        .identifier {
            font-weight: bold;
        }

        .outgoing {
            color: blue;
        }

        .incoming {
            color: red;
        }

        .imgdiv {
            width: 200px;
            height: 200px;
        }

        img {
            width: auto;
            height: auto;
            max-width: 200;
            max-height: 200;
        }
        </style>
        </head>
        <body>
        """ % name)
        s += "<h1>Calls and SMS for %s</h1>\n" % name
        for dt in sorted(contact_data.keys()):
            s += self.format_record(dt, contact_data[dt])
        s += "</body>\n</html>\n"
        return s

    def format_record(self, dt, data):
        s = '<p>'
        s += '<span class="date">'
        s += dt.strftime("%a %Y-%m-%d %H:%M:%S") + ': '
        s += '</span>'
        if data['_record_type'] == 'call':
            s += self.format_call(data)
        elif 'mms_parts' in data:
            s += self.format_mms(data)
        else:
            s += self.format_sms(data)
        s += "</p>\n"
        return s

    def format_call(self, data):
        """return formatted HTML for a call"""
        call_type = CALL_TYPES.get(
            data['type'], 'Unknown call type %s from' % data['type'])
        identifier_class = 'outgoing'
        if data['type'] != '2':
            identifier_class = 'incoming'
        duration = timedelta(seconds=int(data['duration']))
        return '<span class="identifier %s">%s %s</span> %s call' % (
            identifier_class,
            call_type,
            self.format_number(data['number']),
            duration
        )

    def format_sms(self, data):
        """return formatted HTML for an MMS"""
        sms_type = SMS_TYPES.get(
            data['type'], 'Unknown SMS type %s' % data['type'])
        identifier_class = 'outgoing'
        if data['type'] == '1':
            identifier_class = 'incoming'
        return '<span class="identifier %s">%s %s:</span> %s' % (
            identifier_class,
            sms_type,
            self.format_number(data['address']),
            data['body']
        )

    def format_mms(self, data):
        """return formatted HTML for an MMS"""
        sms_type = SMS_TYPES.get(
            data['msg_box'], 'Unknown MMS msg_box %s' % data['msg_box'])
        identifier_class = 'outgoing'
        if data['msg_box'] == '1':
            identifier_class = 'incoming'
        from_addr = 'unknown'
        for addr in data['mms_addresses']:
            if addr['type'] == '137':
                from_addr = addr['address']
        s = '<span class="identifier %s">%s %s:</span>' % (
            identifier_class,
            sms_type,
            self.format_number(from_addr)
        )
        for part in data['mms_parts']:
            if part['ct'] == 'application/smil':
                continue
            if part['ct'] == 'text/plain':
                s += part['text'] + '<br />'
            elif part['ct'].startswith('image/'):
                s += '<a href="%s"><img src="%s" ' \
                     'width="200" height="200" /></a>' % (
                    part['data_file_path'], part['data_file_path']
                )
            else:
                if 'data_file_path' in part:
                    s += 'Unsupported attachment content type %s: %s' % (
                        part['ct'],
                        '<a href="%s">%s</a>' % (part['data_file_path'],
                                                 part['data_file_path'])
                    )
                else:
                    s += 'Unsupported attachment content type: %s' % part['ct']
        return s

    @staticmethod
    def fs_safe_name(fname):
        """
        Generate a filesystem-safe string filename for a file
        :param fname: desired filename
        :type fname: str
        :return: safe filename
        :rtype: str
        """
        x = "".join(
            [
                c for c in fname if (c.isalpha() or
                                     c.isdigit() or
                                     c in ['-', '_', '.'])
            ]
        ).rstrip()
        return x

    @staticmethod
    def format_number(num):
        """format a phone number"""
        if len(num) == 10:
            return '(' + num[:3] + ')' + num[3:6] + '-' + num[6:]
        elif len(num) == 11:
            return num[0] + '-' + num[1:4] + '-' + num[4:7] + '-' + num[7:]
        elif len(num) == 7:
            return num[:3] + '-' + num[3:]
        return num


def parse_args(argv):
    """
    parse arguments/options
    """
    p = argparse.ArgumentParser(description='Dump XML call and SMS logs from '
                                'Android SMS Backup and Restore app to HTML')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-o', '--outdir', dest='outdir', action='store', type=str,
                   default='./sms_out',
                   help='output directory (default: ./sms_out)')
    p.add_argument('-c', '--calls-xml', dest='calls_xml', action='store',
                   type=str, help='Calls XML file path', default=None)
    p.add_argument('SMS_XML', action='store', type=str,
                   help='SMS XML file path')

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

    script = SMSdumper(args.outdir, args.SMS_XML, calls_path=args.calls_xml)
    script.run()
