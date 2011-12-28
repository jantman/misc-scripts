<?php
  /**
   * Script to pull DNS information for all of your Linode hosted zones, output as CSV.
   *
   * Originally created when I moved DNS from in-house to linode, then started moving subdomains one at a time from my servers to Linode.
   *
   * Uses Kerem Durmus' Linode PHP bindings from <https://github.com/krmdrms/linode/>, many thanks to him for releasing this.
   *
   * INSTALLATION (as per krmdrms README):
   *  pear install Net_URL2-0.3.1
   *  pear install HTTP_Request2-0.5.2
   *  pear channel-discover pear.keremdurmus.com
   *  pear install krmdrms/Services_Linode
   *
   * Also requires php-openssl / php5-openssl
   *
   * USAGE: php linodeDnsToCsv.php
   *
   * Copyright 2011 Jason Antman <http://www.jasonantman.com> <jason@jasonantman.com>, all rights reserved.
   * This script is free for use by anyone anywhere, provided that you comply with the following terms:
   * 1) Keep this notice and copyright statement intact.
   * 2) Send any substantial changes, improvements or bog fixes back to me at the above address.
   * 3) If you include this in a product or redistribute it, you notify me, and include my name in the credits or changelog.
   *
   * The following URL always points to the newest version of this script. If you obtained it from another source, you should
   * check here:
   * $HeadURL$
   * $LastChangedRevision$
   *
   * CHANGELOG:
   * 2011-12-17 Jason Antman <jason@jasonantman.com>:
   *    merged into my svn repo
   * 2011-09-12 Jason Antman <jason@jasonantman.com>:
   *    initial version of script
   *
   */

require_once("/var/www/linode_apikey.php"); // PHP file containing: define("API_KEY_LINODE", "myApiKeyHere");
require_once('Services/Linode.php');

// get list of all domains
$domains = array(); // DOMAINID => domain.tld
try {
  $linode = new Services_Linode(API_KEY_LINODE);
  $result = $linode->domain_list();

  foreach($result['DATA'] as $domain)
    {
      $domains[$domain['DOMAINID']] = $domain["DOMAIN"];
    }
}
catch (Services_Linode_Exception $e)
{
  echo $e->getMessage();
}

$records = array(); // array of resource records
$linode->batching = true;
foreach($domains as $id => $name)
{
  $linode->domain_resource_list(array('DomainID' => $id));
}

try {
  $result = $linode->batchFlush();
  
  foreach($result as $batchPart)
    {
      foreach($batchPart['DATA'] as $rrec)
	{
	  if(! isset($records[$rrec['DOMAINID']])){ $records[$rrec['DOMAINID']] = array();}
	  $records[$rrec['DOMAINID']][$rrec['RESOURCEID']] = array('name' => $rrec['NAME'], 'type' => $rrec['TYPE'], 'target' => $rrec['TARGET']);
	}
    }
}
catch (Services_Linode_Exception $e)
{
  echo $e->getMessage();
}

echo '"recid","domain","name","type","target"'."\n";
foreach($domains as $id => $name)
{
  foreach($records[$id] as $recid => $arr)
    {
      echo '"'.$recid.'","'.$name.'","'.$arr['name'].'","'.$arr['type'].'","'.$arr['target']."\"\n";
    }
}


?>