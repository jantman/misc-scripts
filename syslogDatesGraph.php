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
 * DEPENDENCIES:
 * - rrdtool
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

doChart();

function doChart()
{
  global $dates, $keys, $min, $max;

  $rraMax = max($dates);
  $num = ($max - $min) / 60;

  runcmd("rrdtool create --start ".($min - 60)." --step 60 temp.rrd DS:lines:ABSOLUTE:60:0:$rraMax RRA:AVERAGE:0.5:1:$num") or die();

  $count = 0;
  for($i = $min; $i <= ($max + 60); $i+=60)
    {
      // loop through the values in 60-second intervals
      $count++;
      if(isset($dates[$i]))
	{
	  //$dataSet->addPoint(new Point(date("Y-m-d H:i", $i), $dates[$i]));
	  runcmd("rrdtool update temp.rrd $i:".$dates[$i]) or die();
	}
      else
	{
	  // value is 0
	  //$dataSet->addPoint(new Point(date("Y-m-d H:i", $i), 0));
	  runcmd("rrdtool update temp.rrd $i:0") or die();
	}
    }

  /*
rrdtool graph --start -1d --title "css-radius-auth1 - Matching Log Lines Per Minute, Last 24h - ESS-LDAP bind timeout" -v "Lines Per Minute" -S 60 -w 1200 -h 300 \
--x-grid MINUTE:30:HOUR:1:HOUR:2:0:%X \
daily.png DEF:lines=temp.rrd:lines:AVERAGE CDEF:lpm=lines,60,* LINE1:lpm#ff0000:'Lines\n'  COMMENT:'Light gray grid lines every 30 minutes, light red lines every two hours.'

rrdtool graph --start -3d --title "css-radius-auth1 - Matching Log Lines Per Minute, Last 3d - ESS-LDAP bind timeout" -v "Lines Per Minute" -S 60 -w 1200 -h 300 \
--x-grid HOUR:1:HOUR:4:HOUR:6:0:%X \
threeDays.png DEF:lines=temp.rrd:lines:AVERAGE CDEF:lpm=lines,60,* LINE1:lpm#ff0000:'Lines\n' COMMENT:'Light gray grid lines every hour, light red lines every four hours.'

rrdtool graph --start -1w --title "css-radius-auth1 - Matching Log Lines Per Minute, Last 7d - ESS-LDAP bind timeout" -v "Lines Per Minute" -S 60 -w 1200 -h 300 \
--x-grid HOUR:1:HOUR:4:HOUR:12:0:%X \
weekly.png DEF:lines=temp.rrd:lines:AVERAGE CDEF:lpm=lines,60,* LINE1:lpm#ff0000:'Lines\n' COMMENT:'Light gray grid lines every hour, light red lines every four hours.'

*/


  return "";
}

function runcmd($cmd)
{
  echo $cmd."\n";
  exec($cmd, $output, $return);
  if($return == 0){ return true;}
  fwrite(STDERR, "Command '$cmd'\n\texited with status $return: ".implode("\n", $output)."\n");
  return false;
}

?>