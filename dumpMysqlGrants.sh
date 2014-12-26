#!/bin/bash
#
# I got this from Richard Bronosky's (<http://blog.bronosky.com/>)
# answer <http://serverfault.com/a/13050> to this thread:
# <http://serverfault.com/questions/8860/how-can-i-export-the-privileges-from-mysql-and-then-import-to-a-new-server>
# Many thanks to him.
#
# The most up-to-date version of this script can be found at:
# <https://github.com/jantman/misc-scripts/blob/master/dumpMysqlGrants.sh>
#

mygrants()
{
read -p "PASSWORD: " PASSWD
mysql -p$PASSWD -B -N $@ -e "SELECT DISTINCT CONCAT(
'SHOW GRANTS FOR ''', user, '''@''', host, ''';'
) AS query FROM mysql.user WHERE user NOT IN ('root','phpmyadmin','debian-sys-maint')"  | \
mysql -p$PASSWD $@ | \
sed 's/\(GRANT .*\)/\1;/;s/^\(Grants for .*\)/## \1 ##/;/##/{x;p;x;}'
}

mygrants
