<?php
/**
 * updateAPconfigs.php.inc
 * Functions for working with MAC authentication in Ubiquiti Networks AirOS v2 configs.
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

#
# BEGIN CONFIGURATION OF GLOBALS
#

/**
 * @global string $file_path 
 * @name $pubkey
 */
$file_path = "/var/lib/wwwrun/";

/**
 * @global string $pubkey absolute path to ssh public key for auth to the APs
 * @name $pubkey
 */
$pubkey = "/var/lib/wwwrun/.ssh/id_dsa";

/**
 * @global string $APusername the username for logging in to the APs
 * @name $APusername
 */
$APusername = "ubnt";

/**
 * @global bool $AP_DEBUG whether or not to show debugging output for communication with the APs
 * @name $AP_DEBUG
 */
$AP_DEBUG = false;

#
# END CONFIGURATION OF GLOBALS
#

  /**
   * Gets the system.cfg from an AP and saves it as a local file
   *
   * @author jantman
   *
   * @TODO - no error checking here
   *
   * @param $hostname hostname of the AP
   * @param $filePath absolute path to where the local copy should be saved
   *
   * @global string $pubkey
   * @global string $APusername
   * @global bool $AP_DEBUG
   *
   * @return none
   */
function getUbntConfig($hostname, $filePath)
{
    global $pubkey, $APusername, $AP_DEBUG;
    if(file_exists($filePath.".BAK")){ rename($filePath.".BAK", $filePath.".BAK".date("Y-M-D_H-i-s"));}
    if(file_exists($filePath)){ rename($filePath, $filePath.".BAK");}
    $cmd = "scp -i $pubkey $APusername@$hostname:/tmp/system.cfg $filePath";
    if($AP_DEBUG){ echo "Command: ".$cmd."\n";}
    $foo = shell_exec($cmd);
}

  /**
   * Put a local configuration file on the AP, run cfgmtd to load the configuration, then reboot the AP
   *
   * @author jantman
   *
   * @TODO - no error checking here
   *
   * @param $hostname hostname of the AP
   * @param $filePath absolute path to the local config file to upload
   *
   * @global string $pubkey
   * @global string $APusername
   * @global bool $AP_DEBUG
   *
   * @return none
   */
function putUbntConfig($hostname, $filePath)
{
    global $pubkey, $APusername, $AP_DEBUG;
    $cmd = "scp -i $pubkey $filePath $APusername@$hostname:/tmp/system.cfg";
    $foo = shell_exec($cmd);
    $cmd = "ssh -i $pubkey $APusername@$hostname 'cfgmtd -w -p /etc/'";
    $foo = shell_exec($cmd);
    $cmd = "ssh -i $pubkey $APusername@$hostname 'reboot'";
    $foo = shell_exec($cmd);
}

/**
 * Update an existing AP config file to include the specified MAC addresses, write out to a new file.
 *
 * @author jantman
 *
 * @TODO: there's little to no error checking here, even for file permissions or simple stuff like that
 *
 * @param string $oldPath the absolute path to the existing configuration file
 * @param string $newPath the absolute path to where the new config should be written
 * @param array $arr array of MAC addresses to allow, MACs should be all upper case of the form "00:00:00:00:00:00"
 *
 * @return string the full text of the new configuration that was written
 */
function makeNewConfigFile($oldPath, $newPath, $arr)
{
    $fh = fopen($oldPath, "r");
    $pre = "";
    $post = "";
    $inMAC = false;
    while(! feof($fh))
    {
	$line = trim(fgets($fh));
	if($line == ""){ continue;} // skip blank lines
	
	if(substr($line, 0, 18) == "wireless.1.mac_acl")
	{
	    // MAC line, ignore it
	    $inMAC = true;
	}
	elseif($inMAC == false)
	{
	    $pre .= $line."\n";
	}
	else
	{
	    $post .= $line."\n";
	}
    }

    $acl = "";
    $count = 1;
    foreach($arr as $mac)
    {
	$acl .= "wireless.1.mac_acl.$count.mac=".$mac."\n";
	$acl .= "wireless.1.mac_acl.$count.status=enabled\n";
	$count++;
    }
    
    if($count < 32)
    {
	for($i = $count; $i < 33; $i++)
	{
	    $acl .= "wireless.1.mac_acl.$i.mac=\n";
	    $acl .= "wireless.1.mac_acl.$i.status=disabled\n";
	}
    }
	
    $acl .= "wireless.1.mac_acl.policy=allow\n";
    $acl .= "wireless.1.mac_acl.status=enabled\n";


    $out = $pre.$acl.$post;
    
    fclose($fh);
    
    $fh = fopen($newPath, "w");
    fwrite($fh, $out);
    fclose($fh);
    return $out;
}

?>
