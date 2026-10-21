#!/usr/bin/env python3
"""DRAFT: P3-only configuration backup. NEVER execute against a server in P2.
Requires root and an explicit execution argument. Does not touch database data.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess

PATHS = [
 '/srv/magicvvu/magicvvu-starter/deploy/compose.yaml',
 '/srv/magicvvu/magicvvu-starter/deploy/.env',
 '/etc/nginx', '/etc/letsencrypt', '/var/snap/certbot/common',
 '/etc/logrotate.d/nginx', '/etc/logrotate.d/magicvvu-api',
 '/usr/local/bin/certbot', '/usr/local/sbin/magicvvu-certbot-deploy',
 '/usr/local/sbin/magicvvu-cert-monitor', '/usr/sbin/policy-rc.d',
 '/etc/systemd/system/nginx.service',
 '/etc/systemd/system/snap.certbot.renew.service.d',
 '/etc/systemd/system/snap.certbot.renew.timer.d',
 '/etc/systemd/system/magicvvu-cert-monitor.service',
 '/etc/systemd/system/magicvvu-cert-monitor.timer',
 '/etc/systemd/system/timers.target.wants/magicvvu-cert-monitor.timer',
 '/var/www/magicvvu-acme', '/root/magicvvu-acme-staging',
]
PLANNED = [
 '/etc/nginx/conf.d/00-magicvvu-common.conf',
 '/etc/nginx/sites-available/magicvvu-api',
 '/etc/nginx/sites-enabled/magicvvu-api',
 '/etc/nginx/snippets/magicvvu-route-map.conf',
 '/etc/nginx/snippets/magicvvu-proxy-common.conf',
 '/etc/nginx/snippets/magicvvu-http01-server.conf',
 *PATHS[5:],
]


def command(args):
    p = subprocess.run(args, text=True, capture_output=True, timeout=20)
    return {'rc': p.returncode, 'stdout': p.stdout.strip(), 'stderr': p.stderr.strip()[:300]}


def metadata(name):
    p = pathlib.Path(name)
    if not os.path.lexists(p): return {'path': name, 'exists': False}
    s = p.lstat()
    row = {'path': name, 'exists': True, 'uid': s.st_uid, 'gid': s.st_gid,
           'mode': oct(s.st_mode & 0o7777), 'symlink': p.is_symlink()}
    if p.is_symlink(): row['link_target'] = os.readlink(p)
    elif p.is_file(): row['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-p3-authorized', action='store_true')
    parser.add_argument('--label', required=True, help='before-install / after-install / before-https / before-renewal')
    args = parser.parse_args()
    if not args.execute_p3_authorized:
        parser.error('DRAFT: execution disabled. Requires separate P3 authorization.')
    if os.name != 'posix' or os.geteuid() != 0: raise SystemExit('Root on approved Ubuntu host required')
    if not re.fullmatch('[a-z0-9-]{1,40}', args.label): raise SystemExit('Invalid label')
    # Refuse to silently follow a substituted backup root.
    base = pathlib.Path('/root/magicvvu-https-backups')
    if base.is_symlink(): raise SystemExit('Backup root must not be a symlink')
    base.mkdir(mode=0o700, exist_ok=True)
    if base.resolve() != base or base.stat().st_uid != 0 or base.stat().st_mode & 0o077:
        raise SystemExit('Backup root must be root-owned mode 0700')
    os.umask(0o077)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest = base / (stamp + '-' + args.label)
    dest.mkdir(mode=0o700)
    (dest / 'files').mkdir(mode=0o700)
    before = {'utc': stamp, 'label': args.label, 'paths': [metadata(p) for p in PATHS],
              'planned_paths': [metadata(p) for p in PLANNED]}
    for name in PATHS:
        if os.path.lexists(name):
            # cp -a keeps modes, ownership, timestamps and symbolic links.
            subprocess.run(['cp', '-a', '--parents', '--', name, str(dest / 'files')], check=True)
    before['services'] = {s: command(['systemctl', 'show', s, '-p', 'ActiveState', '-p', 'SubState', '-p', 'UnitFileState']) for s in ['nginx', 'docker', 'snap.certbot.renew.timer', 'snap.certbot.renew.service', 'magicvvu-cert-monitor.timer']}
    before['packages'] = command(['dpkg-query', '-W', '-f=${Package}\t${Version}\t${Status}\n', 'nginx', 'certbot', 'snapd'])
    before['listeners'] = command(['ss', '-lntp'])
    before['containers'] = []
    for service in ['backend', 'agent', 'db']:
        name = 'magicvvu-starter-' + service + '-1'
        raw = command(['docker', 'inspect', name])
        if raw['rc'] != 0: raise SystemExit('Container baseline unavailable: ' + name)
        c = json.loads(raw['stdout'])[0]
        before['containers'].append({'name': name, 'id': c['Id'], 'image': c['Image'],
            'health': c['State'].get('Health', {}).get('Status'), 'ports': c['HostConfig']['PortBindings'],
            'restart': c['HostConfig']['RestartPolicy']})
    (dest / 'before.json').write_text(json.dumps(before, indent=2)+'\n')
    (dest / 'created-files.txt').write_text('# Append only paths actually created by this deployment, one absolute path per line.\n')
    (dest / 'changes.jsonl').write_text('')
    (dest / 'COMPLETE').write_text('Configuration-only backup complete; database NOT backed up.\n')
    print(str(dest))  # No env, token, key contents, or raw docker inspect output.


if __name__ == '__main__': main()
