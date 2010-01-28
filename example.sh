#!/bin/sh

if [ $# -eq 1 -a $1 = "--config" ]; then
    # Print config if called with --config
    echo 'match = ^!'
else
    if [ $# -eq 4 ]; then
        nick=$1
        target=$2
        source=$3
        message=$4

        echo "Hello $source! My name is $nick. We are talking in $target and you said '$message'"
    else
        echo "Usage: $0 nick target source \"message\""
    fi
fi
