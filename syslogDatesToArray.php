#!/usr/bin/php
<?php
/**
 ********************************************************************************************************************
 * Dead-simple two-part script to help visualize time distribution of syslog messages. This is the log host part.
 * Reads syslog lines on STDIN, extracts the timestamps and outputs a PHP serialized array (to STDOUT) of the
 * count of  messages per minute for the entire time period given. 
 *
 * The server-side part reads in the serialized array and outputs a number of graphs showing time distribution 
 * of the log messages.
 *
 * Written this way with the (perhaps invalid) assumptions that you have a minimal PHP installation on your syslog
 * host, and a full PHP installation with GD, etc. on another (web) server somewhere, better suited to the graphing.
 *
 ********************************************************************************************************************
 * Copyright 2011 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com> All Rights Reserved.
 *
 * LICENSE:
 * This script may be used, modified and distributed provided that the following terms are met:
 * 1) This notice, license, copyright statement, and all URLs, names, email addresses, etc. are left intact.
 * 2) Any and all substantitive changes/feature additions/bug fixes are sent back to me for inclusion in the next version.
 * 3) The below changelog is kept intact and up-to-date.
 ********************************************************************************************************************
 * The canonical source of this script is:
 * $HeadURL$
 * $LastChangedRevision$
 ********************************************************************************************************************
 * CHANGELOG:
 * 2011-09-28 jason@jasonantman.com:
 *    - first version of script
 ********************************************************************************************************************
 */

$fh = fopen("php://stdin", 'r') or die("Unable to open STDIN for reading.");

$dates = array(); // array to hold our syslog data, ts => count, where TS is integer timestamp of the bottom of the minute, and count is number of lines.
$failed = 0;
$count = 0;
while(($line = fgets($fh)) !== false)
{
  // read a line...
  $foo = dateFromSyslog($line);
  $count++;
  if(! $foo){ $failed++; continue;}
  $date = strtotime(date("Y-m-d H:i", $foo).":00");
  if(! isset($dates[$date])){ $dates[$date] = 1;} else { $dates[$date]++;}
}

// sum up all the values in the array as a count
$sum = array_sum($dates);

if( ($sum + $failed) != $count){ die("ERROR: Sum appears wrong.\n");}

echo serialize(array('dates' => $dates, 'failed' => $failed, 'totalLines' => $count, 'sum' => $sum));

/**
 * Parse the date out of a syslog line, return as an integer timestamp.
 *
 * Returns boolean False on error. Expects date to be at the beginning of the syslog line,
 * in standard (traditional) syslog date format, that is, matching: 
 *
 * @param string $line the full syslog line
 * @return integer or False on error
 */
function dateFromSyslog($line)
{
  // "((Sun|Mon|Tue|Wed|Thu|Fri|Sat) )?" is to cope with software that writes logs directly, starting with day of week (FreeRADIUS radiusd.log)
  $ptn = "/^((Sun|Mon|Tue|Wed|Thu|Fri|Sat) )?(\S{3}\s{1,2}\d{1,2} \d{2}:\d{2}:\d{2})/";
  $matches = array();
  $foo = preg_match($ptn, $line, $matches);
  if(! $foo){ return false;}
  return strtotime($matches[0]);
}

?>