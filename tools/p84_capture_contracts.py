"""Read-only capture of the deployed AI/backend contracts; no credentials printed."""
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import json,subprocess,urllib.request
obj=json.loads(subprocess.check_output(['docker','inspect','magicvvu-starter-agent-1']))[0]
origin='http://'+next(iter(obj['NetworkSettings']['Networks'].values()))['IPAddress']+':8767'
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(origin+'/openapi.json',timeout=12) as response:ai=json.load(response)
code='from app.main import app\nimport json\nprint(json.dumps(app.openapi()))'
backend=json.loads(subprocess.check_output(['docker','exec','magicvvu-starter-backend-1','python','-B','-c',code]))
print(json.dumps({'ai':ai,'backend':backend}))
'''
command=['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
    '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','magicvvu_ai@8.134.172.165','python3 -']
process=subprocess.run(command,input=REMOTE.encode(),capture_output=True,timeout=45)
if process.returncode:
    print(process.stderr.decode(errors='replace')[-1200:]);raise SystemExit(process.returncode)
contracts=json.loads(process.stdout)
directory=ROOT/'docs/versions/V1-P8.4/contracts'
summary={}
for name,value in contracts.items():
    value['x-deployment-status']='production_verified_2026-10-27'
    value['x-ai-adapter-release']='V1-P8.4'
    value['x-conversation-dialogue-protocol']='p84-dialogue-1'
    value['x-maintenance-release']='V1-P8.4' if name=='ai' else 'V1-P9'
    path=directory/('production-'+name+'-openapi.json')
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary[name]={'path':path.relative_to(ROOT).as_posix(),'route_count':len(value['paths'])}
(ROOT/'reports/p84-dialogue/production-contract-capture.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary))
