#!/usr/bin/php
<?php
   /**
    ****************************************************************************************************
    * Script to collect information on a crashed/hung rsyslogd process, and log it all somewhere.
    *
    * Copyright 2011 Jason Antman <jantman@oit.rutgers.edu> <jason@jasonantman.com>,
    *  on behalf of the taxpayers of the State of New Jersey and/or the students of Rutgers University,
    *  The State University of New Jersey.
    *
    * $HeadURL$
    * $LastChangedRevision$
    *
    ****************************************************************************************************
    * Usage:
    * This script defines one function, collectRsyslogInfo(), that collects various information on
    * the rsyslog process, and either outputs it to the filesystem, or returns it as a string (optionally
    * formatted as simple HTML for email). 
    *
    * This function should be called from a PHP wrapper. We have two, used in the following ways:
    * 1) investigateRsyslog.php, just runs this and saves the information. 
    * 2) kickRsyslog.php runs via cron; if log files are >= X seconds old, it saves the information, sends mail,
    *     and restarts rsyslog.
    *
    * CUSTOMIZATION:
    * 1) be sure to look at everything between the "CONFIGURATION" comments.
    * 2) Everything between "RUTGERS" comments is site-specific, and you should probably remove.
    *
    * WARNING: Be aware there's very little error checking in this script. Things like paths existing or being
    *  writable are not checked. There's also very little checking of binary paths, so you should confirm that
    *  everything works right before relying on this.
    *
    * DEPENDENCIES: timeout command or script (PATH_TIMEOUT). See example in svn.jasonantman.com/misc-scripts/
    ****************************************************************************************************
    */

// CONFIGURATION
define("AGE_CHECK_FILE", "/ramdisk/dhcpd.log"); // logfile whose age triggers rsyslog restart
define("THRESHOLD_SEC", 120); // if file above is older than this many seconds, collect info, send mail, restart
define("PID_FILE", "/var/run/syslogd.pid"); // rsyslogd PID file location
define("SAVE_LOC", "/root/rsyslog-investigate/"); // where to save our output if $save is true. Directory should exist. Will create sub-directories for each run like 'SAVE_LOC/rsyslogd_collect_Y-m-d_H-i-s/'
define("PATH_TIMEOUT", "/root/bin/timeout"); // path to script that handles command timeout, <path_timeout> <timeout_sec> <command>
define("STRACE_RUNTIME", 20); // how many seconds to run strace for
// END CONFIGURATION

define("TEXT_SEP", "\n================================================\n");
define("HTML_SEP", "\n<br /><hr />\n");

/**
 * Collect information on a possibly hung/crashed rsyslogd process.
 *
 * @param $save if true, save output of commands as individual files in SAVE_LOC/rsyslogd_collect_Y-m-d_H-i-s/ (default true)
 * @param $html if true, return simply formatted HTML instead of raw text.
 *
 * GLOBALS: if "DEBUG" evaluates to true, prints a bunch of debugging info to STDERR.
 *
 * @return string all of the collected information
 */
function collectRsyslogInfo($save = true, $html = false)
{
  global $DEBUG;

  $out = ""; // string to hold our return output

  $start_time = time();
  if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."entering function"."\n");}

  if($save)
    {
      // create our save directory
      if(! is_dir(SAVE_LOC)){ mkdir(SAVE_LOC);}
      $SAVE_DIR = SAVE_LOC."rsyslogd_collect_".date("Y-m-d_H-i-s", $start_time)."/";
      if(! is_dir($SAVE_DIR)){ mkdir($SAVE_DIR);}
      if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."set SAVE_DIR as $SAVE_DIR"."\n");}
    }

  if($html){ $SEP = HTML_SEP;} else { $SEP = TEXT_SEP;}

  $host = trim(shell_exec("hostname"));

  if(! file_exists(PID_FILE)){ return "ERROR: PID file (".PID_FILE.") does not exist. Bailing out...";}
  $PID = (int)trim(file_get_contents(PID_FILE));

  if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."PID=$PID"."\n");}

  $out .= "collectRsyslogInfo() running at ".date("Y-m-d H:i:s", $start_time)." on $host from ".__FILE__.". found rsyslogd PID as $PID.".$SEP;

  $out .= jantman_run_command("kill -USR2 $PID", $save, $html, $SAVE_DIR);

  // RUTGERS-specific
  $mtime = filemtime(AGE_CHECK_FILE);
  $age = $start_time - $mtime;
  $out .= "age of ".AGE_CHECK_FILE." on '$host' is $age seconds, at ".date("Y-m-d H:i:s").$SEP;
  // END RUTGERS-specific

  $out .= PID_FILE." mtime: ".date("Y-m-d H:i:s", filemtime(PID_FILE))." (age: ".(time() - filemtime(PID_FILE))." seconds)";

  $out .= jantman_command_get_output("tail -5 ".AGE_CHECK_FILE, $save, $html, $SAVE_DIR);
  $out .= jantman_command_get_output("grep \"rsyslogd:\" /var/log/rsyslog-stats | grep \"start\$\" | tail -4", $save, $html, $SAVE_DIR);
  $out .= jantman_command_get_output("tail -12 /var/log/rsyslog-stats", $save, $html, $SAVE_DIR);
  $out .= jantman_command_get_output("tail -10 /var/log/puppetlog", $save, $html, $SAVE_DIR);
  $out .= jantman_command_get_output("top -d 1 -n 4 -b", $save, $html, $SAVE_DIR);
  $out .= jantman_command_get_output("ps aux", $save, $html, $SAVE_DIR);
  $out .= jantman_command_get_output(PATH_TIMEOUT." 20 lsof -p $PID", $save, $html, $SAVE_DIR);
  $out .= jantman_command_get_output(PATH_TIMEOUT." ".STRACE_RUNTIME." /usr/bin/strace -f -tt -p $PID", $save, $html, $SAVE_DIR);

  if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."DONE."."\n");}
  $out .= $SEP;
  $out .= "generated on $host at ".date("Y-m-d H:i:s")." by ".__FILE__;
  return $out;
}

/**
 * Run a command with shell_exec and return a string listing the command and how long it took to run,
 *  formatted as either plain text or html.
 *
 * GLOBALS: if "DEBUG" evaluates to true, prints a bunch of debugging info to STDERR.
 *
 * @param string $cmd full command to run
 * @return float time taken to run, in seconds
 */
function jantman_run_command($cmd, $save, $html, $SAVE_DIR)
{
  global $DEBUG;

  if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."called with cmd='$cmd'"."\n");}

  $start = microtime(true);
  shell_exec($cmd);
  $end = microtime(true);

  if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."command finished, runtime=".round($end - $start, 3)." start=$start end=$end"."\n");}

  return 'Running Command "<tt>'.$cmd.'</tt>"... completed in '.round($end - $start, 3).' seconds.'.($html ? HTML_SEP : TEXT_SEP);
}

/**
 * Run a command, save the output to filesystem, return formatted output string.
 *
 * GLOBALS: if "DEBUG" evaluates to true, prints a bunch of debugging info to STDERR.
 *
 * @param string $cmd the command to run.
 *
 * @return string the output, along with some formatting.
 */
function jantman_command_get_output($cmd, $save, $html, $SAVE_DIR)
{
  global $DEBUG;

  if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."called with cmd='$cmd', save=".($save ? 'true' : 'false')." html=".($html ? 'true' : 'false')."\n");}

  $fname = $SAVE_DIR.jantman_make_command_file_name($cmd);
  if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."output fname='$fname'"."\n");}

  if($save)
    {
      if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."save is true, writing output"."\n");}
      if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."running command as: ".$cmd." 2>&1 > ".$fname."\n");}
      $start_time = microtime(true);
      shell_exec($cmd." > ".$fname." 2>&1");
      $end_time = microtime(true);
      if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."command finished, runtime was ".round($end_time - $start_time, 3)."\n");}
      $output = file_get_contents($fname);
    }
  else
    {
      if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."running command..."."\n");}
      $start_time = microtime(true);
      $output = shell_exec($cmd." 2>&1");
      $end_time = microtime(true);
      if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."command finished, runtime was ".round($end_time - $start_time, 3)."\n");}
    }

  $out = ($html ? HTML_SEP : TEXT_SEP);
  $out .= "Running command ".($html ? '<tt>' : "'").$cmd.($html ? '</tt>' : "'")."...".($html ? '<br />' : "\n");
  $out .= "Command ran in ".round($end_time - $start_time, 3)." seconds".($save ? ", output written to $fname." : ".").($html ? '<br />' : "\n");
  $out .= "Output of command:".($html ? '<br />' : "\n");
  if($html){ $out .= '<pre>'."\n".str_replace(">", "&gt;", str_replace("<", "&lt;", $output))."\n</pre>";} else { $out .= $output."\n";}

  if($DEBUG){ fwrite(STDERR, date("H:i:s.u")." ".__FUNCTION__."\t"."returning from function..."."\n");}
  return $out;
}

/**
 * Turn a command line into a usable file name to store the output.
 * A bit of a hack, but should work for us.
 *
 * @param string $cmd the command line
 * @return string command line with all characters not a-zA-Z0-9_- replaced with a single _
 */
function jantman_make_command_file_name($cmd)
{
  $new = preg_replace("/[^a-zA-Z0-9_-]/", "_", trim($cmd));
  $new = preg_replace('{(.)\1+}', '$1', $new); // get rid of any repeats
  return $new;
}


?>
