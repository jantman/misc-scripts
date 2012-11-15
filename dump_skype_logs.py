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

OUTDIR = "skypeout"
FILE = "main.db"

for opt, arg in options:
    if opt in ('-o', '--outdir'):
        OUTDIR = arg
    elif opt in ('-v', '--verbose'):
        verbose = True
    elif opt in ('-f', '--file'):
        FILE = arg

# TODO: test that FILE exists
# TOOD: test that OUTDIR exists, else create

conn = sqlite3.connect(FILE)
if conn == None:
    print "ERROR: could not connect to database file '" + FILE + "'."
    sys.exit(1)

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

conn.row_factory = sqlite3.Row
cursor = conn.cursor()
c2 = conn.cursor()

EVENTS = {}
CALLS = {}

# add chats to EVENTS dict
cursor.execute("SELECT id, name, timestamp, dialog_partner, adder, participants FROM chats ORDER BY id ASC")
rows = cursor.fetchall()

for row in rows:
    foo = {'type': 'chat', 'timestamp': row['timestamp'], 'partner': row['dialog_partner'], 'id': row['id']}
    if row['timestamp'] in EVENTS:
        print "WARNING: timestamp " + str(row['timestamp']) + " for chat "+ str(row['id']) +" already in EVENTS dict."
    EVENTS[row['timestamp']] = foo

# add calls to EVENTS dict
cursor.execute("SELECT id, begin_timestamp, host_identity, duration, name, is_incoming, conv_dbid, current_video_audience FROM calls ORDER BY id ASC")
rows = cursor.fetchall()

for row in rows:
    foo = {'type': 'call', 'timestamp': row['begin_timestamp'], 'host': row['host_identity'], 'duration': row['duration'], 'is_incoming': row['is_incoming'], 'conv_dbid': row['conv_dbid'], 'current_video_audience': row['current_video_audience'], 'id': row['id']}

    # get data from callmembers
    c2.execute("SELECT id,identity,dispname,call_duration,videostatus,guid,start_timestamp,call_db_id

    if row['begin_timestamp'] in EVENTS:
        print "WARNING: timestamp " + str(row['begin_timestamp']) + " for call "+ str(row['id']) +" already in EVENTS dict."
    EVENTS[row['begin_timestamp']] = foo
    CALLS[row['begin_timestamp']] = foo

conn.close()

for key in sorted(EVENTS.iterkeys()):
    print "%s: %s" % (key, EVENTS[key]['type'])

#print EVENTS
