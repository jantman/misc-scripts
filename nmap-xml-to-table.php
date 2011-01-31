#!/usr/bin/php
<?php
/**
 * Script to transform multiple nmap XML output files (presumably of the same host/port range with different scan options) into a HTML table
 *
 * Copyright 2011 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com> all rights reserved.
 *  Distribution and use of this script is unlimited, provided that you leave this notice intact and send any corrections/additions back to me.
 *
 * This is assuming a relatively simple scan - only one protocol, one or more hosts, one or more ports, and that different scans will be differentiated only by type
 *
 * USAGE: nmap-xml-to-table.php [xml file] [xml file] [...]
 *
 * $LastChangedRevision$
 * $HeadURL$
 *
 */

array_shift($argv); // get rid of script name

$files = array();
foreach($argv as $file)
{
  if(file_exists($file) && is_readable($file))
    {
      $files[] = $file;
    }
  else
    {
      fwrite(STDERR, "File $file does not exist or is not readable, skipping.\n");
    }
}

$results = array();
$scanInfo = array();
$hostAndPort = array();

$count = 0;
foreach($files as $file)
{
  $info = getScanResults($file);
  $results[$count] = $info['hosts'];
  $info['scan']['filename'] = $file;
  $scanInfo[$count] = $info['scan'];
  foreach($info['hosts'] as $host => $portArr)
    {
      if(! isset($hostAndPort[$host])){ $hostAndPort[$host] = array();}
      foreach($portArr as $port => $foo)
	{
	  $hostAndPort[$host][$port] = $foo['service'];
	}
    }
  $count++;
}

?>

<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">

<head>
<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1" />
<title>Condensed NMAP scan results</title>

<style type="text/css">
table.result {
  border-width: 1px 1px 1px 1px;
  border-spacing: 0px;
  border-style: solid solid solid solid;
  border-color: black black black black;
  border-collapse: separate;
  background-color: white;
  margin-left: auto;
  margin-right: auto;
}
table.result th {
  border-width: 1px 1px 1px 1px;
 padding: 2px 2px 2px 2px;
  border-style: solid solid solid solid;
  border-color: black black black black;
  background-color: white;
  -moz-border-radius: 0px 0px 0px 0px;
}
table.result td {
  border-width: 1px 1px 1px 1px;
 padding: 2px 2px 2px 2px;
  border-style: solid solid solid solid;
  border-color: black black black black;
  background-color: white;
  -moz-border-radius: 0px 0px 0px 0px;
}
h2 { text-align: center;}
.lookhere { color: red;}
</style>
</head>
<body>
<h2>Nmap scan results (condensed)</h2>
<?php

// output scan information
echo '<table class="result">'."\n";
echo '<tr><th colspan="7">Scans</th></tr>'."\n";
echo '<tr><th>Num</th><th>proto</th><th>type</th><th>Services</th><th>num hosts</th><th>command</th><th>filename</th></tr>'."\n";
foreach($scanInfo as $num => $arr)
{
  echo '<tr><td>'.$num.'</td><td>'.$arr['protocol'].'</td><td>'.$arr['type'].'</td><td>'.$arr['services'].'</td><td>'.$arr['numHosts'].'</td><td><pre>'.$arr['command'].'</pre></td><td>'.$arr['filename'].'</td></tr>'."\n";
}
echo '</table>'."\n";

echo '<br />'."\n";

echo '<table class="result">'."\n";
echo '<tr><th colspan="'.(count($scanInfo)+1).'">Results</th></tr>'."\n";
echo '<tr><th>Port</th>';
for($i = 0; $i < count($scanInfo); $i++){ echo '<th>'.$i.' ('.$scanInfo[$i]['type'].')</th>';}
echo '</tr>'."\n";
foreach($hostAndPort as $host => $portArr)
{
  echo '<tr><th colspan="'.(count($scanInfo)+1).'">'.$host.'</th></tr>'."\n";

  foreach($portArr as $portName => $service)
    {
      echo '<tr><td>'.$portName.($service != "" ? " (".$service.")" : "").'</td>';
      foreach($scanInfo as $scanNum => $arr)
	{
	  if(isset($results[$scanNum][$host][$portName]))
	    {
	      echo '<td>'.(($results[$scanNum][$host][$portName]['state'] == "open" || $results[$scanNum][$host][$portName]['state'] == "closed" || $results[$scanNum][$host][$portName]['state'] == "unfiltered") ? '<span class="lookhere">' : '').$results[$scanNum][$host][$portName]['state'].' ('.$results[$scanNum][$host][$portName]['state_reason'].(isset($results[$scanNum][$host][$portName]['state_reason_ip']) ? ' '.$results[$scanNum][$host][$portName]['state_reason_ip'] : '').')'.(($results[$scanNum][$host][$portName]['state'] == "open" || $results[$scanNum][$host][$portName]['state'] == "closed" || $results[$scanNum][$host][$portName]['state'] == "unfiltered") ? '</span>' : '').'</td>';
	    }
	  else
	    {
	      echo '<td><em>n/a</em></td>';
	    }
	}
      echo '</tr>'."\n";
    }

}
echo '</table>'."\n";

/**
 * Parse meaningful information from a nmap XML output file and return it as an array
 *
 * @return array
 */
function getScanResults($file)
{
  $xml = simplexml_load_file($file);

  $result = array("scan" => array(), "hosts" => array());

  $command = $xml->attributes();
  $command = (string)$command['args'];
  $result['scan']['command'] = $command;

  $foo = $xml->scaninfo->attributes();
  $result['scan']['type'] = (string)$foo['type'];
  $result['scan']['protocol'] = (string)$foo['protocol'];
  $result['scan']['services'] = (string)$foo['services'];

  $count = 0;
  foreach($xml->host as $host)
    {
      $count++;

      $foo = $host->address->attributes();
      $addr = (string)$foo['addr'];

      $arr = array(); // array to hold ports and results

      // <port protocol="tcp" portid="445"><state state="filtered" reason="admin-prohibited" reason_ttl="241" reason_ip="67.83.255.41"/><service name="microsoft-ds" method="table" conf="3" /></port>
      foreach($host->ports->port as $port)
	{
	  $foo = $port->attributes();
	  $bar = array();
	  
	  $name = (string)($foo['protocol']." ".$foo['portid']);
	  $bar['protocol'] = (string)$foo['protocol'];
	  $bar['portid'] = (string)$foo['portid'];
	  $bar['name'] = $name;

	  $foo = $port->state->attributes();
	  $bar['state'] = (string)$foo['state'];
	  $bar['state_reason'] = (string)$foo['reason'];
	  $bar['state_reason_ttl'] = (string)$foo['reason_ttl'];
	  if(isset($foo['reason_ip'])){ $bar['state_reason_ip'] = (string)$foo['reason_ip'];}

	  if($port->service)
	    {
	      $foo = $port->service->attributes();
	      $bar['service'] = (string)$foo['name'];
	    }

	  $arr[$name] = $bar;
	}
      $result['hosts'][$addr] = $arr;
    }

  $result['scan']['numHosts'] = $count;
  return $result;
}

?>
</body>
</html>