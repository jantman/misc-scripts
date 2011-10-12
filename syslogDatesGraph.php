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

array_shift($argv); // discard first argument (script name)

if(! isset($argv[0]) || $argv[0] == "--help" || $argv[0] == "-h")
{
  die("USAGE: syslogDatesGraph.php <filename.ser> - make RRD and graphs\n\tsyslogDatesGraph.php --rrd <filename.ser> - make RRD file only\n\tsyslogDatesGraph.php --graphs <filename.rrd> - make graphs from existing rrd");
}

$fname = trim(array_shift($argv));
if($fname == "--rrd" || $fname == "--graphs"){ $type = $fname; $fname = trim(array_shift($argv));} else { $type = "--all";}

if(! file_exists($fname) || ! is_readable($fname)){ die("ERROR: File $fname does not exist or is not readable.\n");}

if($type == "--rrd" || $type == "--all")
  {
    $ser = file_get_contents($fname) or die("ERROR: Unable to read file contents.\n");
    $arr = unserialize($ser) or die("ERROR: Unable to unserialize string.\n");

    $dates = $arr['dates'];

    echo "Read in serialized data file... ".$arr['totalLines']." total log lines, ".$arr['failed']." failed to parse, ".count($dates)." distinct 1-minute intervals.\n";

    ksort($dates);

    $keys = array_keys($dates);
    $min = min($keys);
    $max = max($keys);

    $fname = "syslog_".date("Ymd", $min)."_".date("Ymd", $max).".rrd";

    $fname = makeRRD($fname);

    echo "Wrote RRD to $fname for ".date("Y-m-d H:i:s", $min)." to ".date("Y-m-d H:i:s", $max)."\n";
  }

if($type == "--all")
  {
    makeGraphs($fname, $min, $max);
  }
elseif($type == "--graphs")
{
  makeGraphs($fname);
}

function makeRRD($fname = "temp.rrd")
{
  global $dates, $keys, $min, $max;

  $rraMax = max($dates);
  $num = ($max - $min) / 60;

  runcmd("rrdtool create --start ".($min - 60)." --step 60 $fname DS:lines:ABSOLUTE:60:0:$rraMax RRA:AVERAGE:0.5:1:$num") or die();

  $count = 0;
  for($i = $min; $i <= ($max + 60); $i+=60)
    {
      // loop through the values in 60-second intervals
      $count++;
      if(isset($dates[$i]))
	{
	  //$dataSet->addPoint(new Point(date("Y-m-d H:i", $i), $dates[$i]));
	  runcmd("rrdtool update $fname $i:".$dates[$i]) or die();
	}
      else
	{
	  // value is 0
	  //$dataSet->addPoint(new Point(date("Y-m-d H:i", $i), 0));
	  runcmd("rrdtool update $fname $i:0") or die();
	}
    }

  return $fname;
}

function makeGraphs($rrd, $min_ts = 0, $max_ts = 0)
{
  echo "Making graphs from rrd file $rrd\n";
  
  $files = "";
  if($min_ts != 0 && $max_ts != 0){ $fname_ext = "_".date("Ymd", $min_ts)."_".date("Ymd", $max_ts);} else { $fname_ext = "";}
  runcmd("rrdtool graph --start -1d --title \"css-radius-auth1 - Matching Log Lines Per Minute, Last 24h - ESS-LDAP bind timeout\" -v \"Lines Per Minute\" -S 60 -w 1200 -h 300 --x-grid MINUTE:30:HOUR:1:HOUR:2:0:%X daily".$fname_ext.".png DEF:lines=$rrd:lines:AVERAGE CDEF:lpm=lines,60,* LINE1:lpm#ff0000:'Lines\n'  COMMENT:'Light gray grid lines every 30 minutes, light red lines every two hours.'");
  echo "Wrote daily graph to daily".$fname_ext.".png\n";
  $files .= "daily".$fname_ext.".png ";
  runcmd("rrdtool graph --start -3d --title \"css-radius-auth1 - Matching Log Lines Per Minute, Last 3d - ESS-LDAP bind timeout\" -v \"Lines Per Minute\" -S 60 -w 1200 -h 300 --x-grid HOUR:1:HOUR:4:HOUR:6:0:%X threeDays".$fname_ext.".png DEF:lines=$rrd:lines:AVERAGE CDEF:lpm=lines,60,* LINE1:lpm#ff0000:'Lines\n' COMMENT:'Light gray grid lines every hour, light red lines every four hours.'");
  echo "Wrote threeDay graph to threeDays".$fname_ext.".png\n";
  $files .= "threeDays".$fname_ext.".png ";
  runcmd("rrdtool graph --start -1w --title \"css-radius-auth1 - Matching Log Lines Per Minute, Last 7d - ESS-LDAP bind timeout\" -v \"Lines Per Minute\" -S 60 -w 1200 -h 300 --x-grid HOUR:1:HOUR:4:HOUR:12:0:%X weekly".$fname_ext.".png DEF:lines=$rrd:lines:AVERAGE CDEF:lpm=lines,60,* LINE1:lpm#ff0000:'Lines\n' COMMENT:'Light gray grid lines every hour, light red lines every four hours.'");
  echo "Wrote weekly graph to weekly".$fname_ext.".png\n";
  $files .= "weekly".$fname_ext.".png ";

  runcmd("montage -geometry 1300x400 -tile 1x3 ".$files."combined".$fname_ext.".png");
  

  echo "Done.\n";
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