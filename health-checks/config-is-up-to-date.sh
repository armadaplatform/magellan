#!/usr/bin/env bash

if [[ -z $(find /tmp/domain_to_addresses.json -mmin 1) ]]; then
    echo "File /tmp/domain_to_addresses.json is not up to date. Check magellan logs."
    exit 1
fi
