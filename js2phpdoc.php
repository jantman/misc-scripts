#!/usr/bin/php
<?php

/**
 * Command line script to take comments and function prototypes from JS files and make them PHP-ish to be parsed by phpdoc.
 *
 * Reads all *.js files in a specified directory, extracts only comments and function definitions, writes them to either 
 * same-named files in an output directory (if specified), or otherwise to files ending in .js-php in the same directory.
 *
 * Copyright 2010 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
 *
 * The canonical source of the latest version of this script is:
 *  <https://github.com/jantman/misc-scripts/blob/master/js2phpdoc.php>
 *
 * Information on usage and installation can be found at:
 *  <http://blog.jasonantman.com/2010/08/documentation-generation-for-web-apps-php-and-javascript/>
 *
 * INSTALLATION:
 * In order for this to work with PHPdoc nicely, you need to edit your PHPdocumentor default.ini (on my system, at /usr/share/php5/PEAR/data/PhpDocumentor/phpDocumentor.ini),
 *  and add a line with "js" or "js-php" to the [_phpDocumentor_phpfile_exts] section, to get PHPDocumentor to parse .js or .js-php files as PHP.
 *
 * USAGE:
 *  js2phpdoc.php [--help] <input directory> [output directory]
 *
 * EXPECTATIONS:
 *  This script expects relatively strict formatting of source files, to work with phpdoc...
 *  - all comments that matter (docblocks) are phpdoc-style
 *  - all function definitions appear on their own line
 *  - it may be confused by inner functions, variable functions, etc.
 *  - function definitions should appear on their own line (no code on that line)
 *  - basically, keying on "function [A-Za-z0-9_-]+()" should get you a line with just that stuff, and maybe an opening curly brace.
 *
 *
 * MAKEFILE:
 *  To generate documentation, assuming your CWD is the project root directory, and I have PHP files I want to parse in the CWD and "inc/", and JS files in "js/", I use the following Makefile rule:
 *  I also find it helpful to use different package names like "Project-PHP" and "Project-JS"
 *
 * using the temp/directory allows our converted JS files to not pollute the actual source code.
 * copying everything else here preserves file paths as they are in the actual source.
 *
 * docs:
 *	mkdir -p temp/js
 *	bin/js2phpdoc.php js/ temp/js/
 *	cp -r inc temp/
 *	cp *.php temp/
 *	phpdoc -c docs/default.ini
 *      rm -Rf temp
 *
 * LICENSE:
 *  This file is free to use, modify, and distribute under the spirit (but not the exact terms) of the GNU GPL v3.
 *  The following terms apply:
 *  - this header comment must be kept intact, along with all copyright notices and changelog.
 *  - if you make modifications, you must:
 *     1) send them back to me for inclusion in the next version
 *     2) Update the changelog below as appropriate.
 *
 * @author jantman <jason@jasonantman.com> <http://www.jasonantman.com>
 * @author rhorber <raphael.horber@gmail.com>
 *
 * CHANGELOG:
 *
 * 2010-08-25 jantman:
 *  - initial version
 *
 * 2012-06-01 rhorber:
 *  - added recursive file parsing
 *  - changed output file extension to .js-php and put output in same path as input
 *
 * 2012-06-02 jantman:
 *  - changed to use getopt() for better argument handling
 *  - merged in rhorber's changes, updated documentation
 *
 * @package MPAC-NewCall-PHP
 */

$path = $argv[1];
$output_path = $argv[2];

// test if we have a help argument (tests first argument only)
if($path == "--help" || $path == "-h")
  {
    // if so, echo usage information and exit
    usage();
    exit(1);
  }


// test that input path exists and is readale
if(! is_dir($path) || ! is_readable($path))
  {
    fwrite(STDERR, "ERROR: Specified path ($path) does not exist or is not a directory or is not readable. Exiting.\n");
    exit(1);
  }

// test that output directory exists and is writable
if(! is_dir($output_path) || ! is_writable($output_path))
  {
    fwrite(STDERR, "ERROR: Specified output path ($output_path) does not exist or is not a directory or is not writable. Exiting.\n");
    exit(1);
  }

if(substr($path, strlen($path)-1) != "/"){ $path .= "/";}
if(substr($output_path, strlen($output_path)-1) != "/"){ $output_path .= "/";}

// iterate through files in input path
$dh = opendir($path);
if(! $dh){ fwrite(STDOUT, "ERROR: Unable to open input directory ($path) for reading.\n"); exit(1);}
while(false !== ($file = readdir($dh)))
  {
    if(substr($file, strlen($file)-3) == ".js")
      {
	$cleaned = doFile($path.$file);
	$fh = fopen($output_path.$file, "w");
	if(! $fh){ fwrite(STDERR, "ERROR: Unable to open output file(".$output_path.$file.") for writing. Exiting.\n"); exit(1);}
	fwrite($fh, $cleaned);
	fclose($fh);
      }
  }
closedir($dh);

/**
 * Read file at given path, convent to output ready for phpdoc (opening PHP tag, phpdoc-style comments, function definitions), return string.
 *
 * @param string $path path to file
 * @return string
 */
function doFile($path)
{
  $str = ""; // string to return

  $contents = file_get_contents($path); // get file contents
  if(! $contents){ fwrite(STDERR, "ERROR: Unable to read file $path. Exiting."); exit(1);}

  $function_pattern = '/^[[:space:]]*function [A-Za-z0-9_-]+[[:space:]]*\(/m'; // preg pattern to match function definitions

  $lines = explode("\n", $contents); // explode string of file contents into array of lines

  // variables to hold state in loop
  $in_comment = false;
  $comment = "";

  $str .= '<?php'."\n";

  // loop through lines
  foreach($lines as $line)
    {
      $trimmed = trim($line); // get a trimmed (no whitespace) version of the line

      if(substr($trimmed, 0, 3) == "/**")
	{
	  // this line is the start of a phpdoc-style comment
	  $in_comment = true;
	  $comment .= $line."\n";
	}
      elseif($in_comment && substr($trimmed, strlen($trimmed)-2) == "*/")
	{
	  // this line is the end of a phpdoc-style comment
	  $comment .= $line."\n";
	  $str .= $comment."\n";
	  $in_comment = false;
	  $comment = "";
	}
      elseif($in_comment)
	{
	  // this line is in a phpdoc-style comment
	  $comment .= $line."\n";
	}
      elseif(preg_match($function_pattern, $line))
	{
	  // this line is a function definition
	  if(! strpos($line, "{")){ $line .= " { ";}
	  if(! strpos($line, "}")){ $line .= " } ";}

	  $str .= $line."\n\n";
	}
      // else we don't care about this line
    }

  $str .= "\n".'?>'."\n";
  return $str;
}

/**
 * Echo usage information to STDOUT.
 *
 */
function usage()
{
  echo "js2phpdoc.php - Command line script to take comments and function prototypes from JS files and make them PHP-ish to be parsed by phpdoc.\n\n";
  echo "Reads all *.js files in a specified directory, extracts only comments and function definitions, writes them to same-named files in an output directory.\n";
  echo "USAGE:\n";
  echo "js2phpdoc.php [--help] <input directory> <output directory>\n";
}

?>
