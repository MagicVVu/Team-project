"""Synchronize owned AI source only. Never deploy, restart or touch backend/DB.

Existing remote files must match current source or a recorded local Git source
revision (LF/CRLF variants allowed). Unknown changes fail before any writes.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"agent"))
from integration.source_manifest import manifest

REMOTE=r'''
import base64,hashlib,json,os,pathlib,shutil,stat,tempfile
payload=PAYLOAD
root=pathlib.Path.home()/'workspace'/'agent'
if root.is_symlink() or not root.is_dir():raise RuntimeError('Invalid AI workspace')
root=root.resolve()
def path_for(rel):
    path=root/rel
    if path.is_symlink() or not path.resolve().is_relative_to(root):raise RuntimeError('Unsafe AI source path')
    for parent in path.parents:
        if parent==root:break
        if parent.is_symlink():raise RuntimeError('Symlinked parent')
    return path
def digest(path):
    if path.exists() and not path.is_file():raise RuntimeError('Non-file source target')
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
before={rel:digest(path_for(rel)) for rel in payload['files']}
conflicts=[rel for rel,actual in before.items() if actual is not None and actual not in payload['accepted'][rel]]
if conflicts:
    print(json.dumps({'conflicts':conflicts,'written':False}))
    raise SystemExit(3)
changed=[rel for rel,target in payload['files'].items() if before[rel]!=target]
backup=None
if payload['apply'] and changed:
    backup=path_for('.source_backups/'+payload['run_id'])
    if backup.exists():raise RuntimeError('Backup directory already exists')
    backup.mkdir(parents=True,mode=0o700)
    for rel in changed:
        path=path_for(rel)
        if digest(path)!=before[rel]:raise RuntimeError('Concurrent AI source change: '+rel)
        if before[rel] is not None:
            saved=backup/rel;saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,saved)
    for rel in changed:
        path=path_for(rel)
        if digest(path)!=before[rel]:raise RuntimeError('Concurrent AI source change: '+rel)
        content=base64.b64decode(payload['content'][rel],validate=True)
        if hashlib.sha256(content).hexdigest()!=payload['files'][rel]:raise RuntimeError('Payload hash mismatch')
        path.parent.mkdir(parents=True,exist_ok=True)
        mode=stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
        fd,temp=tempfile.mkstemp(prefix='.p84-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(content)
            os.chmod(temp,mode)
            os.replace(temp,path)
        finally:
            if os.path.exists(temp):os.unlink(temp)
after={rel:digest(path_for(rel)) for rel in payload['files']}
if payload['apply'] and after!=payload['files']:raise RuntimeError('AI source verification failed')
print(json.dumps({'remote_root':str(root),'changed':changed,'before':before,'after':after,
    'hashes_verified':after==payload['files'],'written':payload['apply'],
    'backup_directory':str(backup) if backup else None,'services_restarted':False,'backend_modified':False}))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['audit','apply'])
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    current=manifest()
    revisions=['f1f5dcb','32b043c64b72336a7a467de9e928934d36194a53']
    accepted={rel:{digest} for rel,digest in current['files'].items()}
    for revision in revisions:
        for rel in accepted:
            old=subprocess.run(['git','show',revision+':agent/'+rel],cwd=ROOT,capture_output=True)
            if old.returncode==0:
                lf=old.stdout.replace(b'\r\n',b'\n')
                accepted[rel].update(hashlib.sha256(value).hexdigest() for value in (old.stdout,lf,lf.replace(b'\n',b'\r\n')))
    payload={'files':current['files'],'accepted':{p:sorted(v) for p,v in accepted.items()},
        'apply':args.phase=='apply','run_id':'p84-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}
    if payload['apply']:payload['content']={rel:base64.b64encode((ROOT/'agent'/rel).read_bytes()).decode() for rel in current['files']}
    command=['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','magicvvu_ai@8.134.172.165','python3 -']
    script=REMOTE.replace('payload=PAYLOAD','payload='+repr(payload))
    result=subprocess.run(command,input=script.encode(),capture_output=True,timeout=90)
    if result.returncode:
        print(result.stdout.decode(errors='replace')[-2000:])
        print(result.stderr.decode(errors='replace')[-1600:])
        raise SystemExit(result.returncode)
    report=json.loads(result.stdout)
    report.update(stage='V1-P8.4',phase=args.phase,files=current['files'],source_baselines=revisions,
                  documents_included=False,credentials_included=False,database_modified=False)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'files','before','after','source_baselines'}},ensure_ascii=False))


if __name__=='__main__':main()
