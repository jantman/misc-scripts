#!/usr/bin/perl

#
# Perl script to de/encode F5 BigIp persistence cookies.
#
# The latest version of this script can always be obtained from:
#   <http://svn.jasonantman.com/misc-scripts/bigipcookie.pl> via HTTP ot SVN
#
# Update information and description can be found at:
#   <http://blog.jasonantman.com/?p=931>
#
# Copyright 2012 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>.
#
#########################################################################################
#
# LICENSE: AGPLv3 <http://www.gnu.org/licenses/agpl-3.0.html>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# If you make any modifications/fixes/feature additions, it would be greatly appreciated
# if you send them back to me at the above email address.
#
#########################################################################################
#
# CREDITS:
# - F5 itself for the formula: <http://support.f5.com/kb/en-us/solutions/public/6000/900/sol6917.html>
# - Tyler Krpata <http://www.tylerkrpata.com/2009/06/decode-f5-bigip-cookie-in-one-line-of.html>
#     for the Perl one-liner that this logic is based on.
#
# $HeadURL$
# $LastChangedRevision$
#
# Changelog:
#
# 2012-02-02 Jason Antman <jason@jasonantman.com>:
#   - initial version
#

use strict;
use warnings;

if ( $#ARGV < 0 ) {
    print "USAGE: bigipcookie.pl <IP:port | cookie value>\n";
    exit 1;
}

if ($ARGV[0] =~ m/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3}):(\d+)$/) {
    my $ipEnc = $1 + ($2*256) + ($3 * (256**2)) + ($4 * (256**3));
    my $portEnc = hex(join "", reverse ((sprintf "%04x", $5) =~ /../g));
    print "$ipEnc.$portEnc.0000\n";
}
elsif ($ARGV[0] =~ m/^(\d+)\.(\d+)\.0000$/){
    # decode a cookie value
    my $ipEnc = $1;
    my $portEnc = $2;
    my $ip = join ".", map {hex} reverse ((sprintf "%08x", split /\./, $ipEnc) =~ /../g);
    my $portDec = hex(join "", reverse ((sprintf "%04x", $portEnc) =~ /../g));
    print "$ip:$portDec\n";
}
else {
    print "USAGE: bigipcookie.pl <IP:port | cookie value>\n";
    exit 1;
}

