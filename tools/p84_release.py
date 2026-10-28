"""Local release operator. Private container config never leaves the server."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT.parent/'.runtime/p84-release'
REPORTS=ROOT/'reports/p84-dialogue'
sys.path.insert(0,str(ROOT/'agent'))
from integration.source_manifest import manifest

BACKEND=['app/memory_schemas.py','app/routers/session_memory.py','app/services/session_memory.py',
         'app/routers/draft_execution.py','app/services/dialogue.py']


def local_sources():
    return {'agent':{p:(ROOT/'agent'/p).read_bytes() for p in manifest()['files']},
            'backend':{p:(ROOT/'backend/server'/p).read_bytes() for p in BACKEND}}


def packet(rows):return {s:{p:base64.b64encode(b).decode() for p,b in values.items()} for s,values in rows.items()}


def remote(stage,payload):
    script='PAYLOAD='+repr(payload)+'\nSTAGE='+repr(stage)+'\n'+(ROOT/'tools/p84_release_remote.py').read_text(encoding='utf-8')
    command=['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','magicvvu_ai@8.134.172.165','sudo -n /usr/bin/python3 -']
    result=subprocess.run(command,input=script.encode(),capture_output=True,timeout=600)
    if result.returncode:
        (PRIVATE/(stage+'-error.private.log')).write_bytes(result.stdout+result.stderr)
        print('Release step failed; diagnostic retained locally without printing secrets: '+stage)
        print(result.stderr.decode(errors='replace')[-1400:])
        raise SystemExit(result.returncode)
    return json.loads(result.stdout)


def smoke_agent():
    tree=ast.parse((ROOT/'tools/p84_check_remote_source.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CHECK' for t in node.targets):
            value=ast.literal_eval(node.value)
            return value.replace("assert health['conversation_dialogue_protocol']=='p84-dialogue-1'",
                "assert health['conversation_dialogue_protocol']=='p84-dialogue-1'\n        assert health['maintenance_release']=='V1-P8.4'")
    raise RuntimeError('Missing offline AI smoke source')


def merge_backend(audit,rows):
    merged={};proof={}
    for path,new in rows.items():
        wire=audit['services']['backend']['files'][path]
        live=base64.b64decode(wire) if wire else None
        old=subprocess.run(['git','show','36ce90e^:backend/server/'+path],cwd=ROOT,capture_output=True)
        if old.returncode:
            if live is not None and live.replace(b'\r\n',b'\n')!=new.replace(b'\r\n',b'\n'):
                raise RuntimeError('Unowned existing new backend adapter: '+path)
            result=new
        else:
            if live is None:raise RuntimeError('Missing released backend file: '+path)
            with tempfile.TemporaryDirectory(dir=PRIVATE) as temporary:
                directory=Path(temporary)
                for name,raw in [('live',live),('base',old.stdout),('proposed',new)]:
                    (directory/name).write_bytes(raw.replace(b'\r\n',b'\n'))
                process=subprocess.run(['git','merge-file','--stdout','--diff3',str(directory/'live'),str(directory/'base'),str(directory/'proposed')],capture_output=True)
                if process.returncode:
                    (PRIVATE/('conflict-'+path.replace('/','_'))).write_bytes(process.stdout)
                    raise RuntimeError('Backend contribution conflict requires reconciliation: '+path)
                result=process.stdout
        ast.parse(result.decode('utf-8-sig'),filename=path)
        merged[path]=result
        target=PRIVATE/'merged-backend'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(result)
        proof[path]={'live_sha256':hashlib.sha256(live).hexdigest() if live else None,
            'merged_sha256':hashlib.sha256(result).hexdigest(),'three_way_merge_clean':True,
            'identical_to_local':result.replace(b'\r\n',b'\n')==new.replace(b'\r\n',b'\n')}
    return merged,proof


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['audit','prepare','switch','verify']);args=parser.parse_args()
    PRIVATE.mkdir(parents=True,exist_ok=True);REPORTS.mkdir(parents=True,exist_ok=True)
    rows=local_sources();payload={'sources':packet(rows),'attempt':'r2'}
    if args.stage=='audit':
        result=remote('audit',payload)
        (PRIVATE/'audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        merged,proof=merge_backend(result,rows['backend'])
        (PRIVATE/'sources.json').write_text(json.dumps(packet({**rows,'backend':merged}))+'\n',encoding='utf-8')
        report={'stage':'audited','services':{s:r['identity'] for s,r in result['services'].items()},
            'protected_services':result['protected'],'schema_revision':result['schema_revision'],'backend_merge':proof,
            'ai_files':len(rows['agent']),'backend_adapter_files':len(merged),'formal_runtime_switched':False}
    else:
        payload['sources']=json.loads((PRIVATE/'sources.json').read_text())
        assert payload['sources']['agent']==packet({'agent':rows['agent']})['agent'],'AI source changed after release audit'
        payload['audit']=json.loads((PRIVATE/'audit.json').read_text())
        payload['smoke_agent']=smoke_agent()
        payload['smoke_backend']=(ROOT/'tools/p84_release_smoke_backend.py').read_text(encoding='utf-8')
        report=remote(args.stage,payload)
    (REPORTS/('production-'+args.stage+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
