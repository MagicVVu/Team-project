"""Read-only server comparison and local pre-adaptation source backup."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"reports/p86-autonomous/adaptation-20261030"
CACHE=ROOT/".cache/runtime-adaptation-20261030"
sys.path.insert(0,str(ROOT/"agent"))
from integration.source_manifest import manifest

BACKEND=["app/services/dialogue.py","app/dialogue_schemas.py","app/memory_schemas.py",
 "app/routers/session_memory.py","app/services/session_memory.py","app/routers/draft_execution.py",
 "app/services/memory_archive.py","app/services/ai_inventory.py","app/models.py","app/execution_models.py",
 "app/inventory_schemas.py","app/services/draft_execution.py","app/services/physical_inventory.py",
 "app/routers/ai_inventory.py","app/routers/planning.py","app/services/planning_context.py"]


def git(*args):return subprocess.run(["git",*args],cwd=ROOT,capture_output=True,check=True).stdout
def sha(value):return hashlib.sha256(value.replace(b'\r\n',b'\n')).hexdigest()


def postcheck():
    """Keep the initial audit/backup immutable; recheck runtime identity only."""
    code=r'''
import json,subprocess,urllib.request
from datetime import datetime,timezone
out={'checked_at':datetime.now(timezone.utc).isoformat(),'containers':{},'health':{}}
for kind in ('agent','backend','db'):
 name='magicvvu-starter-'+kind+'-1'
 obj=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
 settings=dict(v.split('=',1) for v in obj['Config'].get('Env',[]))
 out['containers'][kind]={'id':obj['Id'],'image':obj['Config']['Image'],'started_at':obj['State']['StartedAt'],
  'health':obj['State'].get('Health',{}).get('Status'),'protocol':settings.get('AI_CONVERSATION_DIALOGUE_PROTOCOL'),
  'engine':settings.get('P3_ENGINE'),'model':settings.get('LLM_MODEL')}
 if kind=='db':continue
 host=next(iter(obj['NetworkSettings']['Networks'].values()))['IPAddress']
 url='http://'+host+(':8767/health' if kind=='agent' else ':8000/api/v1/health')
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(url,timeout=8) as response:out['health'][kind]=json.load(response)
print(json.dumps(out))
'''
    command=['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','magicvvu_ai@8.134.172.165','sudo -n /usr/bin/python3 -']
    remote=subprocess.run(command,input=code.encode(),capture_output=True,timeout=60,check=True)
    value=json.loads(remote.stdout)
    original=json.loads((REPORT/'server-audit.json').read_text(encoding='utf-8'))
    value['same_container_identity']=all(all(value['containers'][kind][key]==old[key]
        for key in ('id','image','started_at','protocol','engine','model')) for kind,old in original['containers'].items())
    value['server_modified_by_this_work']=False
    (REPORT/'server-postcheck.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(value,ensure_ascii=False))


def main():
    REPORT.mkdir(parents=True,exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    # Preserve the conflict text and all three index versions before any edit.
    if not (CACHE/"before.json").exists():
        status=git("status","--porcelain=v2","--branch")
        unmerged=[p for p in git("diff","--name-only","--diff-filter=U","-z").decode().split('\0') if p]
        staged=[p for p in git("diff","--cached","--name-only","--diff-filter=ACM","-z").decode().split('\0') if p]
        paths=list(dict.fromkeys([*unmerged,*staged]))
        for rel in paths:
            target=CACHE/"before-worktree"/rel;target.parent.mkdir(parents=True,exist_ok=True)
            if (ROOT/rel).is_file():target.write_bytes((ROOT/rel).read_bytes())
        for rel in unmerged:
            for stage in (1,2,3):
                target=CACHE/("index-stage-"+str(stage))/rel
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(git("show",f":{stage}:{rel}"))
        gitfile=CACHE/"before.json"
        gitfile.write_text(json.dumps({"head":git("rev-parse","HEAD").decode().strip(),
            "origin_dev":git("rev-parse","origin/dev").decode().strip(),"status":status.decode(),"unmerged":unmerged,
            "preserved_files":paths},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    paths={"agent":list(manifest()["files"]),"backend":BACKEND}
    code=r'''
import base64,hashlib,json,subprocess,urllib.request
names={'agent':'magicvvu-starter-agent-1','backend':'magicvvu-starter-backend-1','db':'magicvvu-starter-db-1'}
result={'containers':{},'sources':{},'apis':{}}
for kind,name in names.items():
 obj=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
 settings=dict(v.split('=',1) for v in obj['Config'].get('Env',[]))
 result['containers'][kind]={'id':obj['Id'],'image':obj['Config']['Image'],'started_at':obj['State']['StartedAt'],'health':obj['State'].get('Health',{}).get('Status'),
  'protocol':settings.get('AI_CONVERSATION_DIALOGUE_PROTOCOL'),'engine':settings.get('P3_ENGINE'),'model':settings.get('LLM_MODEL')}
 if kind=='db':continue
 root='/app/agent' if kind=='agent' else '/app'
 inner="import pathlib,json,base64; r=pathlib.Path("+repr(root)+"); print(json.dumps({p:base64.b64encode((r/p).read_bytes()).decode() if (r/p).is_file() else None for p in "+repr(PATHS[kind])+"}))"
 result['sources'][kind]=json.loads(subprocess.check_output(['docker','exec',name,'python','-B','-c',inner]))
 origin='http://'+next(iter(obj['NetworkSettings']['Networks'].values()))['IPAddress']+(':'+('8767' if kind=='agent' else '8000'))
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for label,path in [('health','/health' if kind=='agent' else '/api/v1/health'),('openapi','/openapi.json')]:
  try:
   with opener.open(origin+path,timeout=8) as response:result['apis'][kind+'_'+label]=json.load(response)
  except Exception as error:result['apis'][kind+'_'+label]={'read_error':type(error).__name__}
command='exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
query="BEGIN READ ONLY; SELECT json_agg(version_num) FROM alembic_version; ROLLBACK;"
result['schema_revision']=subprocess.check_output(['docker','exec','-i',names['db'],'sh','-c',command],input=query.encode()).decode().strip()
print(json.dumps(result))
'''
    command=['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','magicvvu_ai@8.134.172.165','sudo -n /usr/bin/python3 -']
    remote=subprocess.run(command,input=('PATHS='+repr(paths)+'\n'+code).encode(),capture_output=True,timeout=90,check=True)
    value=json.loads(remote.stdout)
    sources=value.pop('sources')
    comparison=[]
    for kind,files in sources.items():
        for rel,encoded in files.items():
            repo_rel=('agent/' if kind=='agent' else 'backend/server/')+rel
            if encoded is None:
                comparison.append({'path':repo_rel,'remote_missing':True});continue
            raw=base64.b64decode(encoded,validate=True)
            path=CACHE/'server-source'/repo_rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            item={'path':repo_rel,'server_sha256':sha(raw),'worktree_matches':(ROOT/repo_rel).is_file() and sha((ROOT/repo_rel).read_bytes())==sha(raw)}
            for ref in ('HEAD','origin/dev'):
                found=subprocess.run(['git','show',ref+':'+repo_rel],cwd=ROOT,capture_output=True)
                item[ref+'_matches']=found.returncode==0 and sha(found.stdout)==sha(raw)
            comparison.append(item)
    for key,data in value.pop('apis').items():
        (REPORT/(key+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding='utf-8')
    value.update(source_comparison=comparison,server_modified=False,personal_inventory_read=False,
        local_head=git('rev-parse','HEAD').decode().strip(),origin_dev=git('rev-parse','origin/dev').decode().strip())
    (REPORT/'server-audit.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding='utf-8')
    print(json.dumps({'containers':value['containers'],'schema_revision':value['schema_revision'],
        'server_sources_not_matching_origin':[x['path'] for x in comparison if not x.get('remote_missing') and not x.get('origin/dev_matches')],
        'local_differences':[x['path'] for x in comparison if not x.get('remote_missing') and not x.get('worktree_matches')],
        'remote_missing':[x['path'] for x in comparison if x.get('remote_missing')],
        'backup':str(CACHE/'before.json'),'server_modified':False},ensure_ascii=False))


if __name__=='__main__':
    if '--postcheck' in sys.argv:postcheck()
    else:main()
