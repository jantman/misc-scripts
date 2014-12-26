#!/usr/bin/php
<?php
/**
 * script to restart rsyslog if it appears to have stopped logging
 * should be run via cron every minute
 * also collects information about system state and mails it to addresses
 *
 * Copyright 2011 Jason Antman <jantman@oit.rutgers.edu> <jason@jasonantman.com>,
 *  on behalf of the taxpayers of the State of New Jersey and/or the students of Rutgers University,
 *  The State University of New Jersey.
 *
 * The latest version of this script can be found at:
 * <https://github.com/jantman/misc-scripts/blob/master/kickRsyslog.php>
 *
 */

require_once('collectRsyslogInfo.php');

$mail_to = array('jantman@oit.rutgers.edu');

if(! file_exists(PID_FILE))
{
    $host = trim(shell_exec("hostname"));
    $subj = "RSYSLOG ERROR - Not running on $host";

    $body = "ERROR - '".PID_FILE."' does not exist on host '$host'.\n\nSomeone should start rsyslogd, unless it is supposed to be stopped.\n\n";
    $body .= "mail sent by ".__FILE__." on $host\n";

    foreach($mail_to as $addr)
    {
	mail($addr, $subj, $body);
    }

    openlog("kickRsyslog.php", LOG_NDELAY | LOG_PERROR | LOG_PID, LOG_DAEMON);
    syslog(LOG_EMERG, __FILE__." thinks rsyslog has died. If you actually see this log message in a file, the script is broken (rsyslog is actually running).");
    closelog();

    exit(1);
}

$mtime = filemtime(AGE_CHECK_FILE);
$age = time() - $mtime;
if($age >= THRESHOLD_SEC)
{
  $body = collectRsyslogInfo(true, true);

  $cmd = "/sbin/service rsyslog restart";
  $host = trim(shell_exec("hostname"));
  $start = microtime(true);
  exec($cmd);
  $foo = microtime(true) - $start;

  $body .= "\nIssuing command '$cmd' as root.... ";
  $body .= "Command ran in ".round($foo, 3)." seconds<br />";

  $headers = "Content-type: text/html\r\n";
  foreach($mail_to as $addr)
    {
      mail($addr, $subj, $body, $headers);
    }

  openlog("kickRsyslog.php", LOG_NDELAY | LOG_PERROR | LOG_PID, LOG_DAEMON);
  syslog(LOG_EMERG, __FILE__." thinks rsyslog is hanging. If you actually see this log message in a file, the script is broken (rsyslog is actually running).");
  closelog();
  exit(1);
}

fwrite(STDERR, __FILE__." - rsyslog appears to be running normally.\n");

?>
