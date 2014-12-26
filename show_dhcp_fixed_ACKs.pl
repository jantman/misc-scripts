#!/usr/bin/perl
#
# show_dhcp_fixed_ACKs.pl - script to show the most recent DHCP ACKs per IP address for ISC DHCPd,
#   from a log file. Originally written for Vyatta routers that just show the dynamic leases.
#
# To use this, you need to have dhcpd logging to syslog, and your syslog server putting the log file at
# /var/log/user/dhcpd (or a file path specified by the $logfile variable below.
#
# To accomplish this on Vyatta 6.3, run:
# set service dhcp-server global-parameters "log-facility local2;"
# set system syslog file dhcpd facility local2 level debug
# set system syslog file dhcpd archive files 5
# set system syslog file dhcpd archive size 3000
# commit
#
# Copyright 2011 Jason Antman <jason@jasonantman.com> All Rights Reserved.
# This script is free for use by anyone anywhere, provided that you comply with the following terms:
# 1) Keep this notice and copyright statement intact.
# 2) Send any substantial changes, improvements or bog fixes back to me at the above address.
# 3) If you include this in a product or redistribute it, you notify me, and include my name in the credits or changelog.
#
# The following URL always points to the newest version of this script. If you obtained it from another source, you should
# check here:
# <https://github.com/jantman/misc-scripts/blob/master/show_dhcp_fixed_ACKs.pl>
#
# CHANGELOG:
# 2011-12-24 jason@jasonantman.com:
#    initial version of script
#
#

use strict;
use warnings;

my $logfile = "/var/log/user/dhcpd";

my %data = ();

open DF, $logfile or die $!;
while ( my $line = <DF> ) {
    if ( $line !~ m/dhcpd: DHCPACK/) { next;}
    $line =~ m/([A-Za-z]+ [0-9]+ [0-9]{1,2}:[0-9]{2}:[0-9]{2}) [^\/x]+ dhcpd: DHCPACK on (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}) to ((?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}) via (.+)/;
    #print "$1==$2==$3==$4==\n" ;
    $data{"$2"}->{'mac'} = "$3";
    $data{"$2"}->{'date'} = "$1";
    $data{"$2"}->{'if'} = "$4";
    $data{"$2"}->{'ip'} = "$2";    
}

printf("%-18s %-20s %-18s %-10s\n", "IP Address", "Hardware Address", "Date", "Interface");
printf("%-18s %-20s %-18s %-10s\n", "----------", "----------------", "----", "---------");

# begin sort by IP address
my @keys =
  map  substr($_, 4) =>
  sort
  map  pack('C4' =>
    /(\d+)\.(\d+)\.(\d+)\.(\d+)/)
    . $_ => (keys %data);
# end sort by IP address

foreach my $key (@keys) {
    printf("%-18s %-20s %-18s %-10s\n", $data{$key}{'ip'}, $data{$key}{'mac'}, $data{$key}{'date'}, $data{$key}{'if'});
}
