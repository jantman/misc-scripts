/**
 * README.txt for updateAPconfigs.php.inc
 *
 * Copyright 2010, 2011 Jason Antman, All Rights Reserved.
 *
 * These functions may be used for any purpose provided that:
 * 1) This copyright notice is kept intact.
 * 2) You send back to me any changes/modifications/bugfixes that you make.
 * 3) This may not be included in commercial software which is sold for a fee, unless you discuss this with me first.
 *
 * @author Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
 *
 * Announcement post: <http://blog.jasonantman.com/2011/01/managing-ubiquiti-networks-mac-acls-from-a-script/>
 *
 * The canonical current version of this script lives at:
 * $HeadURL$
 * $LastChangedRevision$
 */

updateAPconfigs.php.inc is a set of PHP functions for manipulating the MAC ACL
on Ubiquiti AirOSv2 APs, specifically for programmatically changing the MAC
list, and managing the full range of 32 possible MAC addresses.

This is by no means a complete system. I've included some example code
(wirelessTools.php) from my setup, which is a self-service PHP page for my
users, allowing them to maintain a list of their MAC addresses, and have new
additions pushed out to the APs.

For my purpose (an organization's private WLAN), I store the list of MACs in a
MySQL table (schema in 'wireless.sql'), where each user has a username, an ID
number, an LDAP DN, and MAC addresses, each of which has an alias that is just
used for display purposes (i.e. Laptop, iPhone, etc.). The tool is pretty
specific to my client, since auth is handled via LDAP and MACs are stored in
MySQL. But I'm including the code as a starting point for you.

========WARNINGS=======
1) There's little to no error checking in these functions. As you can see, I
do most of the checking that files exist, are writable, etc. in the
wirelessTools.php script. You should be WARNED that just calling the functions
could push out an empty or bad config to your APs. I have no idea what that
would do, but since I'm directly running `cfgmtd`, I assume it would be bad.

2) The APs must reboot to reload the configuration. For my purpose, all of the
people with access to the self-serve page are "trusted" users. Be careful here
- when a user adds a MAC address, the AP will reload config and then
restart. It would be bad to let someone just sit there clicking the button...

=====USAGE====
Be sure to change the global variables at the top of updateAPconfigs.php.inc
to suit your environment. You must already have pubkey-based SSH
authentication setup on the APs, this script uses SSH and SCP with pubkey
auth.

Functions Provided:
getUbntConfig($hostname, $filePath)
   Copies (scp) the config from AP ($hostname) to $filePath on the local machine
putUbntConfig($hostname, $filePath)
   Copies (scp) the config from $filePath on the local machine to AP ($hostname)
   then runs (ssh) `cfgmtd` to persist the configuration and then reboots the AP
makeNewConfigFile($oldPath, $newPath, $arr)
   reads an existing configuration file ($oldPath), changes the MAC ACL to
   include an array of MAC addresses ($arr), writes new config to $newPath
