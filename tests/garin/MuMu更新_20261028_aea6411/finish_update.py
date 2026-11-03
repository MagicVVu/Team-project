import hashlib,json,pathlib,subprocess,datetime,os
REPO=pathlib.Path(r'D:\Team_Project\Team-project')
ROOT=REPO/'tests/garin/MuMu更新_20261028_aea6411'
HANDOFF=REPO/'tests/交接文件夹/2026-10-28_MuMu最新版更新'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
baseline=read(ROOT/'baseline.json');apk=read(ROOT/'evidence/apk-verification.json');install=read(ROOT/'evidence/install-result.json');data=read(ROOT/'evidence/data-after-startup.json');startup=read(ROOT/'evidence/startup-result.json')
assert install['success'] and data['inventory_before']==data['inventory_after']==15
assert data['same_item_ids'] and not data['changed_original_item_ids'] and data['purchases_unchanged'] and data['other_original_preferences_unchanged']
assert not data['cloud_session_present'] and not startup['startup_crash_observed']
source_changed=[p for p,h in baseline['tracked_source_hashes'].items() if not (REPO/p).is_file() or sha(REPO/p)!=h]
snapshot_changed=[p for p,h in baseline['snapshot_hashes'].items() if sha(ROOT/'.snapshot'/p)!=h]
head=subprocess.check_output(['git','--no-optional-locks','-c','safe.directory='+REPO.as_posix(),'-C',str(REPO),'rev-parse','HEAD'],encoding='utf8').strip()
assert not source_changed and not snapshot_changed and head==baseline['source_commit']
integrity={'source_commit':head,'protected_tracked_files':len(baseline['tracked_source_hashes']),'changed_before_handoff_index_update':source_changed,'snapshot_inputs_checked':len(baseline['snapshot_hashes']),'changed_snapshot_inputs':snapshot_changed,'expected_following_owned_document_change':'tests/交接文件夹/README.md append update link only','checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
write(ROOT/'evidence/source-integrity.json',integrity)
notes=[{'stage':'offline build','type':'environment','resolution':'New CameraX/MLKit dependencies were not cached; kept offline failure and downloaded only declared dependencies; online assembleDebug passed.'},{'stage':'installation recorder','type':'harness','resolution':'The install and data checks succeeded; final self-copy of the running file failed. Added a same-path guard; did not reinstall.'},{'stage':'login UI selector','type':'harness','resolution':'Visible guest label includes an arrow (先逛逛 ›); navigation selector now accepts the label prefix. Business assertions unchanged; app not restarted again.'}]
write(ROOT/'evidence/adapter-notes.json',notes)
result={'date':'2026-10-28','status':'UPDATED_AND_STARTUP_VERIFIED','source_commit':head,'version_before':'1.0','version_after':apk['version_name'],'version_code':apk['version_code'],'app_package':apk['package'],'target_serial':apk['target_serial'],'apk_file':apk['apk'],'apk_sha256':apk['apk_sha256'],'apk_bytes':apk['apk_bytes'],'signature_matches_existing':True,'installed_apk_matches_built_artifact':True,'data_preservation':data,'startup':startup,'compiled_api_origin':apk['compiled_api_origin'],'compiled_isolated_flag':apk['cloud_expect_isolated'],'private_backup_directory':baseline['private_backup_directory'],'original_tracked_files_unchanged':True,'no_uninstall_or_clear':True,'cloud_business_acceptance':False,'jev_integrated_by_this_update':False,'paid_model_calls':0,'git_commit_or_push':False}
write(ROOT/'更新结果.json',result)
readme=f'''# MuMu最新版更新记录

日期：2026-10-28。更新归属：Garin测试工作。结果：覆盖安装与启动检查完成。

|项目|实际结果|
|---|---|
|源码基线|{head}|
|目标设备|MuMu Android12，emulator-5556，V2362A|
|安装版本|1.0 → {apk['version_name']}，versionCode {apk['version_code']}|
|包名|{apk['package']}|
|覆盖方式|同签名 adb install -r --no-streaming；未卸载、未清数据|
|安装包|{apk['apk']}，{apk['apk_bytes']:,}字节|
|APK SHA256|{apk['apk_sha256']}|
|设备实际APK|与本次构建产物哈希一致|
|数据|原15条库存完整，ID与原有字段不变；采购仍0条；照片引用仍0条|
|启动|登录页和游客首页可用，观察期间未发现启动崩溃|
|默认服务器地址|{apk['compiled_api_origin']}；本轮未登录或请求业务服务|

## 备份与文件保护

原应用的shared_prefs与files已打包保存在仓库外，另留旧APK与更新前后状态用于核对。私密备份位置：`{baseline['private_backup_directory']}`。不要把私密备份上传Git。

本轮核对了{len(baseline['tracked_source_hashes'])}个原跟踪文件及{len(baseline['snapshot_hashes'])}个隔离副本输入，内容未变化；只在自己的交接目录追加链接。未修改队友源码、构建配置、数据库或Jev配置，未提交或推送Git。APK本机保留，默认被本目录.gitignore排除，避免将大型构建文件混入提交。

## 构建与检查范围

从最新源码的隔离副本构建，使用本机SDK、JDK21、Gradle9.3.1及原调试签名。首次离线因相机/OCR依赖缺失停止；随后只下载已声明依赖，assembleDebug通过。没有更改依赖版本或屏蔽构建规则。

原仓库附带的10月25日APK与当前安装签名不同，且未包含之后的前端提交，因此没有使用该旧包。最终新包沿用已安装App的签名，覆盖后保留原firstInstallTime，lastUpdateTime更新。

本轮只做版本、签名、数据保留和启动检查，没有重跑全量单测/Lint，也没有测云端登录、业务事务、后端接入或模型质量。更新App不代表Jev已接入，付费模型调用为0。

## 证据

- [安装与版本核验](evidence/apk-verification.json)、[安装日志](evidence/install.log)、[设备包信息](evidence/package-after.txt)。
- [安装后数据检查](evidence/data-after-install.json)、[启动后数据检查](evidence/data-after-startup.json)。
- [登录页截图](evidence/login.png)、[游客首页截图](evidence/guest.png)、[启动结果](evidence/startup-result.json)。
- [离线构建日志](evidence/build-offline.log)、[联网构建日志](evidence/build-online.log)、[文件完整性](evidence/source-integrity.json)。
- [适配记录](evidence/adapter-notes.json)：安装记录脚本自复制与登录按钮文字定位问题均已修正，不计为App功能缺陷，也未因此重复安装。
'''
(ROOT/'README.md').write_text(readme,encoding='utf8')
if HANDOFF.exists():raise FileExistsError('Do not overwrite handoff')
HANDOFF.mkdir()
def link(p):return os.path.relpath(p,HANDOFF).replace('\\','/')
(HANDOFF/'README.md').write_text(f'''# MuMu最新版更新交接

2026-10-28，已将Garin的MuMu中Mewstow从1.0更新为 **{apk['version_name']}（versionCode {apk['version_code']}）**，源码基线`aea6411`。

- 本机原签名覆盖安装，原15条库存、采购记录及原有字段保持不变。
- 未卸载App、未清数据；私密备份存于仓库外。
- 安装后的APK哈希与本次隔离构建产物一致。
- 登录页与游客首页启动正常；当前停留在游客首页。
- 未登录云端、未写业务数据库、未调用模型。Jev接入和完整联合测试仍需单独验证。
- 本轮只做安装与启动检查，不把构建成功登记为业务验收通过。

[完整更新记录]({link(ROOT/'README.md')}) · [机器可读结果]({link(ROOT/'更新结果.json')}) · [最新游客首页截图]({link(ROOT/'evidence/guest.png')})

APK保存在本轮Garin目录，默认不加入Git。队友源码与旧测试记录保持原样，未自动提交或推送。
''',encoding='utf8')
index=REPO/'tests/交接文件夹/README.md'
index.write_text(index.read_text(encoding='utf8')+'\n## MuMu最新版更新\n\n[2026-10-28 MuMu覆盖更新与数据保留记录](2026-10-28_MuMu最新版更新/README.md)：更新到1.2.0-test，原15条记录保留，仅完成安装与启动检查。\n',encoding='utf8')
manifest={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and not set(p.relative_to(ROOT).parts)&{'.snapshot','.runtime','__pycache__'} and p.name!='文件校验.json'}
write(ROOT/'文件校验.json',{'files':manifest,'source_files_unchanged':True,'private_backups_excluded':True})
print(json.dumps({'version_after':apk['version_name'],'inventory_preserved':15,'source_files_unchanged':len(baseline['tracked_source_hashes']),'handoff':str(HANDOFF/'README.md'),'snapshot_untouched':True},ensure_ascii=False))
