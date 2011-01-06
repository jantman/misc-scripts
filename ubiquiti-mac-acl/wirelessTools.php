<?php
$basedn = "dc=foo,dc=com"; // the top DN for everything
$dbName = "pcr"; // MySQL DB name
$bindDN = "cn=Administrator,dc=foo,dc=com";
$bindPass = "pass";
$userSearchBaseDN = "cn=DesktopUsers,ou=groups,dc=foo,dc=com";
$topdn = "ou=users,dc=foo,dc=com";
$debug = true;
$wireless_dbName = "wireless";

$apHostnames = array("mpac-wap2");
$file_path = "/var/lib/wwwrun/";
$pubkey = "/var/lib/wwwrun/.ssh/id_dsa";
$APusername = "ubnt";
//$AP_DEBUG = true;

?>

<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">

<head>
<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1" />
<title>MPAC - Wireless Help</title>
<link rel="stylesheet" type="text/css" href="docs.css" />
</head>

<body>
<h1>Wireless Help</h1>
<p class="dateline">Updated Wednesday, October 28, 2009</p>

<p class="dateline">Your IP Address is: <?php echo $_SERVER['REMOTE_ADDR'];?></p>

<p class="abstract">This page provides information on the wireless networks available at MPAC, how to connect your devices, and some helpful tools.</p>

<h2>Contents:</h2>
<ol>
<li><a href="#tools">Tools</a></li>
<li><a href="#details">Connection Information</a></li>
<li><a href="#howto">How To Connect</a>
   <ol>
      <li><a href="#winxp">Windows XP</a></li>
      <li><a href="#linux">Linux</a></li>
      <li><a href="#mac">Mac OS X</a></li>
      <li><a href="#iphone">iPhone</a></li>
   </ol>
</li>
</ol>

<hr />

<a name="tools"><h2>Tools</h2></a>

<h3>Check Wireless Access</h3>

<form name="checkAccess" method="POST">
<div><strong>User:</strong>
<input type="hidden" name="action" value="checkAccess" />
<input type="text" name="check_user" id="check_user" size="30" />
<input type="radio" id="user_type" name="user_type" value="username" checked="checked" /> Username
<input type="radio" id="user_type" name="user_type" value="EMTid" /> EMTid
<input type="radio" id="user_type" name="user_type" value="dn" /> User DN
<input type="submit" value="Check Access" />
</div>
</form>

<?php
if(isset($_POST['action']) && $_POST['action'] == "checkAccess")
{
    checkAccess();
}

?>

<h3>Check your allowed MAC addresses</h3>

<form name="checkMAC" method="POST">
<div><strong>Username:</strong>
<input type="hidden" name="action" value="checkMAC" />
<input type="text" name="ldap_username" id="ldap_username" size="30" />
<strong>Password:</strong>
<input type="password" name="ldap_password" id="ldap_password" size="15" />
<input type="submit" value="Check MAC list" />
</div>
</form>

<?php
if(isset($_POST['action']) && $_POST['action'] == "checkMAC")
{
    checkMAC();
}

?>

<h3>Add a MAC address</h3>

<form name="addMAC" method="POST">
<div><strong>Username:</strong>
<input type="hidden" name="action" value="addMAC" />
<input type="text" name="ldap_username" id="ldap_username" size="30" />
<strong>Password:</strong>
<input type="password" name="ldap_password" id="ldap_password" size="15" />
</div>
<div>
<strong>Device Name/Alias:</strong><input type="text" size="15" name="alias" id="alias" />
<strong>MAC:</strong><input type="text" size="18" name="mac" id="mac" /> <em>(xx:xx:xx:xx:xx:xx)</em>
<input type="submit" value="Add MAC" />
</div>
</form>

<?php
if(isset($_POST['action']) && $_POST['action'] == "addMAC")
{
    addMAC();
}

?>

<hr />

<a name="details"><h2>Connection Infomation</h2></a>

<p>MPAC has two separate networks available:</p>
<ul>
<li><strong>MPAC-secure</strong>: This is a secured network using WPA2-Enterprise (WPA2-EAP). Your must be using a device which supports WAP2-EAP/WPA2-Enterprise (exact variant unknown). Some devices will require additional supplicant software. A few devices just don&#39;t support it - including most game consoles. To connect to MPAC-secure, simply authenticate using your normal username and password. If you don't know your username, you can look it up <a href="usernameLookup.php">here</a>.</li>
<li><strong>MPAC</strong>: The MPAC network is secured using the simpler (and less secure) WPA2-PSL security mode. As such, it should only be used for basic web browsing, and should be considered vulnerable to interception or session hijacking. This access point will use either TKIP or AES/CCMP encryption (it chooses the strongest of the two that the client accepts). This network requires a pre-shared key to connect. <strong>The key is</strong> 07432mpacwap2mpac</li>
<li>All access points also have a MAC ACL ("MAC address block list/filter") enabled. Your device&#39;s MAC address must be explicitly allowed (see <a href="#tools">below</a>.
</ul>

<a name="howto"><h2>How To Connect</h2></a>

<a name="winxp"><h3>Windows XP</h3></a>

<a name="linux"><h3>Linux</h3></a>

<a name="mac"><h3>Mac OS X</h3></a>

<a name="iphone"><h3>iPhone</h3></a>

<!-- END h2-level section -->

</body>

</html>


<?php

function checkAccess()
{
    ldapSetup();
    global $ds, $bindDN, $bindPass, $dbName;
    // check_user, user_type={username|EMTid|dn}
    if($_POST['user_type'] == "username" || $_POST['user_type'] == "EMTid")
    {
	if($_POST['user_type'] == "username")
	{
	    $query = "SELECT userDN FROM roster WHERE username='".mysql_real_escape_string($_POST['check_user'])."';";
	}
	else
	{
	    $query = "SELECT userDN FROM roster WHERE EMTid='".mysql_real_escape_string($_POST['check_user'])."';";
	}
	//CONNECT TO THE DB
	$connection = mysql_connect() or die ("unable to connect! (MySQL error: unable to connect).".mysql_error());
	mysql_select_db($dbName) or die ("I'm sorry, but I was unable to select the database $dbName! ".mysql_error());

	$result = mysql_query($query) or die("Error in query: $query.<br /><strong>Error:</strong>".mysql_error());
	if(mysql_num_rows($result) < 1){ echo "<p style=\"color: red;\"><strong>ERROR:</strong> ".$_POST['user_type']." ".$_POST['check_user']." not found.</p>"; return false;}
	$row = mysql_fetch_assoc($result);
	if(trim($row['userDN']) == ""){ echo "<p style=\"color: red;\"><strong>ERROR:</strong> userDN for ".$_POST['user_type']." ".$_POST['check_user']." not found.</p>"; return false;}
	$userDN = $row['userDN'];
    }
    else
    {
	$userDN = $_POST['check_user'];
    }
    $foo = getGroupMembers($ds, "cn=WirelessUsers,ou=groups,dc=midlandparkambulance,dc=com");

    echo '<div class="result">';
    echo '<p><strong>Result:</strong></p>';
    if(in_array($userDN, $foo))
    {
	echo '<p>User has wireless access enabled. <br /><em>(user dn: '.$userDN.')</em></p>';
    }
    else
    {
	echo '<p style="color: red;">Wireless access <strong>not</strong> enabled. Please see the administrator. <br /><em>(user dn: '.$userDN.')</em></p>';
    }
    echo '</div>';
}

function checkMAC()
{
    ldapSetup();
    global $ds, $bindDN, $bindPass, $dbName, $debug, $wireless_dbName;
    if(authWrapper($_POST['ldap_username'], $_POST['ldap_password'], "cn=WirelessUsers,ou=groups,dc=foo,dc=com") != true) { return false; }

    //CONNECT TO THE DB
    $connection = mysql_connect() or die ("unable to connect! (MySQL error: unable to connect).".mysql_error());
    mysql_select_db($wireless_dbName) or die ("I'm sorry, but I was unable to select the database $dbName! ".mysql_error());
    $query = "SELECT * FROM macs WHERE username='".mysql_real_escape_string($_POST['ldap_username'])."';";
    $result = mysql_query($query) or die("Error in query: $query.<br /><strong>Error:</strong>".mysql_error());
    if(mysql_num_rows($result) < 1){ echo "<p class=\"result\"><strong>No registered MAC addresses found for user ".$_POST['ldap_username'].".</strong>.</p>";}
    else
    {
	echo '<div class="result">';
	echo '<p><strong>MACs for user '.$_POST['ldap_username'].': </strong></p>'."\n";
	echo '<ul>'."\n";
	while($row = mysql_fetch_assoc($result))
	{
	    echo '<li>'.$row['mac'];
	    if($row['alias'] != ""){ echo " (".$row['alias'].")";}
	    echo '</li>'."\n";
	}
	echo '</ul>'."\n";
	echo '</div>';
    }
}

function addMAC()
{
    global $ds, $bindDN, $bindPass, $dbName, $debug, $wireless_dbName, $apHostnames, $file_path, $pubkey, $APusername, $AP_DEBUG;
    $ptn = "/^[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}$/";
    if(preg_match($ptn, $_POST['mac']) < 1)
    {
	echo '<p class="error">ERROR: Invalid MAC address format</p>';
	return false;
    }

    ldapSetup();
    if(authWrapper($_POST['ldap_username'], $_POST['ldap_password'], "") != true) { return false; }

    //CONNECT TO THE DB
    $connection = mysql_connect() or die ("unable to connect! (MySQL error: unable to connect).".mysql_error());
    mysql_select_db($wireless_dbName) or die ("I'm sorry, but I was unable to select the database $dbName! ".mysql_error());
    $query = "SELECT * FROM macs;";
    $result = mysql_query($query) or die("Error in query: $query.<br /><strong>Error:</strong>".mysql_error());
    if(mysql_num_rows($result) > 0)
    {
	while($row = mysql_fetch_assoc($result))
	{
	    $foo = strtoupper($row['mac']);
	    $foo = str_replace(":", "", $foo);
	    $foo = str_replace("-", "", $foo);
	    $bar = strtoupper($_POST['mac']);
	    $bar = str_replace(":", "", $bar);
	    $bar = str_replace("-", "", $bar);
	    if($foo == $bar)
	    {
		if($row['username'] == $_POST['ldap_username'])
		{
		    echo '<p class="error">ERROR: MAC address already in allowed list for this user.</p>';
		}
		else
		{
		    echo '<p class="error">ERROR: MAC address already in allowed list for another user.</p>';
		}
		return false;
	    }
	}
    }

    // at this point, we know the user is auth'ed and the MAC is unique and properly formatted
    $MAC = mysql_real_escape_string(strtoupper($_POST['mac']));
    $alias = mysql_real_escape_string($_POST['alias']);

    // get userDN and EMTid
    $query = "SELECT userDN,EMTid FROM roster WHERE username='".mysql_real_escape_string($_POST['ldap_username'])."';";
    mysql_select_db($dbName) or die ("I'm sorry, but I was unable to select the database $dbName! ".mysql_error());
    $result = mysql_query($query) or die("Error in query: $query.<br /><strong>Error:</strong>".mysql_error());
    $row = mysql_fetch_assoc($result);
    $userDN = mysql_real_escape_string($row['userDN']);
    $EMTid = mysql_real_escape_string($row['EMTid']);
    $username = mysql_real_escape_string($_POST['ldap_username']);

    mysql_select_db($wireless_dbName) or die ("I'm sorry, but I was unable to select the database $dbName! ".mysql_error());

    $query = "INSERT INTO macs SET mac='$MAC',EMTid='$EMTid',username='$username',userDN='$userDN',alias='$alias';";
    $result = mysql_query($query);
    if(! $result)
    {
	echo "<p class=\"error\">ERROR: Adding MAC address failed.<br /><br />Error in query: $query.<br /><strong>Error:</strong>".mysql_error()."</p>";
    }
    else
    {
	echo '<div class="result"><p>Successfully added MAC address.</p>';
	echo '<p>Updating AP configurations...</p>';
	require_once('updateAPconfigs.php.inc');
	foreach($apHostnames as $hostname)
	{
	    echo '<pre>';
	    set_time_limit(120);
	    echo "Getting configuration...\n";
	    if($AP_DEBUG){ echo "Getting to: ".$file_path.$hostname.".cfg"."\n";}
	    getUbntConfig($hostname, $file_path.$hostname.".cfg");
	    $arr = getMACarray();
	    set_time_limit(120);
	    echo "Making new config file...\n";
	    if(! file_exists($file_path.$hostname.".cfg")){ echo "\n</pre><p>ERROR: File did not pull from AP.</p></div>"; return false;}
	    $foo = makeNewConfigFile($file_path.$hostname.".cfg", $file_path.$hostname.".cfg.NEW", $arr); // returns content
	    set_time_limit(120);
	    echo "Putting configuration to AP...\n";
	    putUbntConfig($hostname, $file_path.$hostname.".cfg.NEW");
	    echo '</pre>';
	    echo '<p>&nbsp;&nbsp;&nbsp;'.$hostname.' DONE.</p>';
	}
	echo '</div>';
    }
}

// from mpac_ldap_funcs.php.inc in /root/bin/
function getGroupMembers($ds, $groupDN)
{
  $ri = ldap_read($ds, $groupDN, "objectClass=*");
  if(! $ri){ return false;}
  $foo = ldap_get_entries($ds, $ri);
  $foo = $foo[0]['member'];
  if(isset($foo['count'])){ unset($foo['count']);}
  return $foo;
}

function ldapSetup()
{
    global $ds, $bindDN, $bindPass, $dbName;
    // LDAP STUFF
    $ds = ldap_connect();   
    if( !$ds )
    {
        if($debug) { error_log("ldap_auth.php: Error in contacting the LDAP server (debug 1)");}
        return false;
    }
    if (! ldap_set_option($ds, LDAP_OPT_PROTOCOL_VERSION, 3))
    {
        if($debug) { error_log("ldap_auth.php: Failed to set protocol version to 3");}
        return false;
    }

    //Connection made -- bind as manager/admin
    $bind = ldap_bind($ds, $bindDN, $bindPass);

    //Check to make sure we're bound.
    if( !$bind )
    {
        die("Bind as $bindDN failed.\n");
    }
}

function authByLDAP($username, $password, $groupDN)
{
    /*
     / @param username
     / @param password
     / @param groupDN - DN of group to require
     / @param debug - whether to log debug info or not
     /
     / @return 0 on success, 1 on invalid credentials, 2 on group error, 3 on system error
    */

    if($debug) { error_log("ldap_auth.php: Attempting LDAP Auth username=".$username);}

    global $topdn, $debug;

    $ds = ldap_connect();
    
    if( !$ds )
    {
        if($debug) { error_log("ldap_auth.php: Error in contacting the LDAP server (debug 1)");}
	return 3;
    }

    if (! ldap_set_option($ds, LDAP_OPT_PROTOCOL_VERSION, 3))
    {
	if($debug) { error_log("ldap_auth.php: Failed to set protocol version to 3");}
	return 3;
    }
    
    //Connection made -- bind anonymously and get dn for username.
    $bind = @ldap_bind($ds);
    
    //Check to make sure we're bound.
    if( !$bind )
    {
        if($debug) { error_log("ldap_auth.php: Anonymous bind to LDAP FAILED.  Contact Tech Services! (Debug 2)");}
	return 3;
    }
    
    $search = ldap_search($ds, $topdn, "uid=$username"); // do the search
    
    //Make sure only ONE result was returned -- if not, they might've thrown a * into the username.  Bad user!
    if( ldap_count_entries($ds,$search) != 1 )
    {
        if($debug) { error_log("ldap_auth.php: Error processing username -- please try to login again. (Debug 3) - more than one entry returned.");}
	return 3;
    }
    
    $info = ldap_get_entries($ds, $search);
    
    $userdn = $info[0]['dn'];
    if($debug) { error_log("ldap_auth.php: GOT dn for user: ".$userdn);}

    //Now, try to rebind with their full dn and password.
    $bind = @ldap_bind($ds, $info[0]['dn'], $password);
    if( !$bind || !isset($bind))
    {
	if($debug) { error_log("ldap_auth.php: AUTH failed: ".ldap_error($ds)." (".ldap_errno($ds).")");}
	return 1;
    }
    
    //Now verify the previous search using their credentials.
    $search = ldap_search($ds, $topdn, "uid=$username");
        
    $info = ldap_get_entries($ds, $search);
    if( $username == $info[0]['uid'][0] )
    {
        if($debug) { error_log("ldap_auth.php: AUTH OK"); }
        $fullname = $info[0][cn][0];
    }
    else
    {
	if($debug) { error_log("ldap_auth.php: AUTH failed: ".ldap_error($ds)." (".ldap_errno($ds).")"); }
	return 1;
    }

	//$search = ldap_search($ds, $groupDN, $userdn);
	//$info = ldap_get_entries($ds, $search);

    if($groupDN != "")
    {
	$r = ldap_compare($ds,$groupDN,'member', $userdn);

	if ($r === -1)
	{
	    $err = ldap_error($ds);
	    $eno = ldap_errno($ds);
	    ldap_close($ds);

	    if ($eno === 32)
	    {
		if($debug) { error_log("ldap_auth.php: Access Denied - Group Does Not Exist."); }
	    }
	    elseif ($eno === 16)
	    {
		if($debug) { error_log("ldap_auth.php: Access Denied - Mambership Attribute Does Not Exist."); }
	    }
	    else
	    {
		if($debug) { error_log("ldap_auth.php: LDAP Error: ".$err."Access Denied."); }
	    }
	    return 2;
	}
	elseif ($r === false)
	{
	    ldap_close($ds);
	    if($debug) { error_log("ldap_auth.php: Access Denied. No Group Membership."); }
	    return 2;
	}
	elseif ($r === true)
	{
	    if($debug) { error_log("ldap_auth.php: GROUP OK. Authenticated."); }
	    $_SESSION['username'] = $username;
	    $_SESSION['fullname'] = $fullname;
	    return 0; // both user and group ok
	}
    }
    else
    {
	if($debug) { error_log("ldap_auth.php: GROUP OK. Authenticated."); }
	$_SESSION['username'] = $username;
	$_SESSION['fullname'] = $fullname;
	return 0; // both user and group ok
    }
    return false;
}

function authWrapper($username, $pass, $groupDN)
{
    $foo = authByLDAP($username, $pass, $groupDN);
    if($foo == 0)
    {
	// do nothing, auth OK
	return true;
    }
    elseif($foo == 1)
    {
	echo '<p style="color: red;"><strong>ERROR:</strong> Invalid username or password.</p>';
    }
    elseif($foo == 2)
    {
	echo '<p style="color: red;"><strong>ERROR:</strong> User is not a member of the required group.</p>';
    }
    else
    {
	echo '<p style="color: red;"><strong>ERROR:</strong>Unknown error occurred in LDAP lookup.</p>';
    }
    return false;
}

?>