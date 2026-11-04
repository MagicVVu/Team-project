"""Rebuild ignored source from the fixed Git commit, without checkout or fetch."""
import json,hashlib,subprocess
from prepare import ROUND,REPO,HEAD
record=json.loads((ROUND/'evidence/source.json').read_text(encoding='utf-8'))
assert record['head']==HEAD
for row in record['snapshot']:
    path=ROUND/'.snapshot'/row['path']
    if path.exists():
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],'Existing snapshot mismatch; do not overwrite'
        continue
    value=subprocess.check_output(['git','show',HEAD+':'+row['path']],cwd=REPO)
    # Working files may have CRLF normalization. Accept only the recorded bytes.
    if hashlib.sha256(value).hexdigest()!=row['sha256']:
        normalized=value.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
        if hashlib.sha256(normalized).hexdigest()==row['sha256']:value=normalized
        else:raise RuntimeError('FIXED_GIT_BYTES_DO_NOT_MATCH_MANIFEST: '+row['path'])
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
print('Fixed snapshot restored and all hashes checked. No checkout, server or API call.')
