#!/usr/bin/env php
<?php
  /**
   * Script to dump all URLs from a Firefox3 sessionstore.js file as text or HTML.
   * Copyright 2010 Jason Antman <http://www.jasonantman.com> <jason@jasonantman.com> all rights reserved.
   * This script can be distributed, modified, used, etc. without limit provided that any 
   *  modifications are sent back to me and this notice is kept intact, and the changelog is updated.
   **********************************************
   * Canonical URL to current version:
   *    <http://svn.jasonantman.com/misc-scripts/dumpFirefoxSession.php>
   **********************************************
   * $HeadURL$
   * $LastChangedRevision$
   **********************************************
   * Dependencies:
   *  PHP5 with JSON
   **********************************************
   * TESTED FOR:
   *  Firefox 3.5.7 on OpenSuSE 11.1 x86_64
   *
   **********************************************
   * CHANGELOG:
   *
   * 2010-08-17 jantman:
   *    original version
   *
   **********************************************
   * USAGE: dumpFirefoxSession.php [--text | --html] [sessionstore.js]
   **********************************************
   */

array_shift($argv); // get rid of script name

if(isset($argv[0]) && ($argv[0] == "--help" || $argv[0] == "-h"))
  {
    usage();
    exit(0);
  }

$outputHTML = false;

$arg = array_shift($argv);
if($arg == "--html"){ $outputHTML = true; $arg = array_shift($argv); }


if($arg != NULL)
  {
    $filePath = $arg;
    if(! file_exists($filePath)){ fwrite(STDERR, "File $filePath does not exist. Dieing.\n"); exit(1);}
  }
else
  {
    if(file_exists("sessionstore.js"))
      {
	$filePath = "sessionstore.js";
	fwrite(STDERR, "No sessionstore.js path specified, using ./sessionstore.js\n");
      }
    else
      {
	fwrite(STDERR, "No sessionstore.js path specified and ./sessionstore.js not present... exiting.\n");
	usage();
	exit(1);
      }
  }

// we have a file that exists
$contents = file_get_contents($filePath);
if(! $contents)
  {
    fwrite(STDERR, "ERROR: Could not get contents of file $filePath. Dieing.\n");
    exit(1);
  }

// begin hacks to parse sessionstore.js as valid JSON
$contents = trim($contents);
$contents = trim($contents, "()");
// end hacks

$decoded = json_decode($contents, true); // return as an assoc array
if($decoded == NULL)
  {
    fwrite(STDERR, "ERROR: json_decode failed on file contents.\n");
    exit(1);
  }

// we're only interested in open windows and tabs
$windows = $decoded['windows'];

foreach($windows as $name => $arr)
{
  doWindow($name, $arr);
}

// FUNCTIONS

function doWindow($name, $arr)
{
  global $outputHTML;
  if($outputHTML)
    {
      echo "<h1>Window $name</h1>\n";
      echo '<ol>'."\n";
    }
  else
    {
      echo "====WINDOW $name====\n";
    }
  
  $selected = $arr['selected'];

  foreach($arr['tabs'] as $key => $val)
    {
      $foo = count($val['entries']);
      $current = $val['entries'][$foo-1];
      if($outputHTML)
	{
	  echo '<li>';
	  if($key == $selected){ echo '<strong>SELECTED: </strong>';}
	  echo '<a href="'.$current['url'].'">'.$current['title'].'</a>';
	  echo '</li>'."\n";
	}
      else
	{
	  if($key == $selected) { fwrite(STDOUT, "!!SELECTED!!");}
	  echo $current['url']."\n";
	}
    }


  if($outputHTML){ echo '</ol>'."\n";}

}

function usage()
{
  fwrite(STDERR, "dumpFirefoxSession.php by Jason Antman <http://www.jasonantman.com>\n");
  fwrite(STDERR, "\tUSAGE: dumpFirefoxSession.php [--text | --html ] [path to sessionstore.js]\n");
}

?>