#!/usr/bin/perl

# nagios_log_problem_interval.pl - Chart intervals between problem and recovery from Nagios/Icinga logs
# 
# By Jason Antman <jason@jasonantman.com> 2012.
#
# The latest version of this script can always be found at:
# $HeadURL$
# This version is: $LastChangedRevision$
#
# The post describing this script and giving updates can be found at:
# <http://blog.jasonantman.com/?p=1169>
#
#----------------------------------------------------------------------------
# This script was based off of one found in the F5 Networks iControl Wiki.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Alternatively, the contents of this file may be used under the terms
# of the GNU General Public License (the "GPL"), in which case the
# provisions of GPL are applicable instead of those above.  If you wish
# to allow use of your version of this file only under the terms of the
# GPL and not to allow others to use your version of this file under the
# License, indicate your decision by deleting the provisions above and
# replace them with the notice and other provisions required by the GPL.
# If you do not delete the provisions above, a recipient may use your
# version of this file under either the License or the GPL.
#----------------------------------------------------------------------------
#

use strict;
use warnings;
use Getopt::Long;
use Pod::Usage;
use File::Basename;
use Data::Dumper;

sub find_X_newest_files;
sub parse_log_line;
sub graph_simple_ascii;
sub graph_simple_ascii_line;

# variables to hold state
my $newestLine = 0;
my $oldestLine = 2**31;
my $h = ();
my $temp;
# end variables to hold state

# get options - include archivepath and backtrack number, as well as regex to match
my ($archpath, $sHelp, $backtrack, $regex, $sMan, $result);
$result = GetOptions (
    "archivedir=s" => \$archpath,
    "backtrack:i" => \$backtrack,
    "match=s" => \$regex,
    "man"    => \$sMan,
    "help"   => \$sHelp, "h" => \$sHelp);

pod2usage(1) if $sHelp;
pod2usage(-exitstatus => 0, -verbose => 2) if $sMan;

pod2usage("$0: match regex must be specified.\n") unless $regex;
pod2usage("$0: Archive directory must be specified.\n") unless $archpath;

$backtrack = 30 unless $backtrack;

# find the $backtrack newest files in $archpath
my @files = find_X_newest_files($archpath, $backtrack);

# iterate those log files in order from oldest to most recent
foreach my $fname (@files) {
    # read the file, line by line
    open (FH, "$archpath/$fname") || die "Could not open file $archpath/$fname for reading. \n";
    # note the oldest date present (head -1 of oldest archive)
    foreach my $line (<FH>) {
	chomp $line;
	$temp = parse_log_line($line, $regex);
	next unless exists $temp->{'time'};
	#print "$line\n";
	#print "time=".$temp->{'time'}." type=".$temp->{'type'}."\n";
	if ($temp->{'type'} eq 'OK' && exists $h->{$temp->{'service'}} && $h->{$temp->{'service'}}->{'state'} eq 'PROBLEM') {
	    # if it's a recovery and we have a hash, and the state is problem, take the time of the recovery minus the hash time, increment that interval counter, set state to ok and time to 0
	    my $foo = int(($temp->{'time'} - $h->{$temp->{'service'}}->{'time'})/60);
	    $h->{$temp->{'service'}}->{$foo}++;

	    $h->{$temp->{'service'}}->{'state'} = 'OK';
	    $h->{$temp->{'service'}}->{'time'} = 0;
	}
	elsif ($temp->{'type'} eq 'CRIT') {
	    # if it's a problem, add element to hash if we don't have it, set state to problem and time to time in line
	    $h->{$temp->{'service'}}->{'time'} = $temp->{'time'};
	    $h->{$temp->{'service'}}->{'state'} = 'PROBLEM';
	}
    }
}

foreach my $svc (keys $h) {
    print $svc."\n";
    delete($h->{$svc}->{'time'}); delete($h->{$svc}->{'state'});
    graph_simple_ascii($h->{$svc});
    print "\n\n";
}

sub graph_simple_ascii() {
    my ($hash) = @_;

    my ($c15_30, $c30_60, $c61) = (0, 0, 0);

    print "        Count\n";
    for my $i (1..15) {
	if ( exists $hash->{$i} ){ 
	    graph_simple_ascii_line($i, $hash->{$i}, 80);
	}
	else {
	    graph_simple_ascii_line($i, 0, 80);
	}
    }

    foreach my $i (keys $hash) {
	$c15_30 += $hash->{$i} if $i >= 16 && $i < 30;
	$c30_60 += $hash->{$i} if $i >= 30 && $i < 60;
	$c61 += $hash->{$i} if $i >= 60;
    }

    graph_simple_ascii_line("16-29", $c15_30, 80);
    graph_simple_ascii_line("30-59", $c30_60, 80);
    graph_simple_ascii_line("60+", $c61, 80);

}

sub graph_simple_ascii_line() {
    my ($title, $num, $width) = @_;
    
    my $barWidth = $width - (7 + 6);
    my $x = $num;
    $x = $barWidth if $num > $barWidth;

    print sprintf("%6s", $title).":"; # width of 7
    print ("#" x $num);
    print "(".$num.")"; # width of 6
    print "\n";
}

sub find_X_newest_files() {
    my($path, $num) = @_;
    my @files = ();
    my $count = 0;

    foreach my $line (`ls -1t $path/*.log`) {
	chomp $line;
	push(@files, basename($line));
	$count++;
	last if $count >= $backtrack;
    }
    return @files;
}

sub parse_log_line() {
    my($line, $match) = @_;

    my $ret;
    if ($line =~ /\[(\d+)\] SERVICE ALERT: (.*$match.*);CRITICAL;HARD/) {
	$ret->{'time'} = $1;
	$ret->{'service'} = $2;
	$ret->{'type'} = 'CRIT';
	return $ret;
    }
    if ($line =~ /\[(\d+)\] SERVICE ALERT: (.*$match.*);OK;/) {
	$ret->{'time'} = $1;
	$ret->{'service'} = $2;
	$ret->{'type'} = 'OK';
	return $ret;
    }
    return $ret;
}

__END__

=head1 NAME

nagios_log_problem_duration.pl - Post-process Nagios/Icinga logs and show duration of downtimes/problems

=head1 SYNOPSIS

nagios_log_problem_duration.pl --archivedir=<path> [--backtrack=number] --match=<regex>

=head1 OPTIONS

=over 8

=item B<--archivedir=path>

Path to directory with Nagios archive files

=item B<--match=regex>

Regex to match in the hostname/service description. Cannot include parentheses. 

=item B<--backtrack=number>

Specify the number of archive logs to backtrack (default: 30).

=back

=head1 DESCRIPTION

Script to post-process Nagios/Icinga archived logs, determine the period of time between problems and recoveries.
Useful to identify hosts/services that often alert and then recover quickly.

Still needs scaling for hosts/services with >= 60 events in the selected time period.

Minutes from HARD CRITICAL to Recovery are on the Y axis, count on the X axis

=head1 SAMPLE OUTPUT

> nagios_log_problem_interval.pl --archivedir=/var/icinga/archive --match=myhost --backtrack=10
myhost;HTTP
        Count
     1:########(8)
     2:##(2)
     3:#(1)
     4:##(2)
     5:#######(7)
     6:(0)
     7:(0)
     8:#(1)
     9:(0)
    10:(0)
    11:#(1)
    12:(0)
    13:#(1)
    14:(0)
    15:(0)
 16-29:(0)
 30-59:(0)
   60+:(0)

=cut
