"""Build independently counted acceptance records from immutable raw outputs."""
import collections, datetime, hashlib, json, pathlib, subprocess, sys, xml.etree.ElementTree as ET
ROOT=pathlib.Path(sys.argv[1]).resolve()
if ROOT.name!='V1_分阶段验收_20261016_a251aa0' or ROOT.parent.name!='garin':raise ValueError('Wrong round')
E=ROOT/'evidence'; R=ROOT/'results'; R.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def jsonlines(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def jl(p,rows):p.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
baseline=read(ROOT/'baseline.json'); source=pathlib.Path(baseline['source'])
def git(*args):return subprocess.check_output(['git','--no-optional-locks','-c','safe.directory='+source.as_posix(),'-c','core.quotepath=false','-C',str(source),*args],encoding='utf-8').strip()
audit={}
for label,key,base in [('teammate_files','outside_round_tracked_hashes',source),('historical_garin','historical_garin_hashes',source),('snapshot_inputs','snapshot_sha256',ROOT/'.snapshot')]:
    diff=[k for k,v in baseline[key].items() if not (base/k).is_file() or sha(base/k)!=v]
    audit[label]={'checked':len(baseline[key]),'changed':diff}
audit.update(commit_before=baseline['commit'],commit_after=git('rev-parse','HEAD'),status_after=git('status','--short'),checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
audit['source_unchanged']=not any(audit[k]['changed'] for k in ('teammate_files','historical_garin','snapshot_inputs')) and audit['commit_before']==audit['commit_after']
write(E/'source-integrity.json',audit)
unit=[]
for label in ['ai-source','ai-source-corrected','backend-local','backend-reference-flow','garin-special']:
    path=E/label/'junit.xml';tree=ET.parse(path);cases=tree.findall('.//testcase')
    counts=collections.Counter('FAIL' if c.find('failure') is not None or c.find('error') is not None else 'BLOCKED' if c.find('skipped') is not None else 'PASS' for c in cases)
    unit.append({'suite':label,'total':len(cases),'counts':dict(counts),'evidence':str(path.relative_to(ROOT))})
native=[read(E/(p+'-'+s)/'summary.json') for p in ['p1','p2','p3','p5'] for s in ['dev','test']]
legacy=[];nonpass=[];old={(x['target'],x['id']):x for x in read(ROOT/'.snapshot/tests/garin/失败清单.json')}
for target in ['p0-regression','p1-regression','android-regression']:
    file=E/'p4-history/legacy'/target/'results.jsonl';rows=jsonlines(file)
    legacy.append({'suite':target,'total':len(rows),'counts':dict(collections.Counter(x['status'] for x in rows)),'evidence':str(file.relative_to(ROOT))})
    for line,x in enumerate(rows,1):
        if x['status']=='PASS':continue
        prior=old.get((target,x['id']),{});classify=prior.get('classification','待核对')
        if x['status']=='FAIL' and classify=='程序问题':classify='版本契约差异'
        nonpass.append({'phase':'P4','target':target,'id':x['id'],'version':baseline['commit'],'status':x['status'],'classification':classify,'input':prior.get('text') or x.get('evidence',{}).get('result',{}).get('original_text'),'expected':prior.get('expected'),'actual':x.get('evidence',{}).get('result'),'assertion_failures':x.get('failures',[]),'http':x.get('evidence',{}).get('http'),'before':x.get('evidence',{}).get('before'),'after':x.get('evidence',{}).get('after'),'evidence':str(file.relative_to(ROOT))+':'+str(line),'owner':prior.get('suggested_owner','MagicVVu 与 Garin 核对契约'),'note':'保留原状态和原断言；分类不能替代团队对契约的确认'})
jl(R/'旧用例非通过清单.jsonl',nonpass)
jl(R/'旧用例失败清单.jsonl',[x for x in nonpass if x['status']=='FAIL'])
special=jsonlines(E/'special_observations.jsonl')
for x in special:
    x.update(version=baseline['commit'],status='PASS',http=None,http_note='直接调用隔离对象，未经过HTTP，故不虚构HTTP状态',evidence='evidence/special_observations.jsonl')
    x['trace_id']=x.get('actual',{}).get('trace_id');x['request_id']=x['id'] if x['phase'] in ['P0','P1'] or x['id'] in ['G-P5-02','G-P5-03','G-P5-04','G-P5-05'] else None;x['task_id']=None
    if x['id']=='G-P5-01':x['request_id_note']='会话随机生成；原观察未存该字段，留空；同ID重放已由断言验证'
    if x['id']=='G-P5-06':x['request_id_note']='能力拒绝发生在HTTP前，无公开请求'
jl(R/'专项执行记录.jsonl',special)
verification=read(E/'p4-history/legacy/verification.json')
boundary=[x for x in verification['resolved'] if x['resolution']!='legacy_assertions_pass']
write(R/'历史84次程序问题对照.json',{'baseline':baseline['commit'],'total':84,'original_assertions_pass':81,'still_fail_contract_boundary':boundary,'raw_verifier_note':'开发方 verification.json 将这3条记为 resolved，并硬编码 tested_checkout_includes_uncommitted_p4_changes=true。本轮没有修改P4源码；以baseline和source-integrity为准，保留3条原FAIL。','rows':verification['resolved']})
deferred=[]
def pending(id,phase,owner,pre,steps,expected,dependency):
    deferred.append(dict(id=id,phase=phase,status='BLOCKED',classification='未实现功能' if dependency=='接口待实现' else '环境问题',owner=owner,version=baseline['commit'],precondition=pre,steps=steps,expected=expected,actual='未执行',http=None,trace_id=None,request_id=None,task_id=None,before=None,after=None,evidence=None,unblock=dependency))
pending('I-00','联调前置','inHuman 与 MagicVVu','独立服务与独立数据库；专用测试账号家庭','检查18081健康返回isolated_test=true，核对数据库标识、迁移版本、AI工厂、引擎及提交号；禁止访问18080','任一隔离或版本证明缺失则停止写操作','队友提供隔离环境及部署证明')
pending('I-01','账号家庭','inHuman','隔离服务、测试账号A/B、专用设备','登录A→退出→登录B；等待会话失效后继续请求','无效会话被拒绝；B看不到A缓存或家庭数据','隔离服务和专用设备')
pending('I-02','账号家庭','inHuman','独立家庭H1/H2','创建、加入、切换家庭；B直接访问H1资源；退出后离线打开','家庭数据隔离，越权拒绝，旧家庭缓存不泄漏','隔离服务和专用设备')
pending('I-03','游客数据','inHuman','专用模拟器游客模式，先建本地样例','游客录入→登录→切换账号；观察网络与列表','游客数据不未经确认自动上传，其他账号无旧缓存','隔离服务和专用设备')
pending('I-04','库存采购','inHuman','同一家庭，无牛奶记录','录入2盒→消耗0.5盒→计划采购2盒→实买1.5盒→刷新App与服务端','旧批1.5盒，新批1.5盒，总计3盒；采购历史保留','隔离服务和专用设备；SQLite本地参考闭环已通过但不代替此项')
pending('I-05','库存采购','inHuman','已购项与同一operation_id','重复采购请求；同operation_id重复消耗；刷新并重启App','重复请求不再次入库或扣减，状态一致','隔离服务与PostgreSQL')
pending('I-06','冲突重试','inHuman','两测试成员读取同一库存版本','成员A先修改，B持旧版本修改；断网后重连、刷新后再操作','旧版本409；无静默覆盖；同操作ID不会重复扣减','两客户端与独立PostgreSQL')
pending('I-07','数据库并发','inHuman','空白专用PostgreSQL名含_test；隔离标识就绪','由后端负责人按check_shopping_postgres.py前提执行并发采购、失败回滚，保存事务前后状态','只有一次入库；真实行锁与回滚符合脚本断言','独立PostgreSQL及负责人确认；不得用SQLite替代')
pending('I-08','AI任务','inHuman 与 MagicVVu','实际AI入口版本确认；存在只读上下文','发消息→读取任务→补充澄清→读取草稿；前后查库存采购','任务可恢复；草稿本身不写库存采购，跨家庭任务不可见','隔离服务和专用设备')
pending('I-09','P1正式事务','inHuman 与 MagicVVu','正式草稿确认、开封、移动、丢弃、撤销接口','逐一执行确认与撤销；查询事件数量和版本','移动/开封不改数量，丢弃与消费分开，事务失败可回滚','接口待实现')
pending('I-10','P2正式链路','MagicVVu 与 inHuman','运行服务明确切到P2或兼容入口','多批次风险与原因查询；缺标签日期、保存条件及规则','事实、来源、规则版本齐全；不把冰箱位置当温度、不保证安全','当前隔离脚本默认P1；需部署P2兼容入口')
pending('I-11','P3正式链路','MagicVVu 与 inHuman','完整消费事件、时区及待购物资规划接口','固定时点运行28日7盒、库存2盒、待购1盒；同名选择后续接','日均0.25，剩余8日，新建议1盒；依据可持久化','接口待实现')
pending('I-12','P5公开协议','MagicVVu 与 inHuman','确认公开字段契约及能力标识','测试空答案和item_key澄清能力；检查请求体','不把P5内部input来源字段塞进现有4字段公开消息体','接口待实现')
pending('I-13','P5设备输入','inHuman 与 MagicVVu','专用设备与已部署P5入口','语音99盒→编辑2盒→确认；取消输入；连续识别、迟到回调、后台回来','只提交最终2盒；取消无业务撤销；旧回调不覆盖新文字','设备、麦克风及P5集成')
pending('I-14','P5网络恢复','inHuman 与 MagicVVu','可控制断网的隔离设备','POST后断网→恢复→读取task；反复点击确认','超时不自动重复POST；先读任务再决定下一步','隔离服务和专用设备')
pending('I-15','UI拉绳动画','summerdong2006-dot 与 inHuman','专用设备，记录屏幕与日志','短拉、取消、连续开关、动画时点背景、切页返回、前后台切换','状态恢复，离场区域不能误触；无重复开启或遮挡点击','专用设备及人工操作')
pending('I-16','UI文字录入','summerdong2006-dot 与 inHuman','模拟语音失败、浅色深色界面','识别失败后手动输入；键盘弹出；切换页面及旋转恢复','可编辑再确认，文字不丢失、无界面遮挡','专用设备及人工操作')
pending('M-01','P5真实模型','MagicVVu','先说明费用与预算，明确模型版本','重跑历史p5-42-1并保存原始输出和错误；按锁定数据另开模型轮次','原历史FAIL保留，新轮次单列，不用规则通过抵消模型失败','模型调用费用需先说明后安排，本轮零付费调用')
pending('R-01','样本复核','Garin 与团队','原150条人工复核状态以文件为准','确认漏标位置及创可贴快用完了的意图表示','不代签人工复核；缺信息先澄清，标签规范由团队决定','待团队人工确认；独立记录REVIEW')
deferred[-1]['status']='REVIEW';deferred[-1]['classification']='样本标注问题'
jl(R/'联调待办.jsonl',deferred)
md=['# 联调待办与操作步骤','','所有BLOCKED项尚未执行。先完成I-00，再按编号执行。每项需另存HTTP状态、trace/request/task ID及操作前后状态；账号令牌和私有上下文不进入公开附件。','','|编号|阶段|状态|对接人|','|---|---|---|---|']
md += [f"|{x['id']}|{x['phase']}|{x['status']}|{x['owner']}|" for x in deferred]
for x in deferred:
    md += ['',f"## {x['id']} {x['phase']}",'',f"前提：{x['precondition']}",'',f"步骤：{x['steps']}",'',f"预期：{x['expected']}",'',f"解除阻塞条件：{x['unblock']}"]
(ROOT/'联调待办.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
write(R/'分阶段统计.json',{'baseline':baseline['commit'],'first_batch_only':True,'source_integrity':audit['source_unchanged'],'pytest':unit,'native_datasets':native,'legacy':legacy,'legacy_program_assertions_pass':81,'legacy_program_contract_fail':3,'special_pytest_cases':22,'special_evidence_records':len(special),'pending':dict(collections.Counter(x['status'] for x in deferred)),'paid_provider_calls':0,'note':'各表重叠，不跨表求总通过率；rules评测字段model_calls表示规则提取次数，不是付费模型调用。'})
findings=[
 {'id':'G-F01','status':'FAIL','classification':'测试程序问题','owner':'MagicVVu','summary':'P5整段JSON搜索99会被随机UUID误触发；首轮实际失败，后续随机复跑通过不代表测试已修好','evidence':['evidence/ai-source/junit.xml','evidence/p5-uuid-diagnostic.json'],'next':'由AI负责人改为断言最终text及禁止raw_transcript字段，并使用固定含99的ID验证；本轮不改队友文件'},
 {'id':'G-E01','status':'PASS','classification':'环境问题 已修复','summary':'隔离副本原漏deploy/compose.p2.override.yaml，已补齐同源原文件，未修改预期','evidence':['evidence/ai-source/junit.xml','evidence/ai-source-corrected/junit.xml','baseline.json']},
 {'id':'G-C01','status':'FAIL','classification':'版本契约差异或接口限制','summary':'旧P1保留19FAIL，旧Android快照网关保留18FAIL；逐条记录见旧用例失败清单；不得合并算成新程序失败，也不得转PASS','evidence':['results/旧用例失败清单.jsonl']},
 {'id':'G-C02','status':'FAIL','classification':'版本契约差异','summary':'旧84次程序问题中81条原断言PASS，另3条仍FAIL：P1 p0-41-2终止批次状态，Android ext-013/ext-015未注册采购品','evidence':['results/历史84次程序问题对照.json']},
 {'id':'G-M01','status':'FAIL','classification':'历史模型程序问题 本轮未复测','owner':'MagicVVu','summary':'历史p5-42-1模型失败保留；本轮规则通过不能消除历史模型FAIL','evidence':['.snapshot/agent/eval/p5/results 如未提交则查交接说明；本轮未保留任何新模型输出'],'next':'完成费用说明后另开真实模型轮次'},
 {'id':'G-R01','status':'REVIEW','classification':'样本标注问题','summary':'原150条人工复核未代签；位置漏标与创可贴快用完了意图歧义继续待确认，旧目标各18REVIEW不跨目标去重相加','evidence':['results/旧用例非通过清单.jsonl']},
]
# Reference actual committed model handoff documentation, never invent a model output file.
modeldocs=[p.relative_to(ROOT).as_posix() for p in (ROOT/'.snapshot').rglob('*.md') if 'p5-42-1' in p.read_text(encoding='utf-8',errors='ignore')]
findings[4]['evidence']=modeldocs
write(R/'问题分类.json',findings)
# Only synthetic HTTP responses are captured; request authorization headers are intentionally omitted.
for env in ['ai','backend']:
    exe=ROOT/'.runtime'/env/'Scripts/python.exe'
    with (E/f'packages-{env}.txt').open('w',encoding='utf-8') as f:subprocess.run([str(exe),'-m','pip','freeze'],stdout=f,check=True)
print(json.dumps({'source_unchanged':audit['source_unchanged'],'unit':unit,'legacy':legacy,'special_records':len(special),'nonpass':len(nonpass),'deferred':len(deferred)},ensure_ascii=False,indent=2))
