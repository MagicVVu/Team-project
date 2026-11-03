"""Explicit P8.7 release phases over SSH; no Git mutation or secret export."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/ai-english/production-20261101'
sys.path.insert(0,str(ROOT/'agent'))
from integration.source_manifest import manifest

BASE='8f44a6a'
BACKEND=['app/assistant_language.py','app/data/assistant_lexicon.json',
    'app/main.py','app/memory_schemas.py','app/dialogue_schemas.py','app/routers/ai_inventory.py',
    'app/routers/draft_execution.py','app/routers/session_memory.py','app/services/autonomous.py',
    'app/services/dialogue.py','app/services/session_memory.py']
BLOBS={}


def load_blobs(refs,paths):
    queries=[ref+':'+p for ref in refs for p in paths]
    result=subprocess.run(['git','cat-file','--batch'],cwd=ROOT,input=('\n'.join(queries)+'\n').encode(),capture_output=True,check=True)
    offset=0
    for query in queries:
        end=result.stdout.index(b'\n',offset);header=result.stdout[offset:end];offset=end+1
        if header.endswith(b' missing'):BLOBS[query]=None;continue
        size=int(header.rsplit(b' ',1)[1]);BLOBS[query]=result.stdout[offset:offset+size];offset+=size+1


def blob(ref,path):
    if ref+':'+path in BLOBS:return BLOBS[ref+':'+path]
    value=subprocess.run(['git','show',ref+':'+path],cwd=ROOT,capture_output=True)
    return value.stdout if value.returncode==0 else None


def payload(include_known=True):
    # Historical Dockerfiles are build provenance; preserve them in the image.
    paths={'agent':[p for p in manifest()['files'] if not p.startswith('Dockerfile')],'backend':BACKEND}
    value={'files':{},'base':{},'known':{}}
    refs=subprocess.check_output(['git','rev-list','--first-parent','-8','HEAD'],cwd=ROOT).decode().splitlines() if include_known else []
    if include_known:load_blobs([BASE,*refs],[*['agent/'+p for p in paths['agent']],*['backend/server/'+p for p in paths['backend']]])
    for service,names in paths.items():
        prefix='agent/' if service=='agent' else 'backend/server/'
        value['files'][service]={};value['base'][service]={};value['known'][service]={}
        for path in names:
            raw=(ROOT/prefix/path).read_bytes()
            value['files'][service][path]=base64.b64encode(raw).decode()
            old=blob(BASE,prefix+path) if include_known else None
            value['base'][service][path]=hashlib.sha256(old.replace(b'\r\n',b'\n')).hexdigest() if old is not None else None
            known={hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
            if service=='agent':
                for ref in refs:
                    previous=blob(ref,prefix+path)
                    if previous is not None:known.add(hashlib.sha256(previous.replace(b'\r\n',b'\n')).hexdigest())
            value['known'][service][path]=sorted(known)
    value['local_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    value['public_ca']=(ROOT/'frontend/app/src/debug/res/raw/magicvvu_test_ca.pem').read_text(encoding='ascii')
    return value


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['audit','prepare','switch','verify','model-check','network-check','capture','rollback'])
    args=parser.parse_args();REPORT.mkdir(parents=True,exist_ok=True)
    value=payload(include_known=args.stage=='audit')
    if args.stage!='audit':value['audit']=json.loads((REPORT/'audit.json').read_text(encoding='utf-8'))
    source='PAYLOAD='+repr(value)+'\nSTAGE='+repr(args.stage)+'\n'+(ROOT/'tools/p87_release_remote.py').read_text(encoding='utf-8')
    command=['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','magicvvu_ai@8.134.172.165','sudo -n /usr/bin/python3 -']
    result=subprocess.run(command,input=source.encode(),capture_output=True,timeout=600)
    if result.returncode:
        print(result.stdout.decode(errors='replace')[-1800:]);print(result.stderr.decode(errors='replace')[-800:])
        raise SystemExit(result.returncode)
    data=json.loads(result.stdout)
    if args.stage=='capture':
        for kind,api in data.pop('apis').items():
            target=ROOT/'docs/versions/V1-P8.7/contracts'/('production-'+kind+'-openapi.json')
            target.write_text(json.dumps(api,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (REPORT/(args.stage+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in {'sources','workspace','protected','files','all_python','environment_files'}},ensure_ascii=False))


if __name__=='__main__':main()
