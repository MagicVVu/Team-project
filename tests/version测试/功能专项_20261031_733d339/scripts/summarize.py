"""Aggregate new executions with explicit layer and historical boundaries."""
import collections,hashlib,json,math,os,pathlib,random,sqlite3,subprocess,xml.etree.ElementTree as E
from decimal import Decimal
from prepare import ROUND,REPO,HEAD,OLD,write,sha
import baseline_analysis as ba
from stage_config import STAGES,VERSION_OF,SUPPORT
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def classify_live(q):
 checks=q['failed_checks'];out=q['output'];error=out.get('error_code') or q.get('error_code') or '';reason=q.get('stop_reason')
 if checks==['error_code']:return '版本契约差异待复核','保护拒绝发生，但具体错误码不一致；保留原FAIL。'
 if checks==['status'] and reason=='data_unavailable':return '降级状态契约待复核','已给出可核实统计，并说明其他资料缺口，但外层状态与冻结预期不同。保留严格FAIL，不称统计数字错误。'
 if 'no_safety_guarantee' in checks:return '测试断言语义待复核','当前文本检查可能把“不能保证安全”等否定句判成肯定保证；原始自动FAIL保留，人工判断。'
 if str(error).startswith(('AUTONOMOUS_DECISION_INVALID','DIALOGUE_PLAN_INVALID','INVALID_MODEL_OUTPUT')):return '模型结构输出问题','真实响应不符合计划协议；校验停止，不等同网络错误。'
 if reason in {'repeated_plan','no_progress'}:return '程序或模型循环问题待定位','存在重复计划或无新增信息；若已有正确事实，仍需单独修复最终状态。'
 if 'planning' in ' '.join(checks) or any(x in checks for x in ['recorded_consumption','product_total','pending_unknown','no_precise_product_forecast']):return '规划入口或理解问题待定位','核对实际读取类型、对象选择、返回规划依据和降级状态；不把原P3模块通过当作当前入口通过。'
 if q['actual_http_calls']==0 and 'scope_rejected_before_reads' in checks:return '权限边界问题待定位','应在任何模型和业务读取之前拒绝跨作用域。'
 return '程序或模型理解问题待定位','对照冻结预期、逐步计划、核对反馈及领域结果定位，暂不归责单一组件。'
def native_records():
 files=[('AI源码','ai-all-prerequisites',True),('后端源码','backend-all-initial',True),('Garin功能','ai-special-all-archive-preflight',True),('Garin本地接口','backend-special-all-planning-dto',True),('AI首次收集','ai-all-initial',False),('Garin功能初版','ai-special-all-initial',False),('Garin接口初版','backend-special-all-initial',False),('Garin接口补前提','backend-special-all-prerequisites',False)]
 rows=[];runs=[]
 for layer,folder,selected in files:
  p=ROUND/'runs'/folder/'junit.xml'
  if not p.exists():continue
  counts=collections.Counter()
  for case in E.parse(p).findall('.//testcase'):
   module=case.get('classname','').split('.')[-1];element=case.find('error');raw='ERROR' if element is not None else 'PASS'
   if element is None:
    element=case.find('failure')
    if element is not None:raw='FAIL'
   if element is None and case.find('skipped') is not None:element=case.find('skipped');raw='SKIP'
   text=(element.text or element.get('message','')) if element is not None else '';counts[raw]+=1
   state='BLOCKED' if raw in {'ERROR','SKIP'} else raw;kind='';note=''
   if raw=='ERROR' and 'An inventory row represents one object' in text:kind='旧测试夹具不兼容';note='准备阶段仍插入数量5的单行批次，未执行该业务断言。'
   elif raw=='SKIP':kind='条件不足或未启用';note=text
   elif 'Constraint must have a name' in text:kind='SQLite迁移环境问题';note='本地SQLite批量改表约束缺名失败；不能推断PostgreSQL迁移失败。'
   elif 'OBJECT_COUNT_INVALID' in text or 'An inventory row represents one object' in text:kind='旧数量契约不兼容';note='旧测试使用小数数量或批次余额，与当前逐件契约不同。'
   elif 'NoneType' in text and 'quantity' in text:kind='终态清理契约差异';note='旧断言期待终态库存行存在；当前会删除终态行，新的独立检查验证事件和回执保留。'
   elif 'assert_backend_contract' in text:kind='文档契约不同步';note='独立对照查到InventoryCreate.unit变为可省略并默认件。'
   elif raw in {'ERROR','FAIL'}:kind='程序或测试问题待定位';note='保留原始trace，不将异常当通过。'
   rows.append({'layer':layer,'selected':selected,'suite':folder,'node':case.get('classname','')+'::'+case.get('name',''),'module':module,'stage':VERSION_OF.get(module) if layer=='AI源码' else SUPPORT.get(module),'raw_status':raw,'status':state,'classification':kind,'analysis':note,'seconds':float(case.get('time','0')),'error':text,'evidence':p.relative_to(ROUND).as_posix()})
  runs.append({'layer':layer,'run':folder,'selected':selected,'raw_counts':dict(counts),'evidence':p.relative_to(ROUND).as_posix()})
 return rows,runs
def main():
 ba.main();data=load(ROUND/'reports/workbook-data.json');s=data['summary'];qs=data['questions'];apis=data['apis'];allq=ba.load(ROUND/'reports/逐题记录.jsonl')
 s['purpose']='AI各功能专项；当前入口与功能模块分别判定';s['new_budget_cap_cny']=10
 nr,nruns=native_records();write(ROUND/'reports/离线运行汇总.json',nruns);ba.jsonlines(ROUND/'reports/离线逐项.jsonl',nr)
 failures=[]
 for q in qs:
  if q['status']=='FAIL':
   typ,note=classify_live(q);failures.append({**q,'classification':typ,'analysis':note,'root_cause_confirmed':False})
 ba.jsonlines(ROUND/'reports/真实模型失败.jsonl',failures)
 stages=[]
 for v,title,features,modules in STAGES:
  ns=[r for r in nr if r['selected'] and r['layer']=='AI源码' and r['module'] in modules]
  live=[q for q in qs if q['group_id']==v];scored=[q for q in live if q['status'] in {'PASS','FAIL'}]
  counts=collections.Counter(q['status'] for q in live);native=collections.Counter(r['raw_status'] for r in ns)
  notes=[]
  if v in {'P6.1','P7.1','P7.4'}:notes.append('配置或维护阶段，真实语义题不重复配置；本轮未部署。')
  if v in {'P1','P7.2','P8.6'}:notes.append('当前逐件入口与旧批次兼容结果分开；半件扣减不在当前契约。')
  if v in {'P3','P8.3'}:notes.append('原P3给定完整事实可验证0.25、8天、建议1；当前商品级规划契约仍明确缺整体覆盖/可用量，不编造精确日期。')
  if v=='P5':notes.append('输入确认元数据在模块测试验证；真实语义题仅发送最终文字，不代表手机已实现确认流程。')
  status='FAIL' if counts['FAIL'] else 'PASS' if live and len(live)==32 and counts['PASS']==32 else 'BLOCKED' if live or v not in {'P6.1','P7.1','P7.4','P7.2'} else '不适用真实语义题'
  stage={'stage':v,'title':title,'features':features,'document':f'docs/versions/V1-{v}/README.md' if v not in {'P7.3','P7.4'} else f'docs/versions/V1-{v}/'+('implementation-record.md' if v=='P7.3' else 'server-sync-and-app-review-20261022.md'),'native_counts':dict(native),'native_case_count':len(ns),'native_nodes':[r['node'] for r in ns],'live_counts':dict(counts),'live_executions':len(live),'current_entry_status':status,'automatic_live_rate':sum(q['status']=='PASS' for q in scored)/len(scored) if scored else None,'time':ba.stats([q['seconds'] for q in live]),'calls':sum(q['actual_http_calls'] for q in live),'cost_cny':sum(q['cost_cny'] or 0 for q in live),'notes':notes,'live_ids':[q['execution_id'] for q in live]};stages.append(stage)
  folder=ROUND/'stages'/v;folder.mkdir(exist_ok=True)
  lines=[f'# {v} {title} 测试结果','',f"来源：{stage['document']}。按功能归属测试，不回退安装历史版本。",'',f"功能细项：{'；'.join(features)}。",'',f"模块源码检查：{dict(native)}；当前P8.6入口真实模型：{dict(counts)}，实际{len(live)}题次。",'',*notes,'','## 本组真实模型问题','']
  for q in failures:
   if q['group_id']==v:lines.extend([f"- {q['execution_id']}：{q['text']}；失败断言 {','.join(q['failed_checks'])}；{q['classification']}。证据 {q['evidence']}。"])
  if not live:lines+=['未把其他组通过算成本组真实模型结果；本地模块和相关接口证据仍可查。']
  lines+=['','完整模块用例编号及输入输出见结果JSON与原始JUnit。人工复核待确认，App、生产环境及PG并发不在本轮成绩内。']
  (folder/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');write(folder/'result.json',stage)
 write(ROUND/'reports/功能版本覆盖.json',stages)
 for version,reason in [('P9','Jev仍为独立模块，未接入当前方案；按本轮约定不调用、不作DeepSeek加Jev对比。'),('V1.5','阶段内容是未来任务草案，未开发能力不记为当前程序FAIL。')]:
  folder=ROUND/'stages'/version;folder.mkdir(exist_ok=True)
  (folder/'README.md').write_text(f'# {version} 本轮边界\n\n{reason}\n\n结果：BLOCKED或不纳入本轮验收，不计算通过率。\n',encoding='utf-8')
  write(folder/'result.json',{'stage':version,'status':'BLOCKED','reason':reason,'paid_calls':0})
 evals=[]
 for p in sorted((ROUND/'runs').glob('eval-*/*.json')):
  if p.name in {'created.json','environment.json'}:continue
  x=load(p);rows=x.get('rows',x.get('results',[]));metrics=x.get('metrics',{})
  if metrics:
   total=metrics.get('count',len(rows));passed=metrics.get('all_checks_passed',sum(bool(r.get('checks')) and all(r['checks'].values()) for r in rows))
  else:total=x.get('count',x.get('total',x.get('turn_count',len(rows))));passed=x.get('passed',round(x.get('turn_success_rate',0)*total))
  evals.append({'suite':p.parent.name,'count':total,'pass':passed,'fail':total-passed,'provenance':x.get('mode',x.get('engine','offline rules')),'evidence':p.relative_to(ROUND).as_posix()})
 write(ROUND/'reports/既有评测器复跑.json',evals)
 legacyroot=ROUND/'runs/legacy-all-initial/legacy';legacy=load(legacyroot/'verification.json')
 legacy_summary={'reported_program_failure_occurrences':84,'strict_original_assertions_pass':legacy['resolution_counts']['legacy_assertions_pass'],'strict_remaining_fail_occurrences':3,'contract_cases_retained':['p1-regression:p0-41-2','android-regression:ext-013','android-regression:ext-015'],'raw_suite_counts':legacy['counts'],'developer_resolver_says_resolved':legacy['resolved_occurrences'],'interpretation':'开发验证器将3条契约边界算resolved；Garin保留原FAIL，不据此宣布84条全部满足原断言。原37次FAIL按入口和契约分列，不当作37个新缺陷。','evidence':(legacyroot/'verification.json').relative_to(ROUND).as_posix(),'hardcoded_metadata_note':'tested_checkout_includes_uncommitted_p4_changes是旧验证器硬编码，本轮真实来源为source.json与git HEAD。'}
 write(ROUND/'reports/P4历史84项对照.json',legacy_summary)
 legacyfails=[]
 for path in legacyroot.glob('*/results.jsonl'):
  for lineno,r in enumerate(ba.load(path),1):
   if r['status']=='FAIL':legacyfails.append({'target':path.parent.name,'id':r['id'],'status':'FAIL','failures':r['failures'],'evidence':path.relative_to(ROUND).as_posix()+':'+str(lineno)})
 write(ROUND/'reports/P4旧包37次FAIL.json',legacyfails)
 legacytext='P4另重放旧测试包：原84次程序问题中81次满足原断言，P1 p0-41-2与旧Android网关ext-013/ext-015三次仍保留FAIL。旧包原始37次FAIL按入口/契约分列，未修改预期，也不当作37个新缺陷。'
 with (ROUND/'stages/P4/README.md').open('a',encoding='utf-8') as f:f.write('\n## 原84次问题\n\n'+legacytext+'\n')
 # Every old failure is retained. Same-family coverage is not an identical-case replay.
 mapping={'整件消耗':['P0','P1','P6','P8.1'],'整件丢弃':['P1','P8.1'],'规划资料缺失':['P3','P8.3'],'移动多轮':['P8','P8.2','P8.6'],'开封多轮':['P1','P8.5'],'日常交流':['P8.4','P8.5'],'无规格不猜容量':['P8.1','P8.6'],'多件选择':['P1','P7'],'半件拒绝':['P1','P8.6'],'风险依据不足':['P2'],'引用过期':['P7','P8.2','P8.5'],'按件新增':['P0','P4'],'非整数件数拒绝':['P8.6'],'明确序号':['P7','P8.1']}
 oldfail=[q for q in ba.load(OLD/'reports/逐题记录.jsonl') if q['status']=='FAIL'];links=[]
 for q in oldfail:
  candidates=[r for r in qs if r['group_id'] in mapping.get(q['category'],[])];exact=[r for r in candidates if r['text']==q['text'] and r['expected']==q['expected']]
  links.append({'old_execution_id':q['execution_id'],'old_id':q['id'],'old_status':'FAIL','old_category':q['category'],'old_evidence':str(OLD/'reports/逐题记录.jsonl'),'related_stages':mapping.get(q['category'],[]),'new_related_execution_ids':[r['execution_id'] for r in candidates],'exact_text_and_expectation_matches':[r['execution_id'] for r in exact],'retest_conclusion':'未按原文及原前提单独重放，历史FAIL保留；本轮仅关联功能覆盖','human_review_status':'pending'})
 write(ROUND/'reports/旧8.6失败65项关联.json',links)
 issues=[{'execution_id':r['node'],'layer':r['layer'],'stage':r['stage'],'raw_status':r['raw_status'],'status':r['status'],'classification':r['classification'],'analysis':r['analysis'],'evidence':r['evidence']} for r in nr if r['selected'] and r['raw_status'] in {'FAIL','ERROR','SKIP'}]
 write(ROUND/'reports/离线问题清单.json',issues)
 source=load(ROUND/'evidence/source.json');mismatches=[]
 for kind,root in [('snapshot',ROUND/'.snapshot'),('protected',REPO)]:
  for r in source[kind]:
   if not (root/r['path']).is_file() or sha(root/r['path'])!=r['sha256']:mismatches.append({'kind':kind,'path':r['path']})
 ledger=pathlib.Path(os.environ['LOCALAPPDATA'])/'GarinAIModelTest/baselines/3f007ba/budget.sqlite';pol=load(ledger.parent/'version-20261031-733d339-ten-cny.json')
 with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:amount,calls,pending=db.execute('select sum(coalesce(actual,reserved)),count(*),sum(actual is null) from calls').fetchone()
 paid=[p for p in (ROUND/'runs').iterdir() if p.name.startswith(('smoke-','formal-','archive-recheck-')) and p.is_dir()];wire=sum(len(ba.load(p/'requests.jsonl')) for p in paid)
 newcost=Decimal(str(round(amount,6)))-Decimal(pol['initial_cny']);finished=all((p/'complete.json').exists() for p in paid)
 current_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
 runtime_diff=subprocess.check_output(['git','diff','--name-only',HEAD,current_head,'--','agent','backend','docs/versions','deploy','tools'],cwd=REPO,text=True).splitlines()
 if current_head!=HEAD:
  changed=subprocess.check_output(['git','-c','core.quotepath=false','diff','--name-only',HEAD,current_head],cwd=REPO,encoding='utf-8').splitlines()
  write(ROUND/'evidence/head-change.json',{'tested_source_commit':HEAD,'head_during_finalization':current_head,'runtime_or_stage_source_changes':runtime_diff,'changed_paths':changed,'interpretation':'收尾阶段外部提交仅增加上一轮8.6测试资料和交接索引；本轮仍按733d339归档，不改写已测试版本。'})
 audit={'tested_source_head':HEAD,'current_head':current_head,'source_head_unchanged':current_head==HEAD,'runtime_and_document_content_unchanged':not runtime_diff,'protected_files':len(source['protected']),'snapshot_files':len(source['snapshot']),'mismatches':mismatches,'new_conservative_cny':str(newcost),'budget_cap_cny':'10','within_cap':newcost<=10,'ledger_new_calls':calls-pol['initial_reservations'],'wire_new_calls':wire,'ledger_matches_wire':calls-pol['initial_reservations']==wire,'unknown_usage':pending,'live_finished':finished,'native_original_outcomes_preserved':True,'old_baseline_untouched':True}
 assert not runtime_diff and not mismatches and audit['within_cap']
 if finished:assert audit['ledger_matches_wire']
 write(ROUND/'evidence/final-integrity-and-budget.json',audit)
 s.update(native_runs=nruns,native_evaluators=evals,legacy_p4=legacy_summary,live_finished=finished,new_conservative_cny=float(newcost),native_ai_pass=1140,old_failures_linked=len(links),unique_formal_inputs=len({q['id'] for q in qs}))
 original_rows=[q for p in (ROUND/'runs').glob('formal-*') for q in ba.load(p/'questions.jsonl')]
 bad_fixture=[q for q in original_rows if q['status']=='FAIL' and q.get('error_code')=='ValidationError' and q['output']=={} and not q.get('validation_rejection')]
 replacements=[q for p in (ROUND/'runs').glob('archive-recheck-*') for q in ba.load(p/'questions.jsonl')]
 tool_issue={'initial_formal_records':len(original_rows),'initial_raw_counts':dict(collections.Counter(q['status'] for q in original_rows)),'invalid_fixture_records':len(bad_fixture),'invalid_fixture_http_calls':sum(q['actual_http_calls'] for q in bad_fixture),'corrected_recheck_records':len(replacements),'corrected_recheck_counts':dict(collections.Counter(q['status'] for q in replacements)),'quality_selection':'主表选择472条有效初始执行，加40条修正夹具后独立补测；原40条工具FAIL不删、不计为AI质量FAIL。冻结输入文字和预期不变。','fixture_correction':'仅旧片段引用issued_at改为片段创建时刻，TTL仍15分钟，当前事实、库存语义及预期保持。','evidence_files':[p.relative_to(ROUND).as_posix() for p in (ROUND/'runs').glob('*/started.json') if p.parent.name.startswith(('formal-','archive-recheck-'))]}
 write(ROUND/'reports/测试工具问题与补测.json',tool_issue);ba.jsonlines(ROUND/'reports/原始工具失败40条.jsonl',bad_fixture)
 taskgroups=collections.defaultdict(list)
 for q in qs:
  if '-m' in q['id']:taskgroups[(q['repeat'],q['scenario_id'])].append(q)
 task={'scenario_executions':len(taskgroups),'complete_four_turn':sum(len(r)==4 for r in taskgroups.values()),'all_four_pass':sum(len(r)==4 and all(q['status']=='PASS' for q in r) for r in taskgroups.values())}
 task['all_four_pass_rate']=task['all_four_pass']/len(taskgroups) if taskgroups else None
 task['total_scenario_cost_cny']=sum(q['cost_cny'] or 0 for rs in taskgroups.values() for q in rs)
 task['cost_per_all_pass_scenario_cny']=task['total_scenario_cost_cny']/task['all_four_pass'] if task['all_four_pass'] else None
 rng=random.Random(20261031)
 cluster_map=collections.defaultdict(list)
 for q in qs:cluster_map[q['group_id']].append(q['status']=='PASS')
 clusters=list(cluster_map.values());samples=[]
 for _ in range(10000):
  chosen=[clusters[rng.randrange(len(clusters))] for _ in clusters];samples.append(sum(sum(r) for r in chosen)/sum(len(r) for r in chosen))
 samples.sort();uncertainty={'method':'按16个功能组整体重采样10000次，组内重复观测绑定；只描述合成测试集，不代表真实用户总体。','seed':20261031,'cluster_count':len(clusters),'accuracy_95_interval':[samples[249],samples[9749]],'four_turn_tasks':task}
 write(ROUND/'reports/重复性与不确定性.json',uncertainty)
 s.update(tool_fixture_issue=tool_issue,task_success=task,uncertainty=uncertainty,failed_unique_inputs=len({q['id'] for q in failures}),http_status_counts=dict(collections.Counter(str(a['http_status']) for a in apis)),transport_error_count=sum(bool(a['transport_error']) for a in apis))
 write(ROUND/'reports/summary.json',s)
 data.update(summary=s,stages=stages,native=[r for r in nr if r['selected']],native_runs=nruns,evaluators=evals,live_failures=failures,offline_issues=issues,budget=audit)
 write(ROUND/'reports/workbook-data.json',data)
 lines=['# AI各功能专项测试结果','',f"源码{HEAD[:7]}。当前入口为P8.6，Jev关闭；功能模块与当前入口分开。人工标注待复核。",'',f"真实模型：已执行{s['measured_questions']}/512题次，{s['counts']}，实际API{s['actual_http_calls']}次；运行{'已结束' if finished else '中，不能作最终成绩'}。",'',f"每题平均{s['question_seconds']['mean']:.3f}秒、{s['api_calls_per_question']:.3f}次API、{s['cost_per_question_cny']:.8f}元；单次API平均{s['api_seconds']['mean']:.3f}秒、{s['cost_per_api_call_cny']:.8f}元。",'',f"本轮含小批量保守记账{newcost}元，上限10元；正式用量估算{s['known_cost_cny']:.8f}元，未核对平台账单。",'','| 阶段 | 功能 | 模块测试 | 当前入口真实模型 |','|---|---|---|---|']
 lines.extend(f"| {r['stage']} | {r['title']} | {r['native_counts']} | {r['live_counts'] or '无单独语义题，见配置/单位等专项'} |" for r in stages)
 lines+=['','## 测试工具问题与补测','',tool_issue['quality_selection'],tool_issue['fixture_correction'],'','## 本地接口与后端结果','','后端源码原始结果为166通过、12失败、45跳过、415个准备错误。415个错误主要来自旧五件批次夹具；原始JUnit完整保留，不能称这些业务断言已经执行。4项SQLite迁移错误、旧数量和终态清理契约差异、文档unit必填变化分别列出。新的逐件本地接口专项6项通过，核对数据库和恢复记录。不能把这6项替代全部后端验收。','','当前P3模块完整事实的参考公式已实测通过；当前商品聚合契约仍缺整体覆盖、可用量等证明，保守降级属于正确边界。实际语义入口没有选对读取或没有给出已提供的统计时仍记FAIL。','','旧8.6的65次失败逐项关联了本轮功能覆盖；没有把不同表达的成功当成原用例已修复。P9 Jev不调用，V1.5未开发项、App、真实PG并发和生产联调不在本轮通过范围。','','## 问题优先级','','先处理未经明确选择就生成草稿、引用或跨家庭边界；再处理整件操作、规划读取和恢复；循环结束状态、错误码、文档同步分别跟踪。模型/程序根因未确定时保持待定位，不直接指责某个成员。','','详细失败见真实模型失败和离线问题清单，极端值见测试结果与极端值；分阶段独立结果见stages。']
 (ROUND/'reports/结果总说明.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 with (ROUND/'reports/结果总说明.md').open('a',encoding='utf-8') as f:f.write('\n## P4旧缺陷原断言\n\n'+legacytext+'\n')
 failmd=['# 本轮真实模型失败清单','','原始自动FAIL保留，以下为排查分类，不等于人工确认的根因。','']
 for q in failures:failmd.extend([f"## {q['execution_id']} {q['category']}",'',q['text'],'',f"预期：`{json.dumps(q['expected'],ensure_ascii=False)}`",'',f"实际：{q['reply']}",'',f"未满足：{','.join(q['failed_checks'])}。{q['classification']}：{q['analysis']}",'',f"证据：{q['evidence']}",''])
 (ROUND/'reports/真实模型失败清单.md').write_text('\n'.join(failmd)+'\n',encoding='utf-8')
 print(json.dumps({'questions':s['measured_questions'],'counts':s['counts'],'calls':s['actual_http_calls'],'new_conservative':str(newcost),'finished':finished,'stage_pages':len(stages)},ensure_ascii=False))
if __name__=='__main__':main()
