#!/usr/bin/env python

"""
Script to dump all Skype logs from a main.db file to HTML.

Default output is a directory of HTML files, with an index file and per-chat files.

Copyright 2012 Jason Antman <jason@jasonantman.com> All Rights Reserved.
Free for any use provided that patches are submitted back to me.

The latest version of this script can be found at:
<https://github.com/jantman/misc-scripts/blob/master/dump_skype_logs.py>

Requires Python Modules:
sqlite3
getopt

Changelog:
2012-12-13 Jason Antman <jason@jasonantman.com>:
  - initial version

TODO:
- colors for special message types ??

"""

import sqlite3
import getopt
import sys
import os
import codecs
import datetime
from math import log
from datetime import timedelta 
import re
from BeautifulSoup import BeautifulSoup

# CONFIG
OUTDIR = "skypeout/"
FILE = "main.db"
DATE_FORMATS = {'message': '%H:%M:%S', 'filename': '%Y-%m-%d'}
HIDE_DATES = False
HIGHLIGHT_WORDS = ['highlight', 'words']
HIGHLIGHT_COLOR = "#FFFF00"
# END CONFIG

if not os.path.exists(OUTDIR):
    os.makedirs(OUTDIR)

# TODO: test that FILE exists

#
# Functions to format the various record types for output as html
#

def set_contact_colors(skypename, CONTACT_COLORS):
    global COLORS
    if skypename not in CONTACT_COLORS:
        CONTACT_COLORS[skypename] = COLORS[len(CONTACT_COLORS)]
    return CONTACT_COLORS

def make_safe_filename(f):
    return re.sub(r'[^A-Za-z0-9_]', '', f)

"""
Human friendly file size
credit to joctee on StackOverflow: http://stackoverflow.com/a/10171475/211734
"""
def sizeof_fmt(num):
    unit_list = zip(['B', 'kB', 'MB', 'GB', 'TB', 'PB'], [0, 0, 1, 2, 2, 2])
    if num > 1:
        exponent = min(int(log(num, 1024)), len(unit_list) - 1)
        quotient = float(num) / 1024**exponent
        unit, num_decimals = unit_list[exponent]
        format_string = '{:.%sf} {}' % (num_decimals)
        return format_string.format(quotient, unit)
    if num == 0:
        return '0 bytes'
    if num == 1:
        return '1 byte'

def format_timestamp(t):
    global DATE_FORMATS
    return datetime.datetime.fromtimestamp(t).strftime(DATE_FORMATS['message'])

def format_video(a):
    s = "<li>"
    s += "<strong>%s Video starting</strong>: " % format_timestamp(a['timestamp'])
    s += "dimensions=%s, duration=%s id=%s" % (a['dimensions'], a['duration'], a['id'])
    s += "</li>\n"
    return s

def format_call_start_end(msg_type, body):
    xml = BeautifulSoup(body)
    if msg_type == 30:
        s = "<strong>Start call</strong>, participants: "
    else:
        s = "<strong>End call</strong>, participants: "
        for x in xml.partlist.findAll("part"):
            if x.duration is not None and x["identity"] is not None:
                s += "%s (%s) " % (x["identity"], timedelta(seconds=int(x.duration.string)))
    return s

def highlight_message(msg):
    global HIGHLIGHT_WORDS, HIGHLIGHT_COLOR
    m = " %s " % msg
    m_hlt = m
    for r in HIGHLIGHT_WORDS:
        m_hlt = re.sub('\s+' + r + '\s+', ' <span style="background-color: ' + HIGHLIGHT_COLOR + ';">' + r + '</span> ', m_hlt, 0, re.I)
    was_changed = False
    if m_hlt != m:
        was_changed = True
    return (m_hlt, was_changed)

def format_message(a, color, key, cur_fname):
    s = ""
    grep_line = ""
    was_highlight = False
    if a['msg_type'] == 39 or a['msg_type'] == 30:
        s += "<strong>%s</strong> " % (format_timestamp(a['timestamp']))
        # call start or end, with duration, in <partlist> (participant list)
        if a['body'] is not None:
            s += format_call_start_end(a['msg_type'], a['body'])
        return (s, "")
    s += "<strong>%s <span style=\"color: #%s;\">%s</span>:</strong> " % (format_timestamp(a['timestamp']), color, a['author'])
    if a['msg_type'] == 61:
        # regular message
        if a['body'] is not None:
            (msg_str, was_highlight) = highlight_message(a['body'])
            s += msg_str
    elif a['msg_type'] == 50:
        # contact request
        s += " <strong>Contact Request:</strong> "
        if a['body'] is not None:
            s += a['body']
    elif a['msg_type'] == 51:
        # ignore. probably confirmation of contact added, or signed on, or something like that
        return ("", "")
    elif a['msg_type'] == 68:
        # ignore it, it's a file transfer summary message
        return ("", "")
    else:
        if a['body'] is not None:
            s += a['body'].replace("<", "&lt;").replace(">", "&gt;")
        s += "<em>(MESSAGE author=%s msg_type=%s id=%s)</em>" % (a['author'], a['msg_type'], a['id'])
    final_s = "<li><a name=\"%s\"></a>%s</li>\n" % (key, s)
    if was_highlight is True:
        # format and return grep_line
        grep_line = "<li><a href=\"%s#%s\">%s</a>: %s</li>\n" % (cur_fname, key, cur_fname, s)
    return (final_s, grep_line)

def format_transfer(a):
    s = "<li>"
    s += "<strong>%s File Transfer</strong> " % format_timestamp(a['timestamp'])
    if a['transfer_type'] == 1:
        # incoming
        s += "from "
    else:
        # outgoing
        s += "to "
    s += "%s. File <tt>%s</tt> (local path <tt>%s</tt>). %s transferred in %s. status=%s." % (a['partner'], a['filename'], a['filepath'], sizeof_fmt(float(a['filesize'])), timedelta(seconds=(a['finishtime'] - a['timestamp'])), a['status'])
    s += "</li>\n"
    return s

def format_chat(a):
    s = "<li>"
    s += "<strong>%s Start Chat with %s</strong> " % (format_timestamp(a['timestamp']), a['partner'])
    s += "</li>\n"
    return s

def format_debuginfo(s, identity):
    ret = ""
    incoming = ""
    foo = re.search('video send stream \d+ \(l\): ID: \d+, Type: \d+/\d+, Res: (\d+x\d+), Codec: ([^,]+), FPS ([^,]+),', s)
    if foo is not None:
        ret = "Outgoing Video %s, %s FPS. " % (foo.group(1), foo.group(3))
    ptn = "%s's video recv:\s+Res: ([^,]+), Color: ([^,]+), FPS: ([^,]+)" % re.escape(identity)
    foo = re.search(ptn, s)
    if foo is not None:
        ret += "Incoming Video %s, %s FPS." % (foo.group(1), foo.group(3))
    return ret

def format_call(a):
    s = "<li>"
    s += "<strong>%s %s Call</strong> " % (format_timestamp(a['timestamp']), ("Incoming" if a['is_incoming'] == 1 else "Outgoing"))
    if not a['duration'] is None:
        s += "(duration %s)" % timedelta(seconds=int(a['duration']))
    s += " %s:" % (("from" if a['is_incoming'] == 1 else "to"))
    for x in a['members']:
        s += " %s" % a['members'][x]['identity']
        if a['members'][x]['call_duration'] is not None:
            s += " (call_duration %s" % timedelta(seconds= a['members'][x]['call_duration'])
        if a['members'][x]['debuginfo'] is not None:
            s += ", " + format_debuginfo(a['members'][x]['debuginfo'], a['members'][x]['identity'])
        s += ")"
    s += "</li>\n"
    return s

def write_per_day_file(s, OUTDIR, fname, conv_identity, filedate):
    fh = codecs.open((OUTDIR + fname), "w", "utf-8")
    fh.write("<html><head><title>Skype Conversation with " + conv_identity + " on " + filedate + "</title></head></html><body>\n")
    fh.write("<ul>\n" + body_str + "</ul>\n")
    fh.write("</body></html>")
    fh.close

#
# End format functions
#

conn = sqlite3.connect(FILE)
if conn == None:
    print("ERROR: could not connect to database file '" + FILE + "'.")
    sys.exit(1)

conn.row_factory = sqlite3.Row
cursor = conn.cursor()
c2 = conn.cursor()
c1 = conn.cursor()

c1.execute("SELECT id,identity,type,displayname FROM conversations")
c1rows = c1.fetchall()

FILES = []

COLORS = ['FF0000', '0000FF', '00FF00', 'FFFF00', '00FFFF']

# loop over each conversation
for c1row in c1rows:
    conv_id = c1row['id']
    conv_identity = c1row['identity']

    EVENTS = {}

    CONTACT_COLORS = {}

    # add chats to EVENTS dict
    cursor.execute("SELECT id, name, timestamp, dialog_partner, adder, participants FROM chats WHERE conv_dbid=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'chat', 'timestamp': row['timestamp'], 'partner': row['dialog_partner'], 'id': row['id']}
        if row['timestamp'] in EVENTS:
            print "WARNING: timestamp " + str(row['timestamp']) + " for chat "+ str(row['id']) +" already in EVENTS dict."
        key = ( row['timestamp'] * 100 )
        while key in EVENTS:
            key = key + 1
        EVENTS[key] = foo
        print(foo)

    # add calls to EVENTS dict
    cursor.execute("SELECT id, begin_timestamp, host_identity, duration, name, is_incoming, conv_dbid, current_video_audience FROM calls WHERE conv_dbid=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'call', 'timestamp': row['begin_timestamp'], 'host': row['host_identity'], 'duration': row['duration'], 'is_incoming': row['is_incoming'], 'conv_dbid': row['conv_dbid'], 'current_video_audience': row['current_video_audience'], 'id': row['id'], 'members': {}}
        print("call:", foo)

        # get data from callmembers
        c2.execute("SELECT id,identity,dispname,call_duration,videostatus,debuginfo,guid,start_timestamp,call_db_id FROM callmembers WHERE call_db_id=" + str(row['id']))
        rows2 = c2.fetchall()

        for row2 in rows2:
            foo['members'][row2['identity']] = row2
        key = ( row['begin_timestamp'] * 100 )
        while key in EVENTS:
            key = key + 1
        EVENTS[key] = foo

    # add messages to EVENTS dict
    cursor.execute("SELECT id, convo_id, chatname, author, from_dispname, dialog_partner, timestamp, type, sending_status, consumption_status, body_xml, participant_count, chatmsg_type, chatmsg_status, call_guid FROM messages WHERE convo_id=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'message', 'timestamp': row['timestamp'], 'author': row['author'], 'from_dispname': row['from_dispname'], 'msg_type': row['type'], 'body': row['body_xml'], 'id': row['id']}

        key = ( row['timestamp'] * 100 )
        while key in EVENTS:
            key = key + 1
        EVENTS[key] = foo

    # add file transfers to EVENTS dict
    cursor.execute("SELECT id, type, partner_handle, partner_dispname, status, starttime, finishtime, filepath, filename, filesize, bytestransferred FROM transfers WHERE convo_id=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'transfer', 'timestamp': row['starttime'], 'finishtime': row['finishtime'], 'transfer_type': row['type'], 'partner': row['partner_handle'], 'status': row['status'], 'filepath': row['filepath'], 'filename': row['filename'], 'filesize': row['filesize'], 'bytestx': row['bytestransferred'], 'id': row['id']}

        key = ( row['starttime'] * 100 )
        while key in EVENTS:
            key = key + 1
        EVENTS[key] = foo

    # add videos to EVENTS dict
    cursor.execute("SELECT id, dimensions, duration_hqv, duration_vgad2, duration_ltvgad2, timestamp, hq_present, convo_id FROM videos WHERE convo_id=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'video', 'timestamp': row['timestamp'], 'dimensions': row['dimensions'], 'duration': (row['duration_hqv'] + row['duration_vgad2'] + row['duration_ltvgad2']), 'id': row['id']}

        key = ( row['timestamp'] * 100 )
        while key in EVENTS:
            key = key + 1
        EVENTS[key] = foo

    # make HTML body strings
    toc_str = ""
    body_str = ""
    all_body_str = ""
    grep_str = ""

    cur_ts = 0
    cur_date = ""
    cur_day_fname = ""
    conv_identity_safe = make_safe_filename(conv_identity)
    num_day_files = 0

    for key in sorted(EVENTS.iterkeys()):
        print(key, EVENTS[key])
        foo = datetime.datetime.fromtimestamp(EVENTS[key]['timestamp']).strftime('%a %b %d %Y')
        if HIDE_DATES is True:
            cur_day_fname = "%s_%03d.html" % (str(conv_identity_safe), num_day_files)
        else:
            filedate = datetime.datetime.fromtimestamp(cur_ts).strftime(DATE_FORMATS['filename'])
            cur_day_fname = str(conv_identity_safe) + "_" + filedate + ".html"

        if foo != cur_date:
            # make the filename for the new file
            # done making filename
            if cur_ts != 0:
                # write out the per-day file
                all_body_str += body_str
                num_day_files += 1
                print "writing cur_day_fname=%s" % cur_day_fname
                write_per_day_file(body_str, OUTDIR, cur_day_fname, conv_identity_safe, cur_date)
            cur_ts = EVENTS[key]['timestamp']
            cur_date = foo
            if HIDE_DATES is True:
                body_str = "<li><strong>BEGIN DAY %d</strong></li>" % (num_day_files+1)
            else:
                body_str = "<li><strong>%s</strong></li>" % foo
        if EVENTS[key]['type'] == "chat":
            body_str += format_chat(EVENTS[key])
        elif EVENTS[key]['type'] == "call":
            body_str += format_call(EVENTS[key])
        elif EVENTS[key]['type'] == "message":
            CONTACT_COLORS = set_contact_colors(EVENTS[key]['author'], CONTACT_COLORS)
            (msg_line, grep_line) = format_message(EVENTS[key], CONTACT_COLORS[EVENTS[key]['author']], key, cur_day_fname)
            body_str += msg_line
            grep_str += grep_line
        elif EVENTS[key]['type'] == "transfer":
            body_str += format_transfer(EVENTS[key])
        elif EVENTS[key]['type'] == "video":
            body_str += format_video(EVENTS[key])
        else:
            print "%s: %s" % (key, EVENTS[key]['type'])
            sys.stderr.write("ERROR: invalid type for key " + str(key) + "\n")

    # ok, got all strings, start the output...
    if len(all_body_str) > 0:
        outfile = OUTDIR + str(conv_identity_safe) + "-all.html"
        FILES.append(outfile)
        fh = codecs.open(outfile, "w", "utf-8")
        fh.write("<html><head><title>Skype Conversation with " + conv_identity + "</title></head></html><body>\n")
        fh.write(toc_str)
        fh.write("<ul>\n" + all_body_str + "</ul>\n")
        fh.write("</body></html>")
        fh.close

    if len(grep_str) > 0:
        grepfile = OUTDIR + str(conv_identity_safe) + "-highlights.html"
        fh = codecs.open(grepfile, "w", "utf-8")
        fh.write("<html><head><title>Highlights in Skype Conversation with " + conv_identity + "</title></head></html><body>\n")
        fh.write("<ul>\n" + grep_str + "</ul>\n")
        fh.write("</body></html>")
        fh.close
# env loop over conversations

conn.close()

"""

table CallMembers
id, identity, dispname, call_duration, videostatus, call_name, guid, real_identity, start_timestamp, call_db_id
# type  1=incoming 2=outgoing

table ChatMembers
id, chatname, identity, adder

table Chats
id, name, timestamp, dialog_partner, adder, participants, active_members

table Conversations
id, identity, type, displayname, 

table Messages
id, convo_id, chatname, author, from_dispname, dialog_partner, timestamp, type, sending_status, consumption_status, body_xml, participant_count, chatmsg_type, chatmsg_status, call_guid, 

table Transfers
id, type, partner_handle, partner_dispname, status, starttime, finishtime, filepath, filename, filesize, bytestransferred, convo_id, 

table Videos
id, dimensions, duration_hqv, duration_vgad2, duration_ltvgad2, timestamp, hq_present, convo_id, 

table Calls
id, begin_timestamp, host_identity, duration, name, is_incoming, start_timestamp, conv_dbid, current_video_audience

<http://stephanietan.boldersecurity.com/2011/04/analyzing-skype-chat-and-call-logs.html>
<http://kosi2801.freepgs.com/2009/12/03/messing_with_the_skype_40_database.html>
<http://betrayedspousesclub.blogspot.com/2012/07/skype-maindb.html>

"""
