misc-scripts
=============

[![Project Status: Active - The project has reached a stable, usable state and is being actively developed.](http://www.repostatus.org/badges/0.1.0/active.svg)](http://www.repostatus.org/#active)

This is a collection of miscellaneous scripts that I've written or modified
for my use. Hopefully they may be of some use to others. When I get a chance,
I'll try and update this readme with descriptions of all of the scripts.

Unless otherwise noted, these are distributed under the terms of the LICENSE
file.

* __add_team_to_github_org_repos.py__ - Python script to add a given GitHub Team to all of the specified Organization's repositories.
* __apache_log_verify_site_move.py__ - Python script that parses Apache HTTPD access logs, finds all unique URLs, and compares the current HTTP response code to that of another server. Useful when moving a site.
* __artifactory_support_bundle.py__ - Python script using ``requests`` to generate, list, and download JFrog Artifactory support bundles via the ReST API, from one or more instances/nodes.
* __asg_instances.py__ - Script to list instances in an ASG and their IP addresses, given an ASG name.
* __aws_api_gateway_lint.py__ - Script using boto3 to attempt to identify unused or idle API Gateways.
* __aws-count-tag-names.py__ - Using boto3, scan all AWS resources in the current account, and produce a report detailing all of the distinct tag names and the number of resources having each one.
* __aws_creds_report_csv_filter.py__ - Filter the AWS IAM Credentials Report (CSV) by credential age and/or last used time.
* __aws_cw_log_group_daily_stats.py__ - Python script using boto3 to query CloudWatch Metrics for the IncomingBytes and IncomingLogEvents metrics for one or more LogGroups, across all regions. Retrieves metrics at the 24-hour resolution for N (default 7) days.
* __aws_delete_user.py__ - Python/boto3 script to delete an IAM user including all of its associated resources, with optional dry-run.
* __aws_find_duplicate_sgs.py__ - Using boto3, find duplicated EC2 Security Groups (optionally limited to one VPC).
* __aws_limit_increases_for_service.py__ - Script using boto3 to show all Limit Increase support tickets for a specified service.
* __aws_region_stats.py__ - Python script to print a table with some statistics from each AWS region. Stats include number of RDS instances, EC2 instances, volumes, snapshots, VPCs, and AMIs, ECS clusters, ELBs and ASGs.
* __aws_sg_summary.py__ - Print a summary of all SGs in the current account/region, their rules, and what's in them.
* __aws_subnet_available_ips.py__ - Print information on used and available IPs in an AWS subnet.
* __aws_subnet_ip_usage.py__ - Given an AWS Subnet ID or CIDR, report on the usable number of IPs, used IPs, and how many additional IPs would be taken up if all ELBs and ASGs scaled out.
* __bigipcookie.pl__ - Perl script to de/encode F5 BigIp persistence cookies.
* __bgw210-700_to_graphite.py__ - Pull stats from AT&T / Arris BWM210-700 router web UI and push to graphite.
* __centos7_rpmbuild.Vagrantfile__ - __Moved to [https://github.com/jantman/rpmbuild-vagrant-boxes](https://github.com/jantman/rpmbuild-vagrant-boxes)__
* __check_url_list.py__ - Script to check a list of URLs (passed on stdin) for response code, and for response code of the final path in a series of redirects.
* __cm600_to_graphite.py__ - Pull stats from Netgear CM600 modem web UI and push to graphite.
* __cmd-wrapper.c__ - C wrapper for a setuid/gid command, to ensure that ONLY a certain command and args can be run.
* __collectRsyslogInfo.php__ - Script to collect information on a crashed/hung rsyslogd process, and log it all somewhere.
* __cookies_from_pdml.py__ - Script to parse http Cookie header field from WireShark PDML XML.
* __dashsnap.py__ - script to snapshot a graphite dashboard at specified intervals in the past (i.e. the last 2,4,6 hours) or a single specified time range. Snapshots both PNG images and raw JSON data, builds directory with HTML files.
* __disqus_backup.py__ - script to backup all Disqus comments for a site.
* __dot_find_cycles.py__ - uses Pydot and NetworkX to find cycles in a dot file directed graph (i.e. the graph output of Puppet)
* __dump_firefox_session.py__ - Script to dump all URLs from a Firefox3 sessionstore.js or modern Firefox sessionstore.jsonlz4.
* __dumpMysqlGrants.sh__ - Script to dump all grants from a MySQL server, for input into another.
* __dump_skype_logs.py__ - Script to dump all Skype logs from a main.db file to HTML
* __dump_sphinx_objects_inventory.py__ - Process URL for intersphinx targets and emit html or text.
* __dynamodb_to_csv.py__ - Python/boto3 script to dump all data in a DynamoDB table to CSV.
* __ec2-list-all-tags.py__ - Using boto3, list all distinct tag names on all EC2 instances in all regions.
* __find_outdated_puppets.py__ - Script to look at a Puppet Dashboard unhidden-nodes.csv and extract the latest report time for each node, optionally, list nodes with runtime BEFORE a string.
* __find_test_order_problems.py__ - Script to run tests multiple times and analyze JUnit results XML, to find tests with order-dependent failures.
* __firefox_recovery_to_html.py__ - Script to convert Firefox profile sessionstore-backups/recovery.js to HTML links
* __get_addons.py__ - Unmaintained script to download WoW addons from CurseForge.
* __gist.py__ - Simple python script to upload a file as a private Gist on GitHub. Prompts interactively for Auth token, so usable from shared servers.
* __git_repo_diff.py__ - uses GitPython to compare 2 git repo clones and report on branches that only exist in one, or have different head commits in the two repos
* __github_clone_setup.py__ - script using github3.py to add upstream remote for any clone of a github fork, and add refs to check out pull requests from origin and upstream.
* __github_find_member_with_key.py__ - Script using PyGithub to list an organization's members, and then find who has a specified public key.
* __github_irc_hooks.py__ - script to setup GitHub repo IRC service hooks
* __github_issue_watch_pushover.py__ - Poll github for updates to issues, notify via Pushover if there are any.
* __github_label_setup.py__ - script to setup a given set of labels on all of your (or an org's) GitHub repos.
* __gmvault_link_labels.py__ - Script to iterate over ALL messages in a [GMVault](http://gmvault.org/) backup DB directory and symlink them into per-label per-thread directories.
* __har_urls.py__ - Script to dump all URLs and their status codes from a JSON [HTTP Archive (HAR)](http://www.softwareishard.com/blog/firebug/http-archive-specification/) file, such as those generated by the [Firebug NetExport extension](http://getfirebug.com/wiki/index.php/Firebug_Extensions#NetExport)
* __hipchat_date_history.py__ - Python script to retrieve HipChat room history for a specific date.
* __htmldata.py__ - Perl library to manipulate HTML or XHTML documents, required by mw2html-auth
* __increment_zone_serial__ - This script updates/increments the bind zone file serial number in a file specified as the first argument
* __ismerged__ - shell script that takes a git branch name, and tells if it is merged into master or not
* __jenkins_list_plugins.py__ - Python script to query Jenkins for all installed plugins, and list them. Optionally output as a block of Puppet code for the [puppet-jenkins](https://github.com/jenkinsci/puppet-jenkins) module.
* __jenkins_node_labels.py__ - Python script to list all Jenkins slaves/executors and their labels.
* __jenkins_plugins_to_puppet.py__ - __DEPRECATED__ in favor of ``jenkins_list_plugins.py``. Python script to query Jenkins for all installed plugins, and generate a block of Puppet code for the [puppet-jenkins](https://github.com/jenkinsci/puppet-jenkins) module.
* __jira2trello.py__ - Python script to update a Trello board with some details from Jira.
* __js2phpdoc.php__ - script to take comments and function prototypes from JS files and make them PHP-ish to be parsed by phpdoc
* __kickRsyslog.php__ - script to restart rsyslog if it appears to have stopped logging
* __lastpass2vault.py__ - Interactive script using [HVAC](https://github.com/ianunruh/hvac) and [lastpass-python](https://github.com/konomae/lastpass-python) to copy your [LastPass](https://www.lastpass.com/) saved passwords to a [HashiCorp Vault](https://www.vaultproject.io/) server.
* __libvirt_csv.py__ - Use libvirt python bindings to print CSV lists of dom0_host,domU_name,ID,state,UUID for all qemu+kvm VMs running on libvirt hosts passed in as arguments
* __LICENSE__ - License for these files - GPLv3 with additional provisions
* __linode_ddns_update.sh__ - simple script to use Linode's HTTP API to update Linode DNS for a dynamic IP
* __linodeDnsToCsv.php__ - Script to pull DNS information for all of your Linode hosted zones, output as CSV
* __linode_list_records.py__ - Simple script to list all records in Linode DNS via API, along with their type, DomainID and ResourceID
* __list_all_aws_resources_skew.py__ - Script using [skew](https://github.com/scopely-devops/skew) to list all AWS resources in your account
* __list_github_org_repos.py__ - List information about an org's repositories using PyGithub (GitHub API library)
* __make_puppet_param_markdown.py__ - # Python script to generate MarkDown docblock fragment for all parameters of a Puppet parameterized class or define. Simple, naive regex matching. Assumes you style your manifests properly.
* __mw2html-auth__ - Produce an HTML version (standalone backup/export) of a MediaWiki site that's behind authentication
* __nagios_log_problem_interval.pl__ - Chart intervals between problem and recovery from Nagios/Icinga logs
* __nethogs2statsd.py__ - Python script to push [nethogs](https://github.com/raboof/nethogs) data to [statsd](https://github.com/etsy/statsd).
* __nethogs2statsd.service__ - Example systemd unit for the above script.
* __nmap-xml-to-table.php__ - Script to transform multiple nmap XML output files (presumably of the same host/port range with different scan options) into a HTML table
* __pacman_compare.py__ - Compare packages in two files containing ``pacman -Q`` output. Ignores versions.
* __pagerduty_list_incidents.py__ - Python script to list and filter PagerDuty incidents.
* __print-cmd.sh__ - Simple script to log environment variables and original command for forced ssh commands
* __print-cmd-wrapper.c__ - C wrapper like cmd-wrapper.c, but just echoes back the command that was called
* __pushover__ - script to wrap execution of a command and send [Pushover](https://pushover.net/) and ``notify-send`` notifications about its duration and exit code.
* __quick_cloudtrail.py__ - Python script to parse AWS CloudTrail log JSON files and search for a user, IP, request ID, etc.
* __README.VCS__ - Note on my CVS/SVN to github migration
* __rebuild_srpm.sh__ - Script to rebuild a SRPM 1:1, useful when you want to build a RHEL/CentOS 6 SRPM on a RHEL/CentOS 5 system that doesn't support newer compression (cpio: MD5 sum mismatch)
* __reconcile_git_repos.py__ - Script to reconcile the state of GitHub repos with local repos (from a private or other git server).
* __reviewboard_reminder_mail.py__ - ReviewBoard - Script to send reminder emails for any open reviews, targeted at a specific group, not updated in more than X days.
* __route53_ddns_update.sh__ - Bash script to update Route53 dynamic DNS
* __rss_to_mail_config.py__ - sample configuration file for rss_to_mail.py*
* __rss_to_mail.py__ - Dead simple python script to find new entries in an RSS feed, and email listing of new entries matching a regex to you. Intended to be run via cron.
* __rsync-wrapper.c__ - setuid/gid wrapper around rsync. Useful to allow members of a specified group to do rsync backups as root over SSH.
* __rsyslogIsHung.php__ - script to investigate rsyslog hangs, write output, and send mail
* __rsyslogPstats.php__ - script to parse rsyslog impstats output and generate a simple report
* __ruby_simplecov_diff.rb__ - Given two Ruby simplecov output directories, show the differences
* __s3sync_inotify.py__ - Python script using boto and pyinotify to watch a directory and sync all files in it to an S3 bucket, and update an index.html file for the bucket.
* __savescreen.py__ - Python script to save screen windows and titles, and write a screenrc to recreate them.
* __scrape_domain.py__ - Python script using requests and BeautifulSoup4 to request all URLs/links/images/CSS/feeds/etc. found on a domain.
* __show_cf_template_params.py__ - Show all parameters and their defaults for a CloudFormation template
* __show_dhcp_fixed_ACKs.pl__ - script to show the most recent DHCP ACKs per IP address for ISC DHCPd, from a log file. Originally written for Vyatta routers that just show the dynamic leases
* __simpleLCDproc.py__ - Simple LCDproc replacement in Python. Uses LCDd server.
* __skeleton.py__ - Skeleton of a one-off Python CLI script, including optparse and logging.
* __smart_check.py__ - Check SMART status of all attached and SMART-enabled disks via pySMART. Report on status. Cache status on disk, and exit non-zero if status of any disks changes.
* __sms_backup_dump.py__ - Dump the XML SMS logs from the [SMS Backup and Restore](https://play.google.com/store/apps/details?id=com.riteshsahu.SMSBackupRestore&hl=en) Android app to HTML
* __sync_git_clones.sh__ - __WIP / Alpha__ - Script to sync all local git clones in a list of paths with origin (and upstream, if configured). If present, uses github_clone_setup.py to setup upstream branches for any GitHub forks, and set refs to check out pull requests from origin and upstream.
* __sync_git_clones.conf__ - config file for sync_git_clones.sh
* __syslogAgeChecker.php__ - script to check timestamp of last syslog line in some files, and send mail if >= X seconds
* __syslogDatesGraph.php__ - script to help visualize time distribution of syslog messages. This is the graph host part.
* __syslogDatesToArray.php__ - script to help visualize time distribution of syslog messages. This is the log host part.
* __syslogDatesToArray-sample.ser__ - example serialized data for syslogDatesGraph.php
* __test_libvirt.py__ - some tests using the libvirt python bindings, for qemu+kvm hosts accessed over SSH
* __timeout__ - shell script to execute a command with a timeout
* __tomtom_tsp.py__ - Script to take a list of [TomTom](http://wow.curseforge.com/addons/tomtom/) WoW addon coordinates and output them in the optimal order.
* __toxit.py__ - Script to parse a tox.ini file, and run the test commands inside an existing virtualenv, against the code already installed there.
* __transmission-alphabetical.py__ - Python script (using the transmission-rpc package) to adjust files in the Transmission bittorrent client so they download in alphabetical order.
* __trello_copy_checklist.py__ - Python script to copy a checklist from one Trello card to another.
* __trello_ensure_card.py__ - Script to ensure that a card with the given title (and optionally other attributes) exists in the specified column of the specified board.
* __trello_push_due_dates.py__ - Script to push all due dates on a Trello board (optionally in one list) back by N days.
* __twitter_find_followed_not_in_list.py__ - Simple script to list anyone whom you're following but isn't in one of your lists.
* __ubiquiti-mac-acl/__ - PHP script and MySQL schema to manage the MAC ACL on Ubiquiti AirOS2 devices.
* __unifi_switch_to_statsd.py__ - Script to pull per-port stats from a UniFi switch and push them to statsd.
* __VipToInternalHosts.pl__ - script to take F5 BigIp VIP address and display the members of the pool it is served by
* __watch_all_my_github_repos.py__ - Python script to ensure you're watching all of your own GitHub repos.
* __watch_circleci.py__ - Python script to watch a CircleCI build, optionally notify via Pushover, and optionally retry failed builds.
* __watch_cloudformation.py__ - Python script to watch a CloudFormation stack's events, and exit when the CF stack update or create finishes. Optional notification via PushOver.
* __watch_elasticsearch.py__ - Python script to watch an ElasticSearch cluster's status and exit/notify when the status changes. Optional notifivation via PushOver.
* __watch_jenkins.py__ - Python script using python-jenkins (https://pypi.python.org/pypi/python-jenkins) to watch a job (specified by URL), and exit 0 on success or 1 on failure. Optional notification via PushOver.
* __watts_up_pro_logger.py__ - Logs data from a Watts Up Pro USB data collector to a file, and optionally to a Graphite instance.
* __whendoiwork.py__ - Script to find all git repositories in a list of local filesystem paths, iterate over all commits in them (in the last N days), and build a histogram of the day of week and hour of day of your commits (using information from your git configuration).
* __where_is_my_pi_zero.py__ - Python script to find in-stock Raspberry Pi Zero
* __wiki-to-deckjs.py__ - simple, awful script to change markdown-like (very restricted markup set) markup to deck.js-ready html
* __wordpress_daily_post.php__ - Script to publish the oldest post with a given status, if no other post has been published in 24 hours. Intended to be run via cron on weekdays
* __xb3_to_graphite.py__ - Pull stats from Comcast XB3 modem web UI and push to graphite.
