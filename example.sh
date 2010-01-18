#!/bin/sh

if [ $# -eq 0 ]; then
    # Print config if called with no arguments
    echo 'match = ^!'
else 
    nick=$1
    target=$2
    source=$3
    message=$4

    echo "Hello $source! My name is $nick. We are talking in $target and you said '$message'"
fi
