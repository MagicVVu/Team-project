#!/usr/bin/env python3
"""DRAFT P2. P3-only root hourly monitor. No renewal/reload/writes or secret output.
Set DRAFT_ONLY=False only in the reviewed deployed copy. Exit 1 => operator action.
"""
import datetime
import hashlib
import pathlib
import ssl
import socket
import subprocess

DRAFT_ONLY = True
CERT = pathlib.Path('/etc/letsencrypt/live/magicvvu-ip/cert.pem')


def main():
    if DRAFT_ONLY: raise SystemExit('DRAFT ONLY: monitor not activated')
    result = subprocess.run(['openssl', 'x509', '-in', str(CERT), '-noout', '-checkend', '172800'], capture_output=True)
    if result.returncode: raise SystemExit('ALERT: certificate missing, invalid, or expires within 48h')
    pem = CERT.read_text()
    disk = ssl.PEM_cert_to_DER_cert(pem)
    ctx = ssl.create_default_context()
    with socket.create_connection(('127.0.0.1', 443), timeout=8) as sock:
        with ctx.wrap_socket(sock, server_hostname='8.134.172.165') as tls:
            served = tls.getpeercert(binary_form=True)
            details = tls.getpeercert()
    if hashlib.sha256(disk).digest() != hashlib.sha256(served).digest():
        raise SystemExit('ALERT: serving a different certificate than the production lineage')
    for unit in ['snap.certbot.renew.timer', 'magicvvu-cert-monitor.timer']:
        for action in ['is-enabled', 'is-active']:
            if subprocess.run(['systemctl', action, '--quiet', unit]).returncode:
                raise SystemExit('ALERT: expected timer not enabled/active: ' + unit)
    renewal = subprocess.run(['systemctl', 'show', 'snap.certbot.renew.service', '-p', 'Result', '--value'], capture_output=True, text=True)
    if renewal.returncode or renewal.stdout.strip() != 'success':
        raise SystemExit('ALERT: renewal service last result is not success')
    # Certbot can exit 0 when nothing is due; check certificate age independently.
    print('OK: production TLS verified; expires=' + details['notAfter'] + '; timers active')


if __name__ == '__main__': main()
