"""Read only guest test state; never export credentials or unrelated record values."""
import pathlib,subprocess,json,hashlib,sys,datetime,xml.etree.ElementTree as ET
ROOT=pathlib.Path(r'D:\Team_Project\Team-project\tests\garin\MuMu_游客本地测试_20261016')
ADB=[r'E:\Development\SDKs\Android\platform-tools\adb.exe','-s','127.0.0.1:16416']
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
baseline=json.loads((ROOT/'device_baseline.json').read_text(encoding='utf8'))
tree=ET.fromstring(subprocess.check_output(ADB+['exec-out','run-as','com.example.teamapp','cat','shared_prefs/magicvvu_v1.xml']))
state=json.loads(next(x.text for x in tree if x.attrib.get('name')=='state'))
credentials=ET.fromstring(subprocess.check_output(ADB+['exec-out','run-as','com.example.teamapp','cat','shared_prefs/magicvvu_cloud_credentials.xml']))
items={x['id']:x for x in state['items']}
tests=[x for x in state['items'] if 'GarinTest' in x['name']]
row={'label':sys.argv[1],'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'item_count':len(items),'cloud_session_present':any(x.attrib.get('name')=='session' for x in credentials),'test_items':tests,'test_purchases':[x for x in state['purchases'] if x['itemId'] in {t['id'] for t in tests}],'unrelated_changed':[k for k,v in baseline['initial_item_hashes'].items() if k in items and digest(items[k])!=v],'unrelated_missing':[k for k in baseline['initial_item_hashes'] if k not in items],'unexpected_new_items':[x['id'] for x in state['items'] if x['id'] not in baseline['initial_item_hashes'] and x not in tests],'nonitem_hash':digest({k:v for k,v in state.items() if k!='items'})}
assert not row['cloud_session_present'],'Cloud session appeared; stop local test'
assert not row['unrelated_changed'] and not row['unrelated_missing'],'Existing records changed'
out=ROOT/'checkpoints';out.mkdir(exist_ok=True);file=out/(sys.argv[1]+'.json')
if file.exists():raise FileExistsError(file)
file.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'label':row['label'],'item_count':row['item_count'],'tests':[(x['name'],x['quantity'],x['unit']) for x in tests],'test_purchases':row['test_purchases'],'unrelated_changed':row['unrelated_changed'],'unexpected_new_items':row['unexpected_new_items']},ensure_ascii=False))
