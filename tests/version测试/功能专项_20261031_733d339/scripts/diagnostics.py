"""Read-only schema diagnosis, no external service or real database."""
import json,sys
from prepare import ROUND,write
from offline import setup
out=ROUND/'runs/schema-diagnosis';out.mkdir(exist_ok=False);setup('backend',out)
sys.path.insert(0,str(ROUND/'.snapshot/backend/server/tests'))
from test_v09_execution import app
from contract_compatibility import decimal_schema_projection
old=json.loads((ROUND/'.snapshot/docs/versions/V1-P8.6/contracts/backend-openapi.json').read_text(encoding='utf-8'))
for k in list(old):
 if k.startswith('x-'):old.pop(k)
new=app.openapi();diff=[]
def compare(a,b,path=''):
 if isinstance(a,dict) and isinstance(b,dict):
  for k in sorted(a.keys()|b.keys()):
   p=path+'/'+k
   if k not in a:diff.append({'path':p,'kind':'added','current':b[k]})
   elif k not in b:diff.append({'path':p,'kind':'removed','documented':a[k]})
   else:compare(a[k],b[k],p)
 elif isinstance(a,list) and isinstance(b,list):
  if a!=b:diff.append({'path':path,'kind':'changed','documented':a,'current':b})
 elif a!=b:diff.append({'path':path,'kind':'changed','documented':a,'current':b})
compare(decimal_schema_projection(old),decimal_schema_projection(new))
write(out/'contract-differences.json',{'source':'docs/versions/V1-P8.6/contracts/backend-openapi.json vs current local app.openapi','difference_count':len(diff),'differences':diff,'scope':'local current source only, not running server'})
print(json.dumps({'differences':len(diff),'sample_paths':[d['path'] for d in diff[:12]]},ensure_ascii=False))
