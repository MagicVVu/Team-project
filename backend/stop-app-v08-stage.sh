#!/usr/bin/env bash
set -euo pipefail
# Exact resources created by stage-app-v08.sh; no production services or volumes.
for container in magicvvu-app-v08-test-backend magicvvu-app-v08-test-agent magicvvu-app-v08-test-db; do
    if sudo -n docker container inspect "$container" > /dev/null 2>&1; then
        sudo -n docker stop "$container" > /dev/null
    fi
done
for network in magicvvu-app-v08-test-access magicvvu-app-v08-test; do
    if sudo -n docker network inspect "$network" > /dev/null 2>&1; then
        sudo -n docker network rm "$network" > /dev/null
    fi
done
rm -f /srv/magicvvu/releases/app-v08-20261016/.test.env
printf 'ISOLATED APP TEST SERVICES REMOVED\n'
