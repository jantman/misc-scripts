#!/usr/bin/php
<?php
/**
 * script to parse rsyslog impstats output and generate a simple report.
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

while (($line = fgets($fh)) !== false)
{
  


}
fclose($fh);

?>
