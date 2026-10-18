"""Preserve the overlay and materialize Git bytes plus explicitly changed files."""
import hashlib, json, subprocess, tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(r'C:/Users/Cavia/AppData/Local/OpenAI/Codex-Account2/codex-home/visualizations/2026/10/17/01a1488c-0eac-7ca1-8090-0af8562bc511/phase5-2-20261018')
OUT.mkdir(parents=True, exist_ok=True)
def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])
head = git('rev-parse','HEAD').decode().strip()
changed = set(git('diff','--name-only','-z').decode().strip('\0').split('\0'))
new = set(git('ls-files','--others','--exclude-standard','-z').decode().strip('\0').split('\0'))
changed.discard('');new.discard('')
patch = git('diff','--binary')
(OUT/'candidate.patch').write_bytes(patch)
(OUT/'initial-status.txt').write_bytes(git('status','--short'))
files = set(git('ls-files','-z').decode().strip('\0').split('\0')) | new
snapshot = OUT/'source'
previous_path=OUT/'candidate-source-manifest.json'
previous=json.loads(previous_path.read_text()) if previous_path.exists() else {}
cached={x['path']:x for x in previous.get('files',[])} if previous.get('base_commit')==head else {}
rows = []
for rel in sorted(files):
    path = ROOT/rel
    if not path.is_file(): continue
    dest=snapshot/rel
    if rel in changed|new:
        data=path.read_bytes()
    elif rel in cached and dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest()==cached[rel]['sha256']:
        data=dest.read_bytes()
    else:
        data=git('show','HEAD:'+rel)
    dest = snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    rows.append({'path':rel,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data), 'source':'overlay' if rel in changed|new else 'git-blob'})
identity = hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
manifest = {'base_commit':head,'snapshot_sha256':identity,'files':rows}
(OUT/'candidate-source-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
prior = json.loads((OUT.parent/'phase5/candidate-source-manifest.json').read_text(encoding='utf-8-sig'))
comparison = [{**r,'present':(ROOT/r['path']).exists(),'unchanged':(ROOT/r['path']).is_file() and hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256']} for r in prior['files']]
(OUT/'overlay-preservation.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
with tarfile.open(OUT/'candidate-source.tar.gz','w:gz') as tar:
    for row in rows:
        if row['path'].startswith(('backend/server/','agent/','frontend/tools/')):
            tar.add(snapshot/row['path'],arcname=row['path'],recursive=False)
print(json.dumps({'snapshot':identity,'files':len(rows),'prior_overlay_all_preserved':all(r['unchanged'] for r in comparison)}))
