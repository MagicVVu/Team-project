"""Freeze support fixtures required by unchanged native tests, before paid tests."""
import shutil,subprocess
from prepare import REPO,ROUND,sha,write
import json
path=ROUND/'evidence/source.json';record=json.loads(path.read_text(encoding='utf-8'))
existing={row['path'] for row in record['snapshot']}
paths=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode().split('\0')
for name in filter(None,paths):
    if not (name.startswith(('deploy/','tools/','tests/garin/test_package/Agent_Regression_v1/')) or name=='tests/garin/失败清单.json'):continue
    if name in existing or any(t in {'.cache','__pycache__','credentials','.env','node_modules'} for t in __import__('pathlib').Path(name).parts):continue
    src=REPO/name
    if not src.is_file():continue
    dest=ROUND/'.snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    record['snapshot'].append({'path':name,'sha256':sha(src)})
write(path,record)
print('Support fixture snapshot files:',len(record['snapshot']))
