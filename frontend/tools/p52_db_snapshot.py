"""Direct read-only PostgreSQL evidence, limited to a fresh synthetic fixture."""
import argparse,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
f=json.loads(a.fixture.read_text(encoding='utf-8-sig'))
homes=[f[k] for k in ('household','second_household','other_household')]
code='''
import json
from sqlalchemy import text
from app.database import SessionLocal
homes=HOMES
queries={n:'SELECT x.* FROM '+n+' x WHERE x.household_id IN :homes' for n in ('inventory_items','ai_tasks','ai_drafts','draft_operations','business_events')}
queries['draft_decisions']='SELECT x.* FROM draft_decisions x JOIN ai_drafts d ON d.id=x.draft_id WHERE d.household_id IN :homes'
queries['shopping_list_items']='SELECT x.* FROM shopping_list_items x JOIN shopping_lists l ON l.id=x.shopping_list_id WHERE l.household_id IN :homes'
queries['members']='SELECT user_id,household_id,role FROM household_members WHERE household_id IN :homes'
from sqlalchemy import bindparam
with SessionLocal() as db:
 db.execute(text('SET TRANSACTION READ ONLY'))
 result={n:[dict(x) for x in db.execute(text(q).bindparams(bindparam('homes',expanding=True)),{'homes':homes}).mappings()] for n,q in queries.items()}
 result['migration']=db.execute(text('SELECT version_num FROM alembic_version')).scalar()
 result['server_version']=db.execute(text('SHOW server_version')).scalar()
 db.rollback()
print(json.dumps(result,default=str,ensure_ascii=False))
'''.replace('HOMES',repr(homes))
remote=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','magicvvu','sudo -n python3 /home/admin/magicvvu-p7-p52-final-20261018/p52_remote.py code']
r=subprocess.run(remote,input=code.encode(),capture_output=True)
assert r.returncode==0,'Read-only PostgreSQL evidence helper failed'
data=json.loads(r.stdout)
a.output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'tables':{k:len(v) for k,v in data.items() if isinstance(v,list)},'migration':data['migration']}))
