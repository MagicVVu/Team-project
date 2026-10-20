"""Approved P8.1 one-shot run; execute via SSH sudo python3 stdin.

No permanent server files. The only mutations are the four reviewed INPUT
exceptions and their exact removal in finally. Future runs need fresh approval.
"""
import hashlib
import json
import re
import signal
import subprocess
import time
import urllib.request

PREFIX = "magicvvu-p81-20261020T0930"
LOCAL = "172.19.29.17"
SERVERS = ["100.100.2.136", "100.100.2.138"]
CONTAINERS = ["magicvvu-starter-backend-1", "magicvvu-starter-agent-1", "magicvvu-starter-db-1"]
added = []


def log(event, **fields):
    try:
        print(json.dumps({"event": event, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **fields}), flush=True)
    except BrokenPipeError:
        pass  # A lost SSH output stream must never prevent finally cleanup.


def run(cmd, *, check=True, timeout=15):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError("command failed: " + repr(cmd) + " " + p.stderr)
    return p


def spec(server, protocol):
    return ["-i", "eth0", "-s", server + "/32", "-d", LOCAL + "/32", "-p", protocol,
            "--sport", "53", "-m", "conntrack", "--ctstate", "ESTABLISHED", "-m", "comment",
            "--comment", PREFIX + "-" + server.rsplit(".", 1)[1] + "-" + protocol, "-j", "ACCEPT"]


def structure():
    text = run(["iptables-nft-save"]).stdout
    # Discard timestamps and live counter values, not policies or rule content.
    return "\n".join(re.sub(r"\[\d+:\d+\]", "[COUNTERS]", line)
                     for line in text.splitlines() if not line.startswith("#"))


def dns(server, protocol, name, phase, sample):
    cmd = ["dig", "@" + server, name, "A", "+time=2", "+tries=1", "+noall", "+answer", "+stats", "+comments"]
    if protocol == "tcp":
        cmd += ["+tcp"]
    start = time.monotonic()
    p = run(cmd, check=False, timeout=6)
    records = [line.split() for line in p.stdout.splitlines() if line and not line.startswith(";")]
    addresses = [row[4] for row in records if len(row) >= 5 and row[3] == "A"]
    ok = p.returncode == 0 and "status: NOERROR" in p.stdout and bool(addresses)
    log("dns", phase=phase, server=server, protocol=protocol, name=name, sample=sample,
        ok=ok, exit=p.returncode, elapsed_ms=round(1000 * (time.monotonic() - start)),
        addresses=addresses, output=p.stdout, error=p.stderr)
    return ok


def counters(phase):
    text = run(["iptables-nft", "-nvxL", "INPUT", "--line-numbers"]).stdout
    log("counters", phase=phase, input=text,
        ts_input=run(["iptables-nft", "-nvxL", "ts-input", "--line-numbers"]).stdout)
    return text


def health(phase):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:8000/api/v1/health", timeout=10) as response:
        assert response.status == 200 and json.load(response)["status"] == "ok"
    services = run(["systemctl", "is-active", "ssh", "docker", "tailscaled", "systemd-resolved"]).stdout
    assert services.splitlines() == ["active"] * 4, services
    docker = run(["docker", "inspect", "--format",
                  "{{.Name}}|{{.State.Health.Status}}|{{.State.StartedAt}}|{{.RestartCount}}", *CONTAINERS]).stdout
    assert len(docker.splitlines()) == 3 and all("|healthy|" in line for line in docker.splitlines())
    peers = []
    for container, url in [(CONTAINERS[0], "http://agent:8767/health"),
                           (CONTAINERS[1], "http://backend:8000/api/v1/health")]:
        code = ("import urllib.request,json; r=urllib.request.urlopen(" + repr(url)
                + ",timeout=10); b=json.load(r); assert r.status==200 and b.get('status')=='ok'; print('health=200 ok')")
        result = run(["docker", "exec", container, "python", "-c", code]).stdout.strip()
        peers.append({"container": container, "health": result})
    log("health", phase=phase, services=services, containers=docker, peers=peers)
    return docker


def interrupted(signum, _):
    raise RuntimeError("interrupted by signal " + str(signum))


signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGHUP, interrupted)
failure = None
rollback_errors = []
baseline = None
try:
    assert "nf_tables" in run(["iptables-nft", "--version"]).stdout
    assert run(["readlink", "-f", "/usr/sbin/iptables"]).stdout.strip().endswith("xtables-nft-multi")
    addresses = json.loads(run(["ip", "-j", "-4", "addr", "show", "dev", "eth0"]).stdout)
    assert LOCAL in [a["local"] for link in addresses for a in link["addr_info"]]
    original_input = run(["iptables-nft", "-S", "INPUT"]).stdout
    assert original_input == "-P INPUT ACCEPT\n-A INPUT -j ts-input\n", original_input
    original_ts = run(["iptables-nft", "-S", "ts-input"]).stdout
    assert "-A ts-input -s 100.64.0.0/10 ! -i tailscale0 -j DROP" in original_ts
    assert PREFIX not in run(["iptables-nft-save"]).stdout
    assert run(["iptables-legacy-save"]).stdout.strip() == ""
    baseline_dns = run(["resolvectl", "dns", "eth0"]).stdout
    assert baseline_dns.strip() == "Link 2 (eth0): 1.1.1.1", baseline_dns
    baseline_funnel = json.loads(run(["tailscale", "funnel", "status", "--json"]).stdout)
    baseline = structure()
    original_docker = health("before")
    log("baseline", rules=baseline, dns=baseline_dns, funnel=baseline_funnel,
        nft=run(["nft", "-a", "list", "chain", "ip", "filter", "INPUT"]).stdout)
    counters("before")
    for server in SERVERS:
        for protocol in ["udp", "tcp"]:
            if dns(server, protocol, "acme-v02.api.letsencrypt.org", "before", 1):
                raise RuntimeError("Baseline DNS unexpectedly succeeds; stop for review")
    assert structure() == baseline, "Other firewall structure changed before insertion"
    for server in SERVERS:
        for protocol in ["udp", "tcp"]:
            rule = spec(server, protocol)
            check = run(["iptables-nft", "-w", "5", "-C", "INPUT", *rule], check=False)
            assert check.returncode == 1, "Unexpected duplicate/check result"
            # Record intent before execution so an interruption after kernel commit
            # cannot leave a successfully inserted rule outside the cleanup list.
            added.append(rule)
            p = run(["iptables-nft", "-w", "5", "-I", "INPUT", "1", *rule])
            assert run(["iptables-nft", "-w", "5", "-C", "INPUT", *rule]).returncode == 0
            log("inserted", rule=rule)
    active_input = run(["iptables-nft", "-S", "INPUT"]).stdout
    lines = active_input.splitlines()
    assert len(lines) == 6 and all(PREFIX in line for line in lines[1:5]) and lines[5] == "-A INPUT -j ts-input"
    assert run(["iptables-nft", "-S", "ts-input"]).stdout == original_ts
    log("active_rules", input=active_input,
        nft=run(["nft", "-a", "list", "chain", "ip", "filter", "INPUT"]).stdout)
    for server in SERVERS:
        for name in ["acme-v02.api.letsencrypt.org", "api.deepseek.com"]:
            for protocol in ["udp", "tcp"]:
                for sample in range(1, 4):
                    if not dns(server, protocol, name, "temporary_rules", sample):
                        raise RuntimeError("DNS check failed; rollback without widening rules")
                    time.sleep(0.25)
    active_counters = counters("temporary_rules")
    for server in SERVERS:
        for protocol in ["udp", "tcp"]:
            tag = PREFIX + "-" + server.rsplit(".", 1)[1] + "-" + protocol
            matched = [line for line in active_counters.splitlines() if tag in line]
            assert len(matched) == 1 and int(matched[0].split()[1]) > 0, "No positive match counter for " + tag
    assert health("temporary_rules") == original_docker, "Container restart/state changed"
    assert json.loads(run(["tailscale", "funnel", "status", "--json"]).stdout) == baseline_funnel
    assert run(["resolvectl", "dns", "eth0"]).stdout == baseline_dns
    log("public_check_window", seconds=30, temporary_rules_active=True,
        purpose="independent public HTTPS and new SSH checks from operator")
    time.sleep(30)
except BaseException as error:
    failure = {"type": type(error).__name__, "detail": str(error)}
    log("failure", **failure)
finally:
    # Do not let a second hangup interrupt exact rollback.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    for rule in reversed(added):
        try:
            check = run(["iptables-nft", "-w", "5", "-C", "INPUT", *rule], check=False)
            if check.returncode == 0:
                run(["iptables-nft", "-w", "5", "-D", "INPUT", *rule])
                log("removed", rule=rule)
            elif check.returncode != 1:
                raise RuntimeError("Cannot verify presence before exact rollback")
            assert run(["iptables-nft", "-w", "5", "-C", "INPUT", *rule], check=False).returncode == 1
        except BaseException as error:
            rollback_errors.append({"rule": rule, "type": type(error).__name__, "detail": str(error)})
    log("rollback", errors=rollback_errors, inserted_or_attempted=len(added),
        remaining_marker=PREFIX in run(["iptables-nft-save"]).stdout)

# The script must not silently claim success if rollback/health cannot be proved.
assert not rollback_errors, "Rollback requires immediate operator recovery"
assert PREFIX not in run(["iptables-nft-save"]).stdout
if baseline is not None:
    assert structure() == baseline, "Firewall structure differs after exact rollback"
    assert health("after_rollback") == original_docker
    assert run(["resolvectl", "dns", "eth0"]).stdout == baseline_dns
    assert json.loads(run(["tailscale", "funnel", "status", "--json"]).stdout) == baseline_funnel
    counters("after_rollback")
    for server in SERVERS:
        for protocol in ["udp", "tcp"]:
            assert not dns(server, protocol, "acme-v02.api.letsencrypt.org", "after_rollback", 1), "Unexpected baseline change"
log("complete", temporary_validation_passed=failure is None, rules_removed=True,
    persistent_changes=False, failure=failure)
raise SystemExit(0 if failure is None else 1)
