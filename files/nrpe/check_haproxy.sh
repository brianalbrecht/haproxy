#!/bin/bash
#--------------------------------------------
# This file is managed by Juju
#--------------------------------------------
#
# Copyright 2009,2012 Canonical Ltd.
# Author: Tom Haddon

CRITICAL=0
NOTACTIVE=''
LOGFILE=/var/log/nagios/check_haproxy.log
AUTH=$(grep -r "stats auth" /etc/haproxy | head -1 | awk '{print $4}')

for appserver in $(grep '    server' /etc/haproxy/haproxy.cfg | awk '{print $2'});
do
    output=$(/usr/lib/nagios/plugins/check_http -a ${AUTH} -I 127.0.0.1 -p 10000 --regex="class=\"(active|backup)(2|3).*${appserver}" -e ' 200 OK')
    if [ $? != 0 ]; then
        date >> $LOGFILE
        echo $output >> $LOGFILE
        /usr/lib/nagios/plugins/check_http -a ${AUTH} -I 127.0.0.1 -p 10000 -v | grep $appserver >> $LOGFILE 2>&1
        CRITICAL=1
        NOTACTIVE="${NOTACTIVE} $appserver"
    fi
done

if [ $CRITICAL = 1 ]; then
    echo "CRITICAL:${NOTACTIVE}"
    exit 2
fi

echo "OK: All haproxy instances looking good"
exit 0
