#!/bin/sh
# Filter the original host port before Docker DNAT, including during boot.
# Never change SSH, INPUT policy or other projects.
set -eu
iptables -t raw -N MAGICVVU-TLS 2>/dev/null || true
# iptables-restore commits the replacement chain atomically.
rules=$(mktemp)
trap 'rm -f "$rules"' EXIT
printf '*raw\n-F MAGICVVU-TLS\n' > "$rules"
while IFS= read -r source; do
    case "$source" in ''|'#'*) continue ;; esac
    printf -- '-A MAGICVVU-TLS -s %s -j RETURN\n' "$source" >> "$rules"
done < /etc/magicvvu/ip-direct/allowed-sources.txt
printf -- '-A MAGICVVU-TLS -j DROP\nCOMMIT\n' >> "$rules"
iptables-restore --noflush < "$rules"
iptables -t raw -C PREROUTING -i eth0 -p tcp --dport 8000 -j MAGICVVU-TLS 2>/dev/null ||
    iptables -t raw -I PREROUTING 1 -i eth0 -p tcp --dport 8000 -j MAGICVVU-TLS
