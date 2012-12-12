#!/usr/bin/env python

"""
Script to dump all Skype logs from a main.db file to HTML.

Default output is a directory of HTML files, with an index file and per-chat files.

Copyright 2012 Jason Antman <jason@jasonantman.com> All Rights Reserved.

Requires Python Modules:
sqlite3
getopt

Changelog:
2012-11-15 Jason Antman <jason@jasonantman.com>:
  - initial version

"""

import sqlite3
import getopt
import sys

options, remainder = getopt.getopt(sys.argv[1:], 'f:o:v', ['file=', 'outdir=', 'verbose', ])

OUTDIR = "skypeout/"
FILE = "main.db"

if not os.path.exists(OUTDIR):
    os.mkdirs(OUTDIR)

for opt, arg in options:
    if opt in ('-o', '--outdir'):
        OUTDIR = arg
    elif opt in ('-v', '--verbose'):
        verbose = True
    elif opt in ('-f', '--file'):
        FILE = arg

# TODO: test that FILE exists

conn = sqlite3.connect(FILE)
if conn == None:
    print "ERROR: could not connect to database file '" + FILE + "'."
    sys.exit(1)

conn.row_factory = sqlite3.Row
cursor = conn.cursor()
c2 = conn.cursor()
c1 = conn.cursor()

c1.execute("SELECT id,identity,type,displayname FROM Conversations")
c1rows = c1.fetchall()

FILES = []

for c1row in c1rows:
    conv_id = c1row['id']
    conv_identity = c1row['identity']

    EVENTS = {}

    # add chats to EVENTS dict
    cursor.execute("SELECT id, name, timestamp, dialog_partner, adder, participants FROM chats WHERE conv_dbid=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'chat', 'timestamp': row['timestamp'], 'partner': row['dialog_partner'], 'id': row['id']}
        if row['timestamp'] in EVENTS:
            print "WARNING: timestamp " + str(row['timestamp']) + " for chat "+ str(row['id']) +" already in EVENTS dict."
        key = ( row['timestamp'] * 100 )
        while not key in EVENTS:
            key = key + 1
        EVENTS[key] = foo

    # add calls to EVENTS dict
    cursor.execute("SELECT id, begin_timestamp, host_identity, duration, name, is_incoming, conv_dbid, current_video_audience FROM calls WHERE conv_dbid=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'call', 'timestamp': row['begin_timestamp'], 'host': row['host_identity'], 'duration': row['duration'], 'is_incoming': row['is_incoming'], 'conv_dbid': row['conv_dbid'], 'current_video_audience': row['current_video_audience'], 'id': row['id']}

        # get data from callmembers
        c2.execute("SELECT id,identity,dispname,call_duration,videostatus,guid,start_timestamp,call_db_id FROM callmembers WHERE call_db_id=" + str(row['id']))
        members = ""
        rows2 = c2.fetchall()
        for row2 in rows2:
            members = "%s%s (start=%d duration=%d videostatus=%d" (members, row2['identity'], row2['start_timestamp'], row2['call_duration'], row2['videostatus'])
        foo['members'] = members
        key = ( row['begin_timestamp'] * 100 )
        while not key in EVENTS:
            key = key + 1
        EVENTS[key] = foo
    
    # add messages to EVENTS dict
    cursor.execute("SELECT id, convo_id, chatname, author, from_dispname, dialog_partner, timestamp, type, sending_status, consumption_status, body_xml, participant_count, chatmsg_type, chatmsg_status, call_guid FROM messages WHERE convo_id=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'message', 'timestamp': row['timestamp'], 'author': row['author'], 'from_dispname': row['from_dispname'], 'msg_type': row['type'], 'body': row['body_xml'], 'id': row['id']}

        key = ( row['timestamp'] * 100 )
        while not key in EVENTS:
            key = key + 1
        EVENTS[key] = foo

    # add file transfers to EVENTS dict
    cursor.execute("SELECT id, type, partner_handle, partner_dispname, status, starttime, finishtime, filepath, filename, filesize, bytestransferred FROM transfers WHERE convo_id=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'transfer', 'timestamp': row['starttime'], 'finishtime': row['finishtime'], 'transfer_type': row['type'], 'partner': row['partner_handle'], 'status': row['status'], 'filepath': row['filepath'], 'filename': row['filename'], 'filesize': row['filesize'], 'bytestx': row['bytestransferred'], 'id': row['id']}

        key = ( row['starttime'] * 100 )
        while not key in EVENTS:
            key = key + 1
        EVENTS[key] = foo

    # add videos to EVENTS dict
    cursor.execute("SELECT id, dimensions, duration_hqv, duration_vgad2, duration_ltvgad2, timestamp, hq_present, convo_id FROM videos WHERE convo_id=" + str(conv_id) + " ORDER BY id ASC")
    rows = cursor.fetchall()

    for row in rows:
        foo = {'type': 'video', 'timestamp': row['timestamp'], 'dimensions': row['dimensions'], 'duration': (row['duration_hqv'] + row['duration_vgad2'] + row['duration_ltvgad2']), 'id': row['id']}

        key = ( row['timestamp'] * 100 )
        while not key in EVENTS:
            key = key + 1
        EVENTS[key] = foo

    # make HTML body strings
    toc_str = ""
    body_str = ""

    for key in sorted(EVENTS.iterkeys()):
        if EVENTS[key]['type'] == "chat":
            print "foo"
        elif EVENTS[key]['type'] == "call":
            print "foo"
        elif EVENTS[key]['type'] == "message":
            print "foo"
        elif EVENTS[key]['type'] == "transfer":
            print "foo"
        elif EVENTS[key]['type'] == "video":
            print "foo"
        else:
            sys.stderr.write("ERROR: invalid type for key " + str(key) + "\n")
        print "%s: %s" % (key, EVENTS[key]['type'])

    # ok, got all strings, start the output...
    outfile = OUTDIR + conv_identity + ".html"
    FILES.append(outfile)
    fh = open(outfile, "w")
    fh.write("<html><head><title>Skype Conversation with " + conv_identity + "</title></head></html><body>\n")
    fh.write(toc_str)
    fh.write(body_str)
    fh.write("</body></html>")

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

so I want to mainly look at chats and calls, interleaving them, sorted by calls.begin_timestamp and chats.timestamp

 Calls ---> CallMembers

 Chats ---> ChatMembers

                 -----> Messages
 Conversation --|-----> Videos
                 -----> Transfers

EDIT - NEW THEORY - 
Loop through conversations - each conv_id
  Build arrays of calls/callmembers, chats/chatmembers, messages, videos and transfers, ordered by id (which should also be by ts)
  Start a HTML file body for the conversation, and a headers array
    Compare the timestamp of the first iteam in each array (calls, chats, messages, videos, transfers). Print the first one to the body. If it's not a message (i.e. it's a chat, call, video, or transfer) then put in an anchor as well and add it to the headers array.

"""
