#!/bin/sh

if [ $# -eq 0 ]; then
    echo match = ^\!
    exit
fi

nick=$1
channel=$2
source=$3
message=$4

echo "Hello $source! My name is $nick. We are talking in $channel and you said '$message'"
