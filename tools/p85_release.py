"""P8.5 AI-only operator. No backend sources/configuration or Git mutation."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT/'reports/p85-memory'
sys.path.insert(0, str(ROOT/'agent'))
from integration.source_manifest import manifest


def sources():
    paths = set(manifest()['files'])
    paths.update(p.relative_to(ROOT/'agent').as_posix() for p in (ROOT/'agent/conversation/p85').glob('*.py'))
    values = {p:(ROOT/'agent'/p).read_bytes() for p in sorted(paths)}
    for p, raw in values.items():
        if p.endswith('.py'): ast.parse(raw.decode('utf-8-sig'), filename=p)
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['audit','baseline-check','prepare','candidate-check','switch','verify','model-check','capture'])
    args = parser.parse_args()
    REPORTS.mkdir(parents=True, exist_ok=True)
    values = sources()
    hashes = {p:hashlib.sha256(raw).hexdigest() for p,raw in values.items()}
    payload = {'files':{p:base64.b64encode(raw).decode() for p,raw in values.items()}, 'hashes':hashes}
    if args.stage != 'audit':
        payload['audit'] = json.loads((REPORTS/'p85-production-audit.json').read_text(encoding='utf-8'))
        assert payload['audit']['local_hashes'] == hashes, 'Local sources changed after audit'
    code = 'PAYLOAD='+repr(payload)+'\nSTAGE='+repr(args.stage)+'\n'+(ROOT/'tools/p85_release_remote.py').read_text(encoding='utf-8')
    command = ['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes',
        '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12',
        'magicvvu_ai@8.134.172.165','sudo -n /usr/bin/python3 -']
    result = subprocess.run(command, input=code.encode(), capture_output=True, timeout=480)
    if result.returncode:
        # Server code emits only a sanitized reason. Private container config
        # and build diagnostics never travel back to the local repository.
        print(result.stdout.decode(errors='replace')[-1600:])
        print(result.stderr.decode(errors='replace')[-1600:])
        raise SystemExit(result.returncode)
    data = json.loads(result.stdout)
    if args.stage == 'audit': data['local_hashes'] = hashes
    if args.stage == 'capture':
        contracts = ROOT/'docs/versions/V1-P8.5/contracts'
        (contracts/'production-ai-openapi.json').write_text(json.dumps(data.pop('openapi'), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (REPORTS/('p85-production-'+args.stage+'.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in {'local_hashes','workspace_hashes','runtime_hashes','all_python','protected','allowed_compose','source_files'}}, ensure_ascii=False))


if __name__ == '__main__': main()
