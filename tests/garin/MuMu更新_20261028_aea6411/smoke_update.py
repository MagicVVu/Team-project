"""Native Android startup inspection; no cloud sign-in or business requests."""
import datetime,json,pathlib,re,subprocess,sys,time,xml.etree.ElementTree as ET
ROOT=pathlib.Path(r'D:\Team_Project\Team-project\tests\garin\MuMu更新_20261028_aea6411')
ADB=[r'E:\Development\SDKs\Android\platform-tools\adb.exe','-s','emulator-5556']
def adb(*args):return subprocess.check_output(ADB+list(args))
def capture(label):
    device_file='/sdcard/garin_update_20261028_aea6411_ui.xml'
    for attempt in range(3):
        done=subprocess.run(ADB+['shell','uiautomator','dump',device_file],capture_output=True)
        if done.returncode==0 and b'dumped to:' in done.stdout:break
        time.sleep(.7)
    else:raise RuntimeError('Unable to capture Android UI')
    raw=adb('exec-out','cat',device_file)
    (ROOT/f'evidence/{label}-ui.xml').write_bytes(raw)
    with (ROOT/f'evidence/{label}.png').open('wb') as f:subprocess.run(ADB+['exec-out','screencap','-p'],stdout=f,check=True)
    tree=ET.fromstring(raw)
    return tree,[n.attrib.get('text','') for n in tree.iter('node') if n.attrib.get('text')]
mode=sys.argv[1]
if mode=='login':
    creds=ET.fromstring(adb('exec-out','run-as','com.example.teamapp','cat','shared_prefs/magicvvu_cloud_credentials.xml'))
    if any(n.attrib.get('name')=='session' for n in creds):raise RuntimeError('Unexpected cloud session; do not start')
    result=subprocess.run(ADB+['shell','am','start','-W','-a','android.intent.action.MAIN','-c','android.intent.category.LAUNCHER','-n','com.example.teamapp/.MainActivity'],capture_output=True,text=True,encoding='utf8',errors='replace')
    (ROOT/'evidence/launch.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
    if result.returncode:raise RuntimeError('App launch failed')
    tree,texts=capture('login')
    assert any(t.startswith(('先逛逛','Explore','以游客身份体验','Continue as guest')) for t in texts),texts
    print(json.dumps({'stage':'login','visible_text':texts,'pid':adb('shell','pidof','com.example.teamapp').decode().strip()},ensure_ascii=False))
elif mode=='guest':
    original=ET.parse(ROOT/'evidence/login-ui.xml')
    target=next(n for n in original.iter('node') if n.attrib.get('text','').startswith(('先逛逛','Explore','以游客身份体验','Continue as guest')))
    x1,y1,x2,y2=map(int,re.findall(r'\d+',target.attrib['bounds']))
    subprocess.run(ADB+['shell','input','tap',str((x1+x2)//2),str((y1+y2)//2)],check=True)
    tree,texts=capture('guest')
    assert any(t in {'首页','Home'} for t in texts) and any(t in {'库存','Inventory'} for t in texts),texts
    pid=adb('shell','pidof','com.example.teamapp').decode().strip()
    if not pid:raise RuntimeError('App process not running')
    logs=subprocess.check_output(ADB+['logcat','-d','-t','1600','--pid',pid],encoding='utf8',errors='replace')
    (ROOT/'evidence/startup-app.log').write_text(logs,encoding='utf8')
    crash=bool(re.search(r'FATAL EXCEPTION|Fatal signal|ANR in com\.example\.teamapp',logs))
    if crash:raise RuntimeError('Crash observed in new app process')
    result={'login_page_verified':True,'guest_home_verified':True,'pid':pid,'startup_crash_observed':crash,'cloud_login_performed':False,'business_writes_performed':False,'model_calls':0,'native_android_ui_only':True,'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (ROOT/'evidence/startup-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'stage':'guest','visible_text':texts,'result':result},ensure_ascii=False))
else:raise ValueError('Choose login or guest')
