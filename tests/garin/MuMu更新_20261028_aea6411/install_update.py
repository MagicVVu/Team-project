"""Verify the new APK then replace only the identified MuMu application."""
import datetime,hashlib,json,os,pathlib,re,shutil,subprocess,sys,xml.etree.ElementTree as ET
ROOT=pathlib.Path(r'D:\Team_Project\Team-project\tests\garin\MuMu更新_20261028_aea6411')
REPO=pathlib.Path(r'D:\Team_Project\Team-project')
ADB=[r'E:\Development\SDKs\Android\platform-tools\adb.exe','-s','emulator-5556']
ENV=os.environ.copy();ENV['JAVA_HOME']=r'E:\Development\SDKs\Java\jdk-21.0.12+8'
SIGNER=r'E:\Development\SDKs\Android\build-tools\37.0.0\apksigner.bat'
AAPT=r'E:\Development\SDKs\Android\build-tools\37.0.0\aapt2.exe'
EXPECTED='97a36a8dc4f60fcc931fc5ec413ce6e35baa795e601ea886fbc72fb25d40e921'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def adb(*a):return subprocess.check_output(ADB+list(a))
def state():
    tree=ET.fromstring(adb('exec-out','run-as','com.example.teamapp','cat','shared_prefs/magicvvu_v1.xml'))
    return json.loads(next(x.text for x in tree if x.attrib.get('name')=='state'))
def session_present():
    tree=ET.fromstring(adb('exec-out','run-as','com.example.teamapp','cat','shared_prefs/magicvvu_cloud_credentials.xml'))
    return any(x.attrib.get('name')=='session' for x in tree)
def compare(before,after):
    old={x['id']:x for x in before['items']};new={x['id']:x for x in after['items']}
    changes=[{'item_id':k,'fields':[f for f,v in item.items() if new.get(k,{}).get(f)!=v]} for k,item in old.items() if any(new.get(k,{}).get(f)!=v for f,v in item.items())]
    return {'inventory_before':len(old),'inventory_after':len(new),'missing_ids':sorted(set(old)-set(new)),'new_ids':sorted(set(new)-set(old)),'changed_original_fields':changes,'purchases_unchanged':before['purchases']==after['purchases'],'other_original_preferences_unchanged':all(after.get(k)==v for k,v in before.items() if k not in {'items','purchases'}),'cloud_session_present':session_present()}
baseline=json.loads((ROOT/'baseline.json').read_text(encoding='utf8'))
backup=pathlib.Path(baseline['private_backup_directory']);before=json.loads((backup/'state-before.json').read_text(encoding='utf8'))
source=ROOT/'.snapshot/frontend/app/build/outputs/apk/debug/app-debug.apk'
if not source.is_file():raise FileNotFoundError('Build must succeed first')
if (ROOT/'evidence/install-result.json').exists():raise FileExistsError('Do not repeat an installation recorded by this round')
assert not session_present(),'Cloud session appeared; pause'
assert all((REPO/k).is_file() and sha(REPO/k)==v for k,v in baseline['tracked_source_hashes'].items()),'Original files changed'
assert all(sha(ROOT/'.snapshot'/k)==v for k,v in baseline['snapshot_hashes'].items()),'Copied inputs changed'
original_check=compare(before,state());assert not original_check['changed_original_fields'] and not original_check['new_ids'] and not original_check['missing_ids']
verified=subprocess.run([SIGNER,'verify','--print-certs',str(source)],env=ENV,capture_output=True,text=True,encoding='utf8',errors='replace',check=True)
cert=re.search(r'certificate SHA-256 digest:\s*([a-fA-F0-9]+)',verified.stdout).group(1).lower()
if cert!=EXPECTED:raise RuntimeError('Signing mismatch; will not uninstall or clear data')
badging=subprocess.check_output([AAPT,'dump','badging',str(source)],encoding='utf8',errors='replace')
package=re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'",badging)
if package.groups()!=('com.example.teamapp','4','1.2.0-test'):raise RuntimeError('Unexpected app package/version')
buildconfig=ROOT/'.snapshot/frontend/app/build/generated/source/buildConfig/debug/com/example/teamapp/BuildConfig.java'
compiled=buildconfig.read_text(encoding='utf8');origin=re.search(r'CLOUD_API_URL\s*=\s*"([^"]*)"',compiled).group(1)
apk=ROOT/'Mewstow-aea6411-debug.apk';shutil.copy2(source,apk)
info={'source_commit':baseline['source_commit'],'target_serial':'emulator-5556','package':package.group(1),'version_name':package.group(3),'version_code':int(package.group(2)),'apk':apk.name,'apk_sha256':sha(apk),'apk_bytes':apk.stat().st_size,'certificate_sha256':cert,'signature_matches_existing':True,'compiled_api_origin':origin,'cloud_expect_isolated':'CLOUD_EXPECT_ISOLATED = true' in compiled,'used_default_build_configuration':True,'business_service_contacted':False,'models_called':False}
write(ROOT/'evidence/apk-verification.json',info)
result=subprocess.run(ADB+['install','-r','--no-streaming',str(apk)],capture_output=True,text=True,encoding='utf8',errors='replace')
(ROOT/'evidence/install.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
write(ROOT/'evidence/install-result.json',{'return_code':result.returncode,'success':result.returncode==0 and 'Success' in result.stdout,'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'uninstalled':False,'cleared_app_data':False})
if result.returncode or 'Success' not in result.stdout:raise RuntimeError('Overlay installation failed; old data not cleared; inspect log')
installed_path=adb('shell','pm','path','com.example.teamapp').decode().strip().splitlines()[0].removeprefix('package:')
h=hashlib.sha256()
with subprocess.Popen(ADB+['exec-out','cat',installed_path],stdout=subprocess.PIPE) as process:
    while chunk:=process.stdout.read(1024*1024):h.update(chunk)
    if process.wait():raise RuntimeError('Cannot read installed APK hash')
if h.hexdigest()!=info['apk_sha256']:raise RuntimeError('Installed APK does not match built artifact')
pkg=adb('shell','dumpsys','package','com.example.teamapp').decode(errors='replace')
(ROOT/'evidence/package-after.txt').write_text('\n'.join(s.strip() for s in pkg.splitlines() if any(k in s for k in ('versionCode=','versionName=','firstInstallTime=','lastUpdateTime=')))+'\n',encoding='utf8')
after=state();write(backup/'state-after-install.json',after)
checks=compare(before,after);checks['installed_apk_sha256']=h.hexdigest();checks['installed_apk_matches']=True
write(ROOT/'evidence/data-after-install.json',checks)
if checks['missing_ids'] or checks['new_ids'] or checks['changed_original_fields'] or not checks['purchases_unchanged'] or not checks['other_original_preferences_unchanged']:raise RuntimeError('Data preservation verification failed')
if pathlib.Path(__file__).resolve()!=(ROOT/'install_update.py').resolve():shutil.copy2(__file__,ROOT/'install_update.py')
print(json.dumps({'installed_version':'1.2.0-test','version_code':4,'certificate_matches':True,'apk_sha256':h.hexdigest(),'inventory_preserved':checks['inventory_after'],'data_changed':False,'api_origin':origin,'app_not_started_yet':True},ensure_ascii=False),flush=True)
