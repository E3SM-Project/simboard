#!/bin/bash

if [[ $# -gt 0 ]]; then
    YMD=$1
else
    TODAY=`date -u +%Y%m%d`
    YMD=`date -d "$TODAY - 1 day" +%Y%m%d`
fi

target="Collection_Report-$YMD"

# to distinguish activity collected from the staging runs and the daily archive run,
# we collect these separately into tmp lists, and prepend "staging" and "archive" to
# the output lines, accordingly.

tmplist="tmp-$YMD"
logfiles=`ls raw_logs | grep "staging-chrysalis-$YMD"`

for logfile in $logfiles; do
    cat raw_logs/$logfile | grep case_collection_summary | grep -v "accepted=0" | cut -c1-24,107- | cut -f1-4 -d' ' >> $tmplist
    mv raw_logs/$logfile history_logs
done
prev_IFS=$IFS
IFS=$'\n'
for aline in `cat $tmplist`; do
    echo "staging: $aline" >> $target
done
IFS=$prev_IFS

rm -f $tmplist

# identify the proper corresponding archive daily log here


raw_daily_archive_log=`ls raw_logs/ | grep archive | grep $YMD`
if [[ -f raw_logs/$raw_daily_archive_log ]]; then
    cat raw_logs/$raw_daily_archive_log | grep case_collection_summary | grep -v "accepted=0" | cut -c1-24,107- | cut -f1-4 -d' ' >> $tmplist
    mv raw_logs/$raw_daily_archive_log history_logs
fi
IFS=$'\n'
for aline in `cat $tmplist`; do
    echo "archive: $aline" >> $target
done
IFS=$prev_IFS

rm -f $tmplist

if getent group simboard >/dev/null 2>&1; then
    chgrp simboard $target || {
        printf '%s\n' "WARNING: Unable to change group of $target to simboard" >&2
    }
fi


