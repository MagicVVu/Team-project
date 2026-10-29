"""Read-only verification of the released inventory schema, TLS and services."""
import json
from pathlib import Path
import subprocess

ROOT = Path('/srv/magicvvu/releases/inventory-units-20261029')


def inside(service, code):
    p = subprocess.run(['docker', 'exec', '-i', f'magicvvu-starter-{service}-1', 'python', '-B', '-'],
                       input=code, text=True, capture_output=True, check=True, timeout=30)
    return json.loads(p.stdout)


database = inside('backend', '''
import json
from sqlalchemy import inspect, text
from app.database import engine
from app.main import app
with engine.connect() as db:
 db.execute(text('SET TRANSACTION READ ONLY'))
 payload=db.execute(text('select payload_json from inventory_unit_migration_backup where id=1')).scalar_one()
 before=payload['before']['inventory_items']
 current={str(r['id']):dict(r) for r in db.execute(text('select * from inventory_items')).mappings()}
 fields=('name','household_id','category','storage_location','expires_on','purchased_on','source_shopping_list_item_id','created_by_user_id','opened_at')
 preserved=all(key in current and all(str(current[key][f])==str(old[f]) for f in fields) for old in before for key in [old['id']])
 revision=db.execute(text('select version_num from alembic_version')).scalar_one()
 linked=db.execute(text('select count(*) from product_batches')).scalar_one()
 cross=db.execute(text('select count(*) from product_batches b join inventory_items i on i.id=b.inventory_item_id join products p on p.id=b.product_id where i.household_id<>p.household_id')).scalar_one()
 states={r[0]:r[1] for r in db.execute(text('select status,count(*) from inventory_items group by status'))}
 columns=[c['name'] for c in inspect(db).get_columns('inventory_items')]
 schema=app.openapi()['components']['schemas']['StockResponse']['properties']
 print(json.dumps({'revision':revision,'source_rows':len(before),'inventory_rows':len(current),'status_counts':states,
  'original_ids_fields_preserved':preserved,'every_row_linked':linked==len(current),'cross_household_links':cross,
  'quantity_column_removed':'quantity' not in columns,'specification_column_present':'specification' in columns,
  'inventory_response_omits_quantity':'quantity' not in schema,'audit':payload['audit']}))
''')

https = inside('backend', '''
import json,os,ssl,urllib.request,urllib.error
op=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
def status(path,headers):
 try:
  with op.open(urllib.request.Request('https://127.0.0.1:8443'+path,headers=headers),timeout=5) as response:return response.status
 except urllib.error.HTTPError as error:return error.code
key={'X-MagicVVu-App-Key':os.environ['MAGICVVU_APP_API_KEY']}
print(json.dumps({'direct_tls_health':status('/api/v1/health',key),
 'no_app_key':status('/api/v1/users/me',{}),'no_bearer':status('/api/v1/users/me',key)}))
''')
ai = inside('agent', '''
import json,urllib.request
from p0.domain import UNITS
health=json.load(urllib.request.urlopen('http://127.0.0.1:8767/health',timeout=5))
print(json.dumps({'status':health['status'],'protocol':health.get('conversation_dialogue_protocol'),
 'max_model_calls':health.get('dialogue_max_model_calls'),'portion_and_object_units':all(u in UNITS for u in ('份','件'))}))
''')
assert database['revision'] == '20261029_0012'
assert all(database[k] for k in ('original_ids_fields_preserved', 'every_row_linked', 'quantity_column_removed',
                                'specification_column_present', 'inventory_response_omits_quantity'))
assert database['cross_household_links'] == 0
assert https == {'direct_tls_health': 200, 'no_app_key': 403, 'no_bearer': 401}
assert ai['status'] == 'ok' and ai['protocol'] == 'p85-dialogue-1' and ai['max_model_calls'] == 2 and ai['portion_and_object_units']
result = {'passed': True, 'database': database, 'https': https, 'ai': ai, 'production_model_calls': 0,
          'production_test_inventory_created': False}
(ROOT / 'postcheck.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
