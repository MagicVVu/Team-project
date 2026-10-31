"""Offline analysis only. Never imports or invokes a model client."""
import collections,hashlib,json,os,pathlib,random,re,sqlite3,subprocess
from decimal import Decimal
ROOT=pathlib.Path(__file__).resolve().parents[1]
REPO=ROOT.parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def triage(q):
    o=q['output'];cat=q['category'];checks=q['failed_checks'];err=o.get('error_code') or q.get('error_code') or ''
    if err.startswith(('DIALOGUE_PLAN_INVALID','AUTONOMOUS_DECISION_INVALID')):return '模型结构输出问题','模型输出不符合计划协议，程序停止。保留原响应与schema错误。'
    if cat=='规划资料缺失':return '未支持功能和状态契约差异','夹具明确没有规划资料；应降级且标识data_unavailable。部分返回completed或改问用户。不能按统计预测已实现处理。'
    if checks==['error_code']:return '错误码契约差异待复核','保护拒绝仍生效，但错误码与冻结预期不同；保留FAIL，团队复核后另作裁定。'
    if cat=='引用过期':return '引用有效性问题待定位','过期指代仍返回库存事实。核对过期引用的过滤及模型是否绕过引用重新选择。'
    if cat=='多件选择':return '对象选择问题待定位','用户明确未选对象却生成草稿。应先澄清，核对模型选择器及程序引用优先级。'
    if cat in ('整件消耗','整件丢弃'):return '模型理解和数量落地问题待定位','已说明整件且引用唯一对象，仍追问数量或拒绝。对照原始amount_mode与逐件规则定位，尚未归责单一组件。'
    if cat=='按件新增':return '数量和多操作判断问题待定位','一次新增多件被判为多项修改。对照write_count及MULTIPLE_WRITES规则。'
    if q['stop_reason'] in ('repeated_plan','no_progress'):return '循环终止和状态问题待定位','部分已返回正确事实，但重复计划或无新增信息导致stopped；严格状态断言失败，不等同事实必错。'
    if cat=='日常交流':return '模型意图或对话状态问题待定位','日常讨论被追问或停止；应复核日常交流契约与模型speech_act。'
    return '程序或模型问题待定位','查该题失败断言、计划与领域处理结果；未人工确认根因。'
def main():
    data=read(ROOT/'reports/workbook-data.json');qs=data['questions'];allq=[json.loads(l) for l in (ROOT/'reports/逐题记录.jsonl').read_text(encoding='utf-8').splitlines()]
    fail=[]
    for q in qs:
        if q['status']=='FAIL':
            typ,why=triage(q);fail.append({k:q[k] for k in ['execution_id','id','repeat','category','text','expected','output','failed_checks','stop_reason','actual_http_calls','seconds','cost_cny','evidence']}|{'triage':typ,'analysis':why,'root_cause_confirmed':False,'human_review_status':'pending'})
    (ROOT/'reports/失败逐条.jsonl').write_text(''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in fail),encoding='utf-8')
    cats=[]
    for cat in dict.fromkeys(q['category'] for q in qs):
        r=[q for q in qs if q['category']==cat];f=[q for q in fail if q['category']==cat]
        cats.append({'category':cat,'executed':len(r),'PASS':sum(q['status']=='PASS' for q in r),'FAIL':len(f),'failure_types':dict(collections.Counter(q['triage'] for q in f)),'examples':[q['execution_id'] for q in f[:3]]})
    write(ROOT/'reports/分功能结果.json',cats)
    groups=collections.defaultdict(list)
    for q in qs:groups[q['group_id']].append(q['status']=='PASS')
    rng=random.Random(20261031);g=list(groups.values());boot=[]
    for _ in range(10000):
        sampled=[g[rng.randrange(len(g))] for _ in g];boot.append(sum(sum(a) for a in sampled)/sum(len(a) for a in sampled))
    boot.sort();ci=[boot[249],boot[9749]]
    scenarios=collections.defaultdict(list)
    for q in allq:
        if q['id'].startswith('p86-m'):scenarios[(q['repeat'],q['scenario_id'])].append(q)
    complete=[r for r in scenarios.values() if len(r)==6 and all(q['status']!='BLOCKED' for q in r)]
    task={'complete_scenario_executions':len(complete),'all_six_pass':sum(all(q['status']=='PASS' for q in r) for r in complete),'blocked_scenario_executions':len(scenarios)-len(complete)}
    uncertainty={'cluster_bootstrap_95_interval':ci,'groups':len(g),'resamples':10000,'seed':20261031,'method':'按34个表达/场景族整体有放回重采样，族内所有重复观测绑定；百分位区间，只描述合成集，不代表真实用户总体。','scenario_task_results':task}
    write(ROOT/'reports/统计不确定性.json',uncertainty)
    supplemental={'by_call_count':[], 'http_status_counts':dict(collections.Counter(str(a.get('http_status')) for a in data['apis'])),'returned_model_names':dict(collections.Counter(a.get('model') for a in data['apis'])),'transport_errors':sum(bool(a.get('transport_error')) for a in data['apis']),'dataset_or_annotation_defect_confirmed':False}
    for n in sorted(set(q['actual_http_calls'] for q in qs)):
        r=[q for q in qs if q['actual_http_calls']==n];supplemental['by_call_count'].append({'calls':n,'questions':len(r),'PASS':sum(q['status']=='PASS' for q in r),'FAIL':sum(q['status']=='FAIL' for q in r),'mean_seconds':sum(q['seconds'] for q in r)/len(r),'mean_cost_cny':sum(q['cost_cny'] for q in r)/len(r)})
    write(ROOT/'reports/补充指标.json',supplemental)
    overview=['# P8.6 测试方法与分功能结果','','固定源码733d339，真实DeepSeek，本地只读合成环境，Jev关闭。120条单轮与20个六轮场景，共240个输入；计划重复3遍。正式执行719题次，保留预算BLOCKED1条，完整六轮场景执行59次，其中47次全部六轮PASS，另1次场景因最后一轮预算拦截而未完成。','','严格自动通过率654/719=90.96%，人工标注仍待复核。按34个表达或场景族整体重采样10000次，描述性95%区间为'+f'{ci[0]:.2%}至{ci[1]:.2%}'+'；不能当作真实用户总体正确率。','','| 功能 | 题次 | PASS | FAIL |','|---|---:|---:|---:|']
    overview.extend(f"| {c['category']} | {c['executed']} | {c['PASS']} | {c['FAIL']} |" for c in cats)
    overview+=['','## 调用路径与计量','','实际HTTP共766次，均保存请求、响应、用量、耗时及题目关联。正式请求HTTP状态及返回模型别名见补充指标。成功HTTP不等于业务断言通过。计量和源码测试最终55项通过；初始工具失败及修复日志保留。','','包含零调用的每题均值适合评估当前整个AI方案。模型API自身性能用单次API均值，不能拿零调用短路径当作模型推理速度。调用两次可能是读取后finish，不一定是判断前一个答案正确性。','','## 成本口径','','正式批次用量估算0.74768412元，按响应Token、缓存、10月31日周末价格计算；单次API均价0.00097609元，每题0.00103989元。正式与小批量合计773次真实HTTP，保守记账4.957662元，在本轮另设5元内。平台实扣账单未核对。','','原账本旧余额4.534698元保持原样，本轮累加后9.492360元，不能把累计数当作本轮花费。预算按峰值未缓存价格预留，最后一个新请求的最坏预留会越过5元，所以在发出前拦截。即使用量估算较低，也未绕过保护继续调用。','','## 复现实验与后续比较','','源码、依赖、提示词及配置见evidence；冻结数据哈希见datasets/manifest.json。当前single-object-1逐件库存，整件消耗/丢弃，规格不是余量。每遍重建相同状态，多轮前序草稿只保存在合成上下文，不执行业务写入。允许网络仅DeepSeek443；未接App、业务服务或真实数据库。','','旧P8.4/P8.5的批次数量语义不同，未强行混跑并比较通过率。本轮不包含完整规划服务、真实数据库计算与App联调验收。后续Jev按相同数据与判分同期对照，记录所有组件成本及超时；用本集调优后应另备未见评估集。','','单独的安全性与可读性人工复核仍待完成。新一轮付费执行应另立批次和额度，不得重跑正式命令覆盖本轮证据。']
    (ROOT/'reports/测试方法与分功能结果.md').write_text('\n'.join(overview)+'\n',encoding='utf-8')
    lines=['# P8.6 失败交接清单','','65次自动FAIL保留原判定，不改冻结预期。以下为证据分流，根因仍需AI负责人复核；同一问题三遍失败不算三个独立缺陷。人工标注未代签。','','| 功能 | 已执行 | PASS | FAIL | 示例执行编号 |','|---|---:|---:|---:|---|']
    for c in cats:
        if c['FAIL']:lines.append(f"| {c['category']} | {c['executed']} | {c['PASS']} | {c['FAIL']} | {', '.join(c['examples'])} |")
    lines+=['','## 优先处理','','多件未选仍生成草稿、过期引用被继续使用应优先复核。整件消耗与丢弃的18次失败影响核心任务。规划缺数据、重复计划停止和错误码差异要分别修复或确认契约，不能混称答案事实错误。','','## 分流统计','']
    for t,n in collections.Counter(q['triage'] for q in fail).items():lines.append(f'- {t}：{n}题次。')
    lines+=['','未发现已确认的样本标注错误；错误码、日常交流和降级状态等契约仍待团队复核，不得据此自动把FAIL改成PASS。规划接口在本轮合成夹具中故意不可用，这是降级测试，不能据此断言正式服务器一定未实现。','','## 逐条问题','']
    for q in fail:
        lines.extend([f"### {q['execution_id']} {q['category']}",'',q['text'],'',f"分流：{q['triage']}。{q['analysis']}",'',f"失败断言：{', '.join(q['failed_checks'])}。停止原因：{q['stop_reason']}。",'',f"实际回复：{q['output'].get('reply','')}。",'',f"预期：`{json.dumps(q['expected'],ensure_ascii=False)}`",'',f"证据：{q['evidence']}。完整输出见同编号失败逐条JSONL。",''])
    (ROOT/'reports/失败交接清单.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    source=read(ROOT/'evidence/source.json');mismatch=[]
    for kind,base in [('protected',REPO),('snapshot',ROOT/'.snapshot')]:
        for e in source[kind]:
            p=base/e['path']
            if not p.exists() or digest(p)!=e['sha256']:mismatch.append({'kind':kind,'path':e['path']})
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    ledger=pathlib.Path(os.environ['LOCALAPPDATA'])/'GarinAIModelTest/baselines/3f007ba/budget.sqlite';pol=read(ledger.parent/'p86-20261031-733d339-five-cny.json')
    with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
        amount,count,pending=db.execute('select sum(coalesce(actual,reserved)),count(*),sum(actual is null) from calls').fetchone()
    live_calls=sum(len((p/'requests.jsonl').read_text(encoding='utf-8').splitlines()) for p in (ROOT/'runs').iterdir() if p.name.startswith(('formal-','smoke-')))
    newcost=Decimal(str(round(amount,6)))-Decimal(pol['initial_cny']);newcalls=count-pol['initial_reservations']
    audit={'head_unchanged':head==source['head'],'protected_files':len(source['protected']),'snapshot_files':len(source['snapshot']),'hash_mismatches':mismatch,'new_conservative_cny':str(newcost),'cap_cny':pol['new_cap_cny'],'within_budget':newcost<=Decimal(pol['new_cap_cny']),'new_ledger_calls':newcalls,'new_wire_calls':live_calls,'ledger_matches_wire':newcalls==live_calls,'unknown_usage':pending,'real_business_database_accessed':False,'live_calls_stopped':True}
    write(ROOT/'evidence/final-integrity-and-budget.json',audit)
    assert audit['head_unchanged'] and not mismatch and audit['within_budget'] and audit['ledger_matches_wire']
    write(ROOT/'evidence/adapter-notes.json',{'raw_records_preserved':True,'decision_step':'原始计数器按问题编号累计跨遍，分析按execution_id内实际请求顺序重新编号；原值保留为recorded_cumulative_step。不影响模型提示、次数、耗时或费用。','initial_fixes':'付费执行前修复离线CURRENT重复参数、模拟Oracle、UTF8读取等测试工具问题，初始日志保留；55项最终计量及源码测试通过。','workbook_export':'导出程序打印成功后进程返回1；以最终XLSX解压、缓存值、公式、图表结构及渲染验证结果作为交付依据。'})
    print(json.dumps({'failure_records':len(fail),'task':task,'cluster_ci':ci,'audit':audit},ensure_ascii=False))
if __name__=='__main__':main()
