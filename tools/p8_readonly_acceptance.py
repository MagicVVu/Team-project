"""Read-only P8 production snapshot. Never logs in, uses tokens or reads user data.

Run from a non-Tailnet network: python tools/p8_readonly_acceptance.py
DNS samples are bounded (default 3); --ssh uses an existing OpenSSH alias.
This reports observations, not an overall PASS or a deployment authorization.
"""
import argparse
import json
import subprocess
import urllib.error
import urllib.request

ORIGIN = "https://iz7xvftxzwe1mwbso1ovyyz.tail0abb88.ts.net"
ZERO = "00000000-0000-0000-0000-000000000000"
PATHS = ["/api/v1/health", "/openapi.json", "/docs", "/redoc",
         "/internal/v1/inventory/search", "/api/v1/users/me",
         f"/api/v1/households/{ZERO}/inventory-items"]


def public_checks():
    # Explicitly disable environment proxies; HTTPS uses the system SSL context.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    results = []
    for path in PATHS:
        try:
            with opener.open(ORIGIN + path, timeout=15) as response:
                status = response.status
                # Read only the public health body; do not read any other result.
                health = json.load(response) if path == "/api/v1/health" else None
        except urllib.error.HTTPError as error:
            status, health = error.code, None
            error.close()
        except (OSError, ValueError):
            status, health = "network_or_tls_error", None
        item = {"path": path, "status": status}
        if health is not None:
            item["healthy"] = health.get("status") == "ok"
        results.append(item)
    return results


REMOTE = r'''
import json,subprocess,urllib.request,time
samples = __SAMPLES__
containers=['magicvvu-starter-backend-1','magicvvu-starter-agent-1','magicvvu-starter-db-1']
result={'read_only':True,'production_login_tested':False,'private_data_accessed':False}
try:
 with urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=10) as r:
  result['local_health']={'http':r.status,'healthy':json.load(r).get('status')=='ok'}
except (OSError,ValueError):result['local_health']={'error':True}
rows=[]
for name in containers:
 p=subprocess.run(['sudo','-n','docker','inspect','--format',
 '{{.Name}}|{{.State.Health.Status}}|{{.State.StartedAt}}|{{.RestartCount}}',name],capture_output=True,text=True,timeout=10)
 rows.append({'name':name,'state':p.stdout.strip() if p.returncode==0 else 'inspection_failed'})
result['containers']=rows
p=subprocess.run(['tailscale','funnel','status','--json'],capture_output=True,text=True,timeout=10)
result['funnel_status_readable']=p.returncode==0
for service in ['tailscaled','docker','systemd-resolved']:
 p=subprocess.run(['systemctl','is-active',service],capture_output=True,text=True,timeout=10)
 result[service]=p.stdout.strip()
dns=[]
for server in ['100.100.2.136','100.100.2.138','223.5.5.5','119.29.29.29']:
 for protocol in ['udp','tcp']:
  for sample in range(samples):
   args=['dig','@'+server,'acme-v02.api.letsencrypt.org','A','+time=2','+tries=1','+noall','+answer','+stats']
   if protocol=='tcp':args+=['+tcp']
   start=time.monotonic()
   p=subprocess.run(args,capture_output=True,text=True,timeout=5)
   dns.append({'server':server,'protocol':protocol,'sample':sample+1,
    'resolved':p.returncode==0 and any(len(line.split())>=5 and line.split()[3]=='A' for line in p.stdout.splitlines()),
    'elapsed_ms':round((time.monotonic()-start)*1000)})
result['dns']=dns
print(json.dumps(result,sort_keys=True))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh", default="magicvvu")
    parser.add_argument("--dns-samples", type=int, default=3, choices=range(1, 11))
    parser.add_argument("--public-only", action="store_true")
    args = parser.parse_args()
    result = {"public_observations": public_checks(),
              "network_must_be_confirmed_non_tailnet_by_operator": True,
              "overall_pass": False}
    if not args.public_only:
        process = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
                                  args.ssh, "python3 -"],
                                 input=REMOTE.replace("__SAMPLES__", str(args.dns_samples)),
                                 capture_output=True, text=True, timeout=60 + 40*args.dns_samples)
        try:
            result["server"] = json.loads(process.stdout) if process.returncode == 0 else {"ssh_failed": True}
        except ValueError:
            result["server"] = {"unreadable_result": True}
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
