#!/usr/bin/perl
#----------------------------------------------------------------------------
# VipToInternalHosts.pl - script to take F5 BigIp VIP address and display
# the members of the pool it is served by. 
#
# By Jason Antman <jason@jasonantman.com> 2012.
#
# The latest version of this script can always be found at:
# $HeadURL$
# This version is: $LastChangedVersion$
#
# The post describing this script and giving updates can be found at:
# <http://blog.jasonantman.com/?p=1129>
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

#use SOAP::Lite + trace => qw(method debug);
use SOAP::Lite;
use Getopt::Long;
use Pod::Usage;

#----------------------------------------------------------------------------
# Disable SSL Cert Validation
#----------------------------------------------------------------------------
$ENV{PERL_LWP_SSL_VERIFY_HOSTNAME}=0;

#----------------------------------------------------------------------------
# Default Values
#----------------------------------------------------------------------------
my $default_port = "80"; # default port number for VIPs

#----------------------------------------------------------------------------
# Validate Arguments
#----------------------------------------------------------------------------
my $sHost;
my $sUID;
my $sPWD;
my $sVIP;
my $sHelp;
my $man;

$result = GetOptions (
    "host=s" => \$sHost,
    "user=s" => \$sUID,
    "pass:s" => \$sPWD,
    "vip=s"  => \$sVIP,
    "man"    => \$man,
    "help"   => \$sHelp, "h" => \$sHelp);

pod2usage(1) if $sHelp;
pod2usage(-exitstatus => 0, -verbose => 2) if $man;

if ( ! $sPWD ) {
    print "Enter password for $sUID\@$sHost: ";
    chomp($sPWD = <>);
    print "\n";
}

# if no port specified, cat on default
if ( $sHost !~ /.+:\d+/ ) {
    $sHost .= ":".$default_port;
}

#----------------------------------------------------------------------------
# Transport Information
#----------------------------------------------------------------------------
sub SOAP::Transport::HTTP::Client::get_basic_credentials
{
    return "$sUID" => "$sPWD";
}


#----------------------------------------------------------------------------
# checkResponse
#----------------------------------------------------------------------------
sub checkResponse()
{
    my ($soapResponse) = (@_);
    if ( $soapResponse->fault )
    {
	print $soapResponse->faultcode, " ", $soapResponse->faultstring, "\n";
	exit();
    }
}

#----------------------------------------------------------------------------
# GetInterface
#----------------------------------------------------------------------------
sub GetInterface()
{
    my ($name) = (@_);
  my $Interface = SOAP::Lite
    -> uri("urn:iControl:$name")
    -> readable(1)
    -> proxy("https://$sHost/iControl/iControlPortal.cgi");
    
  #----------------------------------------------------------------------------
  # Attempt to add auth headers to avoid dual-round trip
  #----------------------------------------------------------------------------
    eval { $Interface->transport->http_request->header
  (
    'Authorization' => 'Basic ' . MIME::Base64::encode("$sUID:$sPWD", '')
  ); };
  
    return $Interface;
}

$Pool = &GetInterface("LocalLB/Pool");
$VirtualServer = &GetInterface("LocalLB/VirtualServer");

#----------------------------------------------------------------------------
# GetHostsFromVip
#----------------------------------------------------------------------------
sub GetHostsFromVip()
{
    my @vips = (@_);
  
    $soapResponse = $VirtualServer->get_list();
    &checkResponse($soapResponse);
    @vs_list = @{$soapResponse->result};
  
    $soapResponse = $VirtualServer->get_destination(
      SOAP::Data->name(virtual_servers => [@vs_list])
      );
    &checkResponse($soapResponse);
    @dest_list = @{$soapResponse->result};
  
    $soapResponse = $VirtualServer->get_default_pool_name(
      SOAP::Data->name(virtual_servers => [@vs_list])
      );
    &checkResponse($soapResponse);
    @pool_list = @{$soapResponse->result};

    my $found = 0;

    foreach $vip (@vips)
    {
	for $i (0 .. $#vs_list)
	{
	    $dest = @dest_list[$i];
	    $addr = $dest->{"address"};
	    $port = $dest->{"port"};
	    next unless ( $vip eq "$addr:$port");
	    $vs = @vs_list[$i];
	    $p2 = @pool_list[$i];
	    print "VIP ${addr}:${port} ($vs) -> Pool '$p2'\n";
	    $found = 1; last;
	}
	last if $found == 1;
    }

    # get the members of the pool
    $soapResponse = $Pool->get_member(
      SOAP::Data->name(pool_names => [$p2])
      );
    &checkResponse($soapResponse);
    @pool_list = @{$soapResponse->result};

    print "Members of Pool '$p2':\n";
    foreach $member (@{@pool_list[0]})
    {
	$addr = $member->{"address"};
	$port = $member->{"port"};
	print "\t$addr:$port\n";
    }

}

#----------------------------------------------------------------------------
# Main logic
#----------------------------------------------------------------------------
&GetHostsFromVip($sVIP);

__END__

=head1 NAME

vipToInternalHosts.pl - F5 Big-Ip VIP address to internal pool member addresses.

=head1 SYNOPSIS

vipToInternalHosts.pl --host=hostname --user=username [--pass=password] --vip=address|ip[:port]

=head1 OPTIONS

=over 8

=item B<--host=hostname>

Specify hostname of the F5 BigIp host. 

=item B<--user=username>

Specify username to use to authenticate to F5 host.

=item B<--pass=password>

Specify password to use to authenticate to F5 host. If omitted, prompt for password to be entered interactively.

=item B<--vip=[address|address:port|hostname|hostname:port]>

VIP address in the form address[:port]. If port is omitted, defaults to 80.

=back

=head1 DESCRIPTION

Take API access credentials for a F5 BigIp load balancer and a VIP address, translate to a pool name and the internal addresses of the pool members.

=head1 SAMPLE OUTPUT

> ./VipToInternalHosts.pl --host=prod-lb1.example.com --user=myname --pass=mypassword --vip=128.6.30.130:80
VIP 128.6.30.130:80 (f5_vip_name) -> Pool 'pool_name'
Members of Pool 'pool_name':
	10.145.15.10:80
	10.145.15.11:80
> 

=cut
