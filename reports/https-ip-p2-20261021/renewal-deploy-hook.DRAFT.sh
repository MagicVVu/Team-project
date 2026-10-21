#!/bin/bash
# DRAFT P2: future /etc/letsencrypt/renewal-hooks/deploy/50-magicvvu-nginx, root:root 0750.
# P3 reviewer must change DRAFT_ONLY to 0 in the deployed copy after approval.
set -euo pipefail
DRAFT_ONLY=1
if [[ "$DRAFT_ONLY" != 0 ]]; then
    echo 'DRAFT ONLY: no reload performed' >&2
    exit 78
fi
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
expected_lineage=/etc/letsencrypt/live/magicvvu-ip
if [[ "${RENEWED_LINEAGE:-}" != "$expected_lineage" ]]; then
    echo 'Unrelated certificate lineage; no MagicVVu reload'
    exit 0
fi
openssl x509 -in "$expected_lineage/cert.pem" -noout -checkip 8.134.172.165
openssl x509 -in "$expected_lineage/cert.pem" -noout -checkend 86400
openssl verify -CApath /etc/ssl/certs -untrusted "$expected_lineage/chain.pem" "$expected_lineage/cert.pem"
nginx -t
systemctl is-active --quiet nginx
systemctl reload nginx
disk_fp=$(openssl x509 -in "$expected_lineage/cert.pem" -noout -fingerprint -sha256)
for attempt in 1 2 3 4 5; do
    if served_fp=$(timeout 5 openssl s_client -connect 127.0.0.1:443 \
        -verify_ip 8.134.172.165 -verify_return_error -CApath /etc/ssl/certs \
        </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha256); then
        if [[ "$disk_fp" == "$served_fp" ]]; then
            logger -t magicvvu-certbot 'Validated production certificate loaded by nginx'
            exit 0
        fi
    fi
    sleep 1
done
logger -t magicvvu-certbot 'ERROR: reload completed but served certificate verification/fingerprint check failed'
exit 1
