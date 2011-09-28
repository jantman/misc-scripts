#!/usr/bin/php
<?php
/**
 ********************************************************************************************************************
 * Dead-simple two-part script to help visualize time distribution of syslog messages. This is the graph host part.
 * Reads in the serialized array created by the server part, and generates a number of graphs (in CWD) of the data.
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

if(! isset($argv[1]))
{
  die("USAGE: syslogDatesGraph.php <filename.ser>\n");
}

$fname = trim($argv[1]);
if(! file_exists($fname) || ! is_readable($fname)){ die("ERROR: File $fname does not exist or is not readable.\n");}

$ser = file_get_contents($fname) or die("ERROR: Unable to read file contents.\n");
$arr = unserialize($ser) or die("ERROR: Unable to unserialize string.\n");

$dates = $arr['dates'];

echo "Read in serialized data file... ".$arr['totalLines']." total log lines, ".$arr['failed']." failed to parse, ".count($dates)." distinct 1-minute intervals.\n";

ksort($dates);

$keys = array_keys($dates);
$min = min($keys);
$max = max($keys);

for($i = $min; $i < ($max + 60); $i+=60)
{
  // loop through the values in 60-second intervals
  if(isset($dates[$i]))
    {

    }
  else
    {
      // value is 0
    }
}

?>