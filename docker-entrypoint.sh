#!/bin/bash
set -e

if [ -f /run/secrets/elementsd_user ] && [ -f /run/secrets/elementsd_pass ]; then
    creds=("--rpcuser=$(cat /run/secrets/elementsd_user)" "--rpcpassword=$(cat /run/secrets/elementsd_pass)")
elif [ -f /run/secrets/elementsd_pass ] && [ -f /run/secrets/reissuance_priv_key ]; then
    creds=("--rpcpassword=$(cat /run/secrets/elementsd_pass)" "--reissuanceprivkey=$(cat /run/secrets/reissuance_priv_key)")
elif [ -f /run/secrets/elementsd_pass ]; then
    creds=("--rpcpassword=$(cat /run/secrets/elementsd_pass)")
fi

command="$@ ${creds[@]}"

bash -c "${command}"
