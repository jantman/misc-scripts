#!/usr/bin/php
<?php
/**
 * script to parse rsyslog impstats output and generate a simple report.
 * right now, we're just reporting on the main Q and imuxsock.
 * 
 * Assumes that you have pstats logging to its own file, like <http://www.rsyslog.com/periodic-statistics-on-rsyslog-counters/>
 *
 * Copyright 2011 Jason Antman <jantman@oit.rutgers.edu> <jason@jasonantman.com>,
 *  on behalf of the taxpayers of the State of New Jersey and/or the students of Rutgers University,
 *  The State University of New Jersey.
 *
 * $HeadURL$
 * $LastChangedRevision$
 *
 */

define("PSTATS_LOG_FILE", "/var/log/rsyslog-stats"); // log file for rsyslog stats

$fh = fopen(PSTATS_LOG_FILE, "r") or die("Unable to open file: ".PSTATS_LOG_FILE."\n");

// variables to hold state
$start_time = 0;

$MAIN_maxSize = 0;
$MAIN_maxEnq = 0;
$MAIN_maxFull = 0;
$MAIN_lastTime = 0;

while (($line = fgets($fh)) !== false)
{
  $matches = array();
  if(preg_match('/(\w+\s+\d+\s+\d+:\d+:\d+).+rsyslogd:.+start$/', $line, $matches))
    {
      if($start_time != 0)
	{
	  // output stats for the last daemon run
	  $period = $MAIN_lastTime - $start_time;
	  echo date("Y-m-d H:i:s", $start_time)." to ".date("Y-m-d H:i:s", $MAIN_lastTime)." len_sec=".$period." MAIN_maxSize=".$MAIN_maxSize." MAIN_maxEnq=".$MAIN_maxEnq." MAIN_maxFull=".$MAIN_maxFull." MAIN_rate_perSec=".round($MAIN_maxEnq / $period, 3)."\n";
	}

      // this line denotes a rsyslogd start
      $start_time = strtotime($matches[1]);
      $MAIN_maxSize = 0;
      $MAIN_maxEnq = 0;
      $MAIN_maxFull = 0;
      $MAIN_lastTime = 0;
    }
  elseif(preg_match('/(\w+\s+\d+\s+\d+:\d+:\d+).+rsyslogd-pstats: main Q: size=(\d*) enqueued=(\d*) full=(\d*) maxqsize=(\d*)/', $line, $matches))
    {
      // mainQ stats line
      $MAIN_lastTime = strtotime($matches[1]);
      if($matches[2] > $MAIN_maxSize){ $MAIN_maxSize = $matches[2];}
      if($matches[3] > $MAIN_maxEnq){ $MAIN_maxEnq = $matches[3];}
      if($matches[4] > $MAIN_maxFull){ $MAIN_maxFull = $matches[4];}
    }
  elseif(preg_match('/(\w+\s+\d+\s+\d+:\d+:\d+).+rsyslogd-pstats: imuxsock: submitted=(\d*) ratelimit.discarded=(\d*) ratelimit.numratelimiters=(\d*)/', $line, $matches))
    {
      // imuxsock stats line

    }


}
fclose($fh);

/*
grep "start" /var/log/rsyslog-stats | tail -2
Sep  9 09:00:06 css-dhcp rsyslogd: [origin software="rsyslogd" swVersion="5.8.5" x-pid="23880" x-info="http://www.rsyslog.com"] start
Sep  9 09:54:31 css-dhcp rsyslogd: [origin software="rsyslogd" swVersion="5.8.5" x-pid="31215" x-info="http://www.rsyslog.com"] start
[root@css-dhcp misc-scripts]# tail -40 /var/log/rsyslog-stats
Sep  9 11:12:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=166767 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:12:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:12:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=54869 full=0 maxqsize=15 
Sep  9 11:12:31 css-dhcp rsyslogd-pstats: main Q: size=3 enqueued=167084 full=0 maxqsize=190 
Sep  9 11:13:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=168986 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:13:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:13:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=55611 full=0 maxqsize=15 
Sep  9 11:13:31 css-dhcp rsyslogd-pstats: main Q: size=3 enqueued=169307 full=0 maxqsize=190 
Sep  9 11:14:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=171043 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:14:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:14:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=56314 full=0 maxqsize=15 
Sep  9 11:14:31 css-dhcp rsyslogd-pstats: main Q: size=5 enqueued=171368 full=0 maxqsize=190 
Sep  9 11:15:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=173180 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:15:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:15:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=57032 full=0 maxqsize=15 
Sep  9 11:15:31 css-dhcp rsyslogd-pstats: main Q: size=3 enqueued=173509 full=0 maxqsize=190 
Sep  9 11:16:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=175264 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:16:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:16:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=57746 full=0 maxqsize=15 
Sep  9 11:16:31 css-dhcp rsyslogd-pstats: main Q: size=3 enqueued=175597 full=0 maxqsize=190 
Sep  9 11:17:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=177236 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:17:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:17:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=58443 full=0 maxqsize=15 
Sep  9 11:17:31 css-dhcp rsyslogd-pstats: main Q: size=3 enqueued=177573 full=0 maxqsize=190 
Sep  9 11:18:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=179299 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:18:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:18:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=59136 full=0 maxqsize=15 
Sep  9 11:18:31 css-dhcp rsyslogd-pstats: main Q: size=31 enqueued=179640 full=0 maxqsize=190 
Sep  9 11:19:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=181281 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:19:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:19:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=59806 full=0 maxqsize=15 
Sep  9 11:19:31 css-dhcp rsyslogd-pstats: main Q: size=52 enqueued=181626 full=0 maxqsize=190 
Sep  9 11:20:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=183352 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:20:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:20:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=60485 full=0 maxqsize=15 
Sep  9 11:20:31 css-dhcp rsyslogd-pstats: main Q: size=3 enqueued=183701 full=0 maxqsize=190 
Sep  9 11:21:31 css-dhcp rsyslogd-pstats: imuxsock: submitted=185426 ratelimit.discarded=0 ratelimit.numratelimiters=0 
Sep  9 11:21:31 css-dhcp rsyslogd-pstats: action 15 queue[DA]: size=0 enqueued=0 full=0 maxqsize=0 
Sep  9 11:21:31 css-dhcp rsyslogd-pstats: action 15 queue: size=0 enqueued=61173 full=0 maxqsize=15 
Sep  9 11:21:31 css-dhcp rsyslogd-pstats: main Q: size=3 enqueued=185779 full=0 maxqsize=190 
*/

?>
