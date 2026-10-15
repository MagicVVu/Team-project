"""Local operator helper: allowlisted code sync, never a directory/package upload.

Existing remote files must match the previous owned manifest or the new content.
No service restart, chmod, deletion, deployment or credential upload is performed.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import subprocess

from .source_manifest import ROOT, manifest

REMOTE_SCRIPT = '''
import hashlib,json,pathlib,sys
payload=json.load(sys.stdin)
root=pathlib.Path.home()/'workspace'/'agent'
if root.is_symlink() or not root.is_dir(): raise SystemExit('AI workspace is missing or symlinked')
root=root.resolve()
files={}
for rel,expected in payload['files'].items():
    path=root/rel
    if path.is_symlink() or not path.resolve().is_relative_to(root): raise SystemExit('Unsafe runtime path')
    for parent in path.parents:
        if parent==root: break
        if parent.is_symlink(): raise SystemExit('Symlinked runtime parent')
    actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    previous=payload['previous'].get(rel)
    if actual is not None and actual not in {expected,previous}: raise SystemExit('Unowned remote modification: '+rel)
    files[rel]=actual
if payload['prepare']:
    for rel in payload['files']: (root/rel).parent.mkdir(parents=True,exist_ok=True)
print(json.dumps({'root':str(root),'files':files}))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--host", default="magicvvu_ai@8.134.172.165")
    args = parser.parse_args()
    if args.host.startswith("-") or any(c.isspace() for c in args.host): parser.error("invalid host")
    current = manifest()
    previous = json.loads(args.previous.read_text(encoding="utf-8-sig"))["files"]
    options = ["-i", str(args.identity), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={args.known_hosts.as_posix()}", "-o", "ConnectTimeout=10"]

    def inspect(prepare):
        payload = {"files":current["files"], "previous":previous, "prepare":prepare}
        # JSON payload is data on stdin to Python, never shell-interpolated.
        script = REMOTE_SCRIPT.replace("payload=json.load(sys.stdin)", "payload=json.loads("+repr(json.dumps(payload))+")")
        proc = subprocess.run(["ssh", *options, args.host, "python3 -"], input=script.encode(), capture_output=True, check=True)
        return json.loads(proc.stdout)

    before = inspect(True)
    changed = [rel for rel, digest in current["files"].items() if before["files"][rel] != digest]
    groups = defaultdict(list)
    for rel in changed: groups[str(Path(rel).parent).replace("\\", "/")].append(rel)
    for parent, paths in groups.items():
        destination = before["root"] + ("/"+parent if parent != "." else "") + "/"
        subprocess.run(["scp", *options, *[str(ROOT/rel) for rel in paths], f"{args.host}:{destination}"], check=True)
    after = inspect(False)
    if after["files"] != current["files"]: raise RuntimeError("Remote hash verification failed")
    report = {"kind":current["kind"], "files":current["files"], "changed":changed,
        "remote_root":after["root"], "hashes_verified":True,
        "documents_included":False, "credentials_included":False, "services_restarted":False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"changed_files":len(changed), "verified_files":len(current["files"]), "remote_root":after["root"]}))


if __name__ == "__main__":
    main()
