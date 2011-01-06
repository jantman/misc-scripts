<?php
/**
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
 *
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

function getMACarray()
{
    global $wireless_dbName;
    $connection = mysql_connect() or die ("unable to connect! (MySQL error: unable to connect).".mysql_error());
    mysql_select_db($wireless_dbName) or die ("I'm sorry, but I was unable to select the database $dbName! ".mysql_error());
    $query = "SELECT * FROM macs;";
    $result = mysql_query($query) or die("Error in query: $query.<br /><strong>Error:</strong>".mysql_error());
    $arr = array();
    while($row = mysql_fetch_assoc($result))
    {
	$arr[] = $row['mac'];
    }
    return $arr;
}

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
