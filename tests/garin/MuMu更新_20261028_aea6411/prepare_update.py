"""Freeze frontend and back up the existing MuMu app; no installation here."""
import datetime,hashlib,json,os,pathlib,re,shutil,subprocess,tarfile,xml.etree.ElementTree as ET
REPO=pathlib.Path(r'D:\Team_Project\Team-project')
ROUND=REPO/'tests/garin/MuMu更新_20261028_aea6411'
BACKUP=pathlib.Path(os.environ['LOCALAPPDATA'])/'GarinBackups/MuMu_20261028_aea6411'
ADB=[r'E:\Development\SDKs\Android\platform-tools\adb.exe','-s','emulator-5556']
GIT=['git','--no-optional-locks','-c','safe.directory='+REPO.as_posix(),'-C',str(REPO)]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def adb(*a):return subprocess.check_output(ADB+list(a))
if ROUND.exists() or BACKUP.exists():raise FileExistsError('Existing update/backup must not be overwritten')
head=subprocess.check_output(GIT+['rev-parse','HEAD'],encoding='utf8').strip()
if head!='aea6411d868ff30e64ab440239de8bbba7059f09':raise RuntimeError('Source baseline changed')
properties=adb('shell','getprop','ro.product.model').decode().strip()
if properties!='V2362A':raise RuntimeError('Unexpected target device')
pkg=adb('shell','dumpsys','package','com.example.teamapp').decode(errors='replace')
if 'versionCode=1 ' not in pkg or 'versionName=1.0' not in pkg:raise RuntimeError('Installed baseline changed')
credentials=ET.fromstring(adb('exec-out','run-as','com.example.teamapp','cat','shared_prefs/magicvvu_cloud_credentials.xml'))
if any(x.attrib.get('name')=='session' for x in credentials):raise RuntimeError('Cloud session appeared; pause before launching a cloud app')
ROUND.mkdir(parents=True);(ROUND/'evidence').mkdir();BACKUP.mkdir(parents=True)
(ROUND/'.gitignore').write_text('.snapshot/\n.runtime/\n*.apk\n__pycache__/\n*.pyc\n',encoding='utf8')
tracked=subprocess.check_output(GIT+['ls-files','-z']).decode('utf8').split('\0')
original={p:sha(REPO/p) for p in tracked if p and (REPO/p).is_file()}
status=subprocess.check_output(GIT+['status','--short'],encoding='utf8')
# Closing the app avoids a write racing the backup; no app data is removed.
subprocess.run(ADB+['shell','am','force-stop','com.example.teamapp'],check=True)
state_xml=adb('exec-out','run-as','com.example.teamapp','cat','shared_prefs/magicvvu_v1.xml')
tree=ET.fromstring(state_xml);state=json.loads(next(x.text for x in tree if x.attrib.get('name')=='state'))
if len(state['items'])!=15 or state['purchases']:raise RuntimeError('Expected 15 inventory records and no shopping entries')
write(BACKUP/'state-before.json',state)
archive=BACKUP/'app-data-before.tar'
with archive.open('wb') as f:subprocess.run(ADB+['exec-out','run-as','com.example.teamapp','tar','-cf','-','shared_prefs','files'],stdout=f,check=True)
with tarfile.open(archive) as t:
    members=t.getmembers()
    state_member=next(m for m in members if m.name=='shared_prefs/magicvvu_v1.xml')
    if t.extractfile(state_member).read()!=state_xml:raise RuntimeError('Backup state mismatch')
package_path=adb('shell','pm','path','com.example.teamapp').decode().strip().splitlines()[0].removeprefix('package:')
if not package_path.startswith('/data/app/') or not package_path.endswith('/base.apk'):raise RuntimeError('Unexpected installed APK path')
with (BACKUP/'installed-1.0.apk').open('wb') as f:subprocess.run(ADB+['exec-out','cat',package_path],stdout=f,check=True)
write(BACKUP/'backup-manifest.json',{'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'device':'emulator-5556','model':properties,'package':'com.example.teamapp','files':{p.name:sha(p) for p in BACKUP.iterdir() if p.is_file()},'inventory_count':15,'purchase_count':0,'photo_reference_count':sum(bool(i.get('image')) for i in state['items'])})
snapshot=ROUND/'.snapshot/frontend';snapshot.mkdir(parents=True)
hashes={}
for rel in tracked:
    if not rel.startswith('frontend/') or not (REPO/rel).is_file():continue
    parts=pathlib.PurePosixPath(rel).parts
    if any(x in {'.gradle','.cache','build','__pycache__'} for x in parts):continue
    if pathlib.PurePosixPath(rel).name.startswith('.env') or pathlib.PurePosixPath(rel).suffix in {'.keystore','.jks','.p12'}:continue
    target=ROUND/'.snapshot'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(REPO/rel,target);hashes[rel]=sha(target)
(snapshot/'local.properties').write_text('sdk.dir=E:/Development/SDKs/Android\n',encoding='utf8')
write(ROUND/'baseline.json',{'client_date':'2026-10-28','source_commit':head,'original_status':status,'tracked_source_hashes':original,'snapshot_hashes':hashes,'target_serial':'emulator-5556','target_model':properties,'package':'com.example.teamapp','version_before':'1.0','code_before':1,'inventory_before':15,'shopping_before':0,'cloud_session_present':False,'private_backup_directory':str(BACKUP),'backup_tar_sha256':sha(archive),'before_state_sha256':hashlib.sha256(json.dumps(state,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'photo_reference_count':sum(bool(i.get('image')) for i in state['items'])})
shutil.copy2(__file__,ROUND/'prepare_update.py')
print(json.dumps({'snapshot_files':len(hashes),'protected_tracked_files':len(original),'backup_bytes':archive.stat().st_size,'private_backup':str(BACKUP),'inventory_preserved':15,'cloud_session':False},ensure_ascii=False),flush=True)
# Existing global Gradle cache is read only; all new writes go to the round.
cache_source=pathlib.Path(r'E:\Development\Caches\Gradle')
cache_dest=ROUND/'.runtime/gradle-home'
counts={}
for rel in ['wrapper/dists/gradle-9.3.1-bin','caches/modules-2']:
    source=cache_source/rel;target=cache_dest/rel
    if not source.is_dir():continue
    src=pathlib.Path('\\\\?\\'+str(source.absolute()));dst=pathlib.Path('\\\\?\\'+str(target.absolute()))
    shutil.copytree(src,dst,ignore=shutil.ignore_patterns('*.lock','*.lck','*.part'),dirs_exist_ok=True)
    copied=[p for p in dst.rglob('*') if p.is_file()]
    counts[rel]={'files':len(copied),'bytes':sum(p.stat().st_size for p in copied)}
write(ROUND/'evidence/cache-preparation.json',{'source_read_only':str(cache_source),'copied':counts})
print(json.dumps({'private_gradle_cache_ready':True,'counts':counts},ensure_ascii=False),flush=True)
