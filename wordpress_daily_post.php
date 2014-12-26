#!/usr/bin/php
<?php
/**
 * wordpress_daily_post.php
 * Script to publish the oldest post with a given status, if no
 * other post has been published in 24 hours. Intended to be run
 * via cron on weekdays.
 *
 * Copyright 2012 Jason Antman <jason@jasonantman.com>
 *
 * Licensed under the Apache License, Version 2.0 <http://www.apache.org/licenses/LICENSE-2.0>
 *
 * use it anywhere you want, however you want, provided that this header is left intact,
 * and that if redistributed, credit is given to me.
 *
 * It is strongly requested, but not technically required, that any changes/improvements
 * be emailed to the above address.
 *
 * The latest version of this script will always be available at:
 * https://github.com/jantman/misc-scripts/blob/master/wordpress_daily_post.php
 *
 * Changelog:
 * 2014-12-26 Jason Antman <jason@jasonantman.com>
 *  - GitHub script URL
 * 2012-09-03 Jason Antman <jason@jasonantman.com> - 1.0
 *  - first version
 */

# BEGIN CONFIGURATION
define('WP_LOAD_LOC', '/var/www/vhosts/blog.jasonantman.com/wp-load.php'); // Configure this to the full path of your Wordpress wp-load.php
define('SOURCE_POST_STATUS', 'pending'); // post status to publish
# END CONFIGURATION

$VERBOSE = false;
$DRY_RUN = false;
array_shift($argv);
while(count($argv) > 0) {
  if(isset($argv[0]) && $argv[0] == "-d" || $argv[0] == "--dry-run"){
    $DRY_RUN = true;
    fwrite(STDERR, "DRY RUN ONLY - NOT ACTUALLY PUBLISHING.\n");
  }
  if(isset($argv[0]) && $argv[0] == "-v" || $argv[0] == "--verbose"){
    $VERBOSE = true;
    fwrite(STDERR, "WP_LOAD_LOC=".WP_LOAD_LOC."\n");
    fwrite(STDERR, "SOURCE_POST_STATUS=".SOURCE_POST_STATUS."\n");
  }
  array_shift($argv);
}

$_SERVER['HTTP_HOST'] = 'localhost'; // needed for wp-includes/ms-settings.php:100
require_once(WP_LOAD_LOC);

# check that we're running on a weekday
if(date('N') >= 6) {
#  if($VERBOSE){ fwrite(STDERR, "today is a saturday or sunday, dieing.\n"); }
#  exit(1);
}

# find the publish date/time of the last published post
$published = get_posts(array('numberposts' => 1, 'orderby' => 'post_date', 'order' => 'DESC', 'post_status' => 'publish'));
$post = $published[0];
$pub_date = $post->post_date;
$pub_id = $post->ID;

if(strtotime($pub_date) >= (time() - 86400)) {
  if($VERBOSE){ fwrite(STDERR, "last post (ID $pub_id) within last day ($pub_date). Nothing to do. Exiting.\n"); }
  exit(0);
} else {
  if($VERBOSE){ fwrite(STDERR, "Found last post (ID $pub_id) with post date $pub_date.\n"); }
}


# find the earliest post of status SOURCE_POST_STATUS, if there is one.
$to_post = get_posts(array('numberposts' => 1, 'orderby' => 'post_date', 'order' => 'ASC', 'post_status' => SOURCE_POST_STATUS));
if(count($to_post) < 1) {
  if($VERBOSE) { fwrite(STDERR, "No posts found with status '".SOURCE_POST_STATUS."'. Nothing to do. Exiting.\n"); }
  exit(0);
}

$post = $to_post[0];
$to_pub_id = $post->ID;
$to_pub_date = $post->post_date;
$to_pub_title = $post->post_title;
$now = time();
$new_date = date("Y-m-d H:i:s", $now);
$new_date_gmt = gmdate("Y-m-d H:i:s", $now);

if($VERBOSE){ fwrite(STDERR, "Post to publish: ID=$to_pub_id DATE=$to_pub_date NEW_DATE=$new_date TITLE=$to_pub_title\n"); }

# actually publish it
if(! $DRY_RUN){
  $arr = array('ID' => $to_pub_id, 'post_status' => 'publish', 'post_date' => $new_date, 'post_date_gmt' => $new_date_gmt);
  $ret = wp_update_post($arr); // publish the post
  if($ret == 0) {
    fwrite(STDERR, "ERROR: Post $to_pub_id was not successfully published.");
    exit(1);
  }
  if($VERBOSE){ fwrite(STDERR, "Published post. New ID: $ret\n"); }
}
else {
  fwrite(STDERR, "Dry run only, not publishing post.\n");
}

# check that the post really was published
$published = get_posts(array('numberposts' => 1, 'orderby' => 'post_date', 'order' => 'DESC', 'post_status' => 'publish'));
$post = $published[0];
$pub_date = $post->post_date;
$pub_id = $post->ID;
$pub_title = $post->post_title;
$pub_guid = $post->guid;

if($pub_title != $to_pub_title) {
  fwrite(STDERR, "ERROR: title of most recent post does not match title of what we wanted to post.");
  exit(1);
}

fwrite(STDOUT, "Published post $pub_id at $pub_date\n");
fwrite(STDOUT, "Title: $pub_title\n");
fwrite(STDOUT, "\n\n\n GUID/Link: $pub_guid\n");
fwrite(STDOUT, "\n\n".__FILE__." on ".trim(shell_exec('hostname --fqdn'))." running as ".get_current_user()."\n");

?>
