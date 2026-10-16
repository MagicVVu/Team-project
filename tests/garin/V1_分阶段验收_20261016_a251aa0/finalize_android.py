import pathlib,json,shutil,xml.etree.ElementTree as ET,hashlib,sys
r=pathlib.Path(sys.argv[1]).resolve();e=r/'evidence';d=e/'android-unit-results';d.mkdir(exist_ok=True)
for x in (r/'.snapshot/frontend/app/build/test-results/testDebugUnitTest').glob('*.xml'):shutil.copy2(x,d/x.name)
cases=[c for p in d.glob('*.xml') for c in ET.parse(p).findall('.//testcase')]
failed=[c.attrib for c in cases if c.find('failure') is not None or c.find('error') is not None];skipped=[c.attrib for c in cases if c.find('skipped') is not None]
apk=r/'.snapshot/frontend/app/build/outputs/apk/debug/app-debug.apk'
result={'assembleDebug':{'status':'PASS','evidence':'evidence/android-assemble.log','apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'apk_bytes':apk.stat().st_size,'installed':False},'testDebugUnitTest':{'status':'PASS' if cases and not failed and not skipped else 'FAIL','total':len(cases),'pass':len(cases)-len(failed)-len(skipped),'fail':len(failed),'blocked':len(skipped),'evidence':'evidence/android-unit-results'},'lintDebug':{'status':'BLOCKED','classification':'环境问题','reason':'离线缓存缺少Compose desktop 1.7.0/1.3.0依赖，lintAnalyzeDebug未完成；不能登记Lint通过或无告警','evidence':'evidence/android-build.log'},'environment_repairs':['补齐Gradle私有缓存时使用Windows长路径支持','中文路径经临时V盘别名运行；任务结束已解除','仅本轮命令参数android.overridePathCheck=true；无构建文件修改'],'service_connected':False,'device_tests':'BLOCKED'}
(r/'results/Android结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
f=r/'results/问题分类.json';findings=json.loads(f.read_text(encoding='utf8'));findings.append({'id':'G-E02','status':'BLOCKED','classification':'环境问题','owner':'Garin 与 inHuman','summary':result['lintDebug']['reason'],'evidence':['evidence/android-build.log'],'next':'在隔离构建环境补齐依赖后单独重跑Lint；本轮未联网下载，不修改依赖版本'});f.write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
