-- MySQL dump 10.10
--
-- Host: localhost    Database: wireless
-- ------------------------------------------------------
-- Server version	5.0.26-log
-- ------------------------------------------------------
-- SQL schema for updateAPconfigs.php.inc database
-- Functions for working with MAC authentication in Ubiquiti Networks AirOS v2 configs.
--
-- Copyright 2010, 2011 Jason Antman, All Rights Reserved.
--
-- These functions may be used for any purpose provided that:
-- 1) This copyright notice is kept intact.
-- 2) You send back to me any changes/modifications/bugfixes that you make.
-- 3) This may not be included in commercial software which is sold for a fee, unless you discuss this with me first.
--
-- @author Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
--
-- Announcement post: <http://blog.jasonantman.com/2011/01/managing-ubiquiti-networks-mac-acls-from-a-script/>
--
-- The canonical current version of this script lives at:
-- $HeadURL$
-- $LastChangedRevision$
--

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `macs`
--

DROP TABLE IF EXISTS `macs`;
CREATE TABLE `macs` (
  `mac` varchar(20) NOT NULL,
  `EMTid` varchar(10) default NULL,
  `username` varchar(30) default NULL,
  `userDN` varchar(100) default NULL,
  `alias` varchar(100) default NULL,
  PRIMARY KEY  (`mac`)
) ENGINE=MyISAM DEFAULT CHARSET=latin1;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2011-01-06 21:09:02
