"""P1 only: run over SSH stdin as root; never print env, tokens or private keys."""
import ast
import datetime
import glob
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import urllib.parse

OUT = {"phase": "P1", "read_only": True,
       "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}


def run(args, timeout=15):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "stdout": p.stdout.strip(),
                "stderr": p.stderr.strip()[:1200]}
    except subprocess.TimeoutExpired:
        return {"timeout": True, "argv0": args[0]}
    except OSError as e:
        return {"error": type(e).__name__, "argv0": args[0]}


def meta(name, digest=False):
    p = pathlib.Path(name)
    if not p.exists() and not p.is_symlink():
        return {"path": name, "exists": False}
    s = p.stat()
    result = {"path": name, "exists": True, "mode": oct(s.st_mode & 0o7777),
              "uid": s.st_uid, "gid": s.st_gid, "size": s.st_size,
              "symlink": p.is_symlink()}
    if p.is_symlink():
        result["target"] = str(p.resolve())
    if digest and p.is_file():
        result["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


OUT["host"] = {"hostname": run(["hostname"]),
               "os": pathlib.Path('/etc/os-release').read_text(),
               "uptime": run(["uptime"]), "memory": run(["free", "-m"]),
               "disk": run(["df", "-h", "/", "/srv", "/var"]),
               "inodes": run(["df", "-i", "/", "/srv", "/var"]),
               "time_sync": run(["timedatectl", "show", "-p", "NTPSynchronized", "-p", "Timezone"])}
OUT["listeners"] = run(["ss", "-lntup"])
OUT["services"] = {s: run(["systemctl", "show", s, "-p", "ActiveState", "-p", "SubState", "-p", "UnitFileState"])
                   for s in ["docker", "nginx", "snapd", "snapd.socket"]}
OUT["packages"] = run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n", "nginx", "nginx-common", "certbot", "snapd", "ca-certificates", "python3-venv"])
OUT["executables"] = {n: shutil.which(n) for n in ["nginx", "certbot", "snap", "openssl", "curl", "python3", "apt-cache"]}
OUT["nginx_version"] = run(["nginx", "-v"])
OUT["certbot_version"] = run(["certbot", "--version"])
OUT["snap_list"] = run(["snap", "list"], 12)
OUT["snap_version"] = run(["snap", "version"], 12)
OUT["apt_candidates"] = run(["apt-cache", "policy", "nginx", "certbot", "snapd"], 12)

config_files = sorted(set(glob.glob('/etc/nginx/**/*', recursive=True)))
OUT["nginx_config_metadata"] = [meta(p, True) for p in config_files if pathlib.Path(p).is_file()]
OUT["nginx_directive_summary"] = []
for name in config_files:
    p = pathlib.Path(name)
    if not p.is_file() or p.suffix not in ('.conf', ''):
        continue
    for line in p.read_text(errors='replace').splitlines():
        m = re.match(r'\s*(listen|server_name|ssl_certificate|ssl_certificate_key|proxy_pass|include|access_log|error_log)\s+([^;]+);', line)
        if m:
            directive, value = m.groups()
            if directive == 'proxy_pass':
                u = urllib.parse.urlsplit(value)
                value = f'{u.scheme}://{u.hostname}:{u.port}' if u.hostname else '[dynamic target]'
            OUT['nginx_directive_summary'].append({"file": name, "directive": directive, "value": value})

OUT["config_baseline"] = [meta(p, True) for p in [
    '/srv/magicvvu/magicvvu-starter/deploy/compose.yaml',
    '/srv/magicvvu/magicvvu-starter/deploy/.env',
    '/etc/nginx/nginx.conf', '/etc/letsencrypt/cli.ini']]

ids = run(["docker", "ps", "-aq"])
OUT["docker_version"] = run(["docker", "--version"])
OUT["compose_version"] = run(["docker", "compose", "version"])
OUT["containers"] = []
if ids.get('rc') == 0 and ids['stdout']:
    inspected = run(["docker", "inspect", *ids['stdout'].split()])
    if inspected.get('rc') == 0:
        for c in json.loads(inspected['stdout']):
            OUT['containers'].append({
                "name": c['Name'].lstrip('/'), "image": c['Config']['Image'],
                "status": c['State']['Status'], "health": c['State'].get('Health', {}).get('Status'),
                "started": c['State'].get('StartedAt'), "restarts": c.get('RestartCount'),
                "restart_policy": c['HostConfig']['RestartPolicy'],
                "bindings": c['HostConfig']['PortBindings'],
                "runtime_ports": c['NetworkSettings']['Ports'],
                "networks": list(c['NetworkSettings']['Networks']),
                "compose_files": (c['Config'].get('Labels') or {}).get('com.docker.compose.project.config_files'),
                "mounts": [{k: m.get(k) for k in ['Type', 'Name', 'Source', 'Destination', 'RW']} for m in c['Mounts']]})
    else:
        OUT['docker_inspect_error'] = {k: v for k, v in inspected.items() if k != 'stdout'}
OUT["docker_stats"] = run(["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.PIDs}}"])
OUT["docker_disk"] = run(["docker", "system", "df"])
OUT["compose_projects"] = run(["docker", "compose", "ls", "--format", "json"])
compose = run(["docker", "compose", "--env-file", "/srv/magicvvu/magicvvu-starter/deploy/.env", "-f", "/srv/magicvvu/magicvvu-starter/deploy/compose.yaml", "config", "--format", "json"])
if compose.get('rc') == 0:
    parsed = json.loads(compose['stdout'])
    OUT['compose_services'] = {k: {x: v.get(x) for x in ['image', 'ports', 'expose', 'restart', 'networks', 'depends_on']} for k, v in parsed.get('services', {}).items()}
else:
    OUT['compose_parse'] = {"rc": compose.get('rc'), "timeout": compose.get('timeout'), "details": "suppressed to avoid interpolated secrets"}

# Inspect the deployed functions BEFORE deciding whether to call them.
source = run(["docker", "exec", "magicvvu-starter-backend-1", "python", "-c", "from pathlib import Path; print(Path('app/main.py').read_text())"])
OUT['health_function_audit'] = {}
if source.get('rc') == 0:
    tree = ast.parse(source['stdout'])
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ['health_check', 'readiness_check']:
            OUT['health_function_audit'][node.name] = ast.get_source_segment(source['stdout'], node)
else:
    OUT['health_function_audit']['unavailable'] = True

OUT['certificates'] = []
for name in sorted(set(glob.glob('/etc/letsencrypt/live/*/cert.pem') + glob.glob('/etc/nginx/**/*.crt', recursive=True))):
    OUT['certificates'].append({"metadata": meta(name), "public_details": run(['openssl', 'x509', '-in', name, '-noout', '-dates', '-issuer', '-ext', 'subjectAltName'])})
OUT['certificate_directories'] = [meta(p) for p in ['/etc/letsencrypt', '/etc/letsencrypt/live', '/etc/letsencrypt/renewal', '/etc/letsencrypt/renewal-hooks/deploy', '/var/snap/certbot/common', '/root/.acme.sh']]
OUT['renewal_files'] = [meta(p, True) for p in glob.glob('/etc/letsencrypt/renewal/*.conf') + glob.glob('/etc/letsencrypt/renewal-hooks/**/*', recursive=True) if pathlib.Path(p).is_file()]
OUT['timers'] = run(['systemctl', 'list-timers', '--all', '--no-pager'])
units = run(['systemctl', 'list-unit-files', '--no-pager', '--no-legend'])
OUT['certificate_units'] = [line for line in units.get('stdout', '').splitlines() if re.search('certbot|acme|letsencrypt|lego', line, re.I)]
OUT['certificate_schedules'] = []
schedule_files = glob.glob('/etc/cron*/*') + ['/etc/crontab'] + glob.glob('/var/spool/cron/crontabs/*') + glob.glob('/etc/systemd/system/**/*', recursive=True)
for name in schedule_files:
    p = pathlib.Path(name)
    if p.is_file() and p.stat().st_size < 150000:
        text = p.read_text(errors='replace')
        terms = sorted(set(re.findall(r'certbot|letsencrypt|acme\.sh|lego', text, re.I)))
        if terms:
            OUT['certificate_schedules'].append({"metadata": meta(name, True), "tools_found": terms})

OUT['ufw'] = run(['ufw', 'status', 'verbose'])
fw = run(['iptables-save'])
OUT['iptables_policies'] = [line for line in fw.get('stdout', '').splitlines() if line.startswith(':')]
OUT['iptables_port_rules'] = [re.sub(r' --comment ("[^"]*"|\S+)', ' --comment [omitted]', line) for line in fw.get('stdout', '').splitlines() if re.search(r'--dports? (22|80|443|8000|5432|8767)(\s|,|$)', line)]
OUT['ipv6_policies'] = run(['ip6tables', '-S', 'INPUT'])
OUT['routes'] = run(['ip', 'route', 'show', 'default'])
OUT['proxy_env_present'] = [k for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'] if os.environ.get(k)]
OUT['network_checks'] = []
for url in ['https://acme-staging-v02.api.letsencrypt.org/directory', 'https://acme-v02.api.letsencrypt.org/directory', 'https://api.snapcraft.io/', 'https://archive.ubuntu.com/ubuntu/']:
    host = urllib.parse.urlsplit(url).hostname
    result = {"url": url, "dns": run(['getent', 'ahostsv4', host], 8)}
    probe = run(['curl', '--noproxy', '*', '--proto', '=https', '--connect-timeout', '5', '--max-time', '10', '-sS', '-o', '/dev/null', '-w', 'http=%{http_code} peer=%{remote_ip} tls_verify=%{ssl_verify_result}', url], 12)
    result['https_probe'] = probe
    OUT['network_checks'].append(result)
OUT['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
print(json.dumps(OUT, ensure_ascii=False, indent=2))
