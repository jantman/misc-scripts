#!/usr/bin/php
<?php
/**
 * script to investigate rsyslog hangs, write output, and send mail
 *
 * Copyright 2011 Jason Antman <jantman@oit.rutgers.edu> <jason@jasonantman.com>,
 *  on behalf of the taxpayers of the State of New Jersey and/or the students of Rutgers University,
 *  The State University of New Jersey.
 *
 * $HeadURL$
 * $LastChangedRevision$
 *
 */

$mailTo = array('jantman@oit.rutgers.edu');

require_once('collectRsyslogInfo.php');

$out = collectRsyslogInfo(true, true);

$headers = "Content-type: text/html\r\n";

$host = trim(shell_exec("hostname"));

foreach($mailTo as $addr)
{
  mail($addr, "collectRsyslogInfo.php output on $host at ".date("Y-m-d H:i:s"), $out, $headers);
}

echo $out;


?>
