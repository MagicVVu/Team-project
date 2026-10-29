"""Restore ignored snapshot bytes from the exact local Git commit, never HEAD."""
import hashlib,json,subprocess
from pathlib import Path
from prepare import ROUND,REPO

def frozen_bytes(raw,expected):
    # Git stores LF; the frozen Windows checkout generally uses CRLF.
    candidates=[raw,raw.replace(b'\r\n',b'\n'),raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')]
    for candidate in candidates:
        if hashlib.sha256(candidate).hexdigest()==expected:return candidate
    raise RuntimeError('GIT_BYTES_DIFFER_FROM_FROZEN_WORKING_SOURCE')

def main():
    manifest=json.loads((ROUND/'evidence/source-manifest.json').read_text(encoding='utf-8'))
    restored=0
    for row in manifest['snapshot_files']:
        dest=ROUND/'.snapshot'/row['path']
        if not dest.resolve().is_relative_to((ROUND/'.snapshot').resolve()): raise RuntimeError('UNSAFE_SNAPSHOT_PATH')
        if dest.exists():
            if hashlib.sha256(dest.read_bytes()).hexdigest()!=row['sha256']: raise RuntimeError('EXISTING_SNAPSHOT_CHANGED')
            continue
        raw=subprocess.check_output(['git','show',manifest['head']+':'+row['path']],cwd=REPO)
        raw=frozen_bytes(raw,row['sha256'])
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);restored+=1
    print(json.dumps({'restored':restored,'commit':manifest['head']}))
if __name__=='__main__':main()
