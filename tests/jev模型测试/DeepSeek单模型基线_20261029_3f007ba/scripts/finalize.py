"""Finalize evidence integrity and handoff after the paid process has stopped."""
import collections,json,os,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
from prepare import ROUND,REPO,write,sha
from summarize import load

def main():
    evidence=ROUND/'evidence'; frozen=json.loads((evidence/'source-manifest.json').read_text(encoding='utf-8'))
    changed=[]
    for row in frozen['outside_owned_files']:
        path=REPO/row['path']
        if not path.exists() or sha(path)!=row['sha256']: changed.append(row['path'])
    snapshot_changed=[r['path'] for r in frozen['snapshot_files'] if sha(ROUND/'.snapshot'/r['path'])!=r['sha256']]
    after=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    integrity={'outside_owned_checked':len(frozen['outside_owned_files']),'outside_owned_changed':changed,
        'snapshot_checked':len(frozen['snapshot_files']),'snapshot_changed':snapshot_changed,
        'head_before':frozen['head'],'head_after':after,'source_unchanged':not changed and not snapshot_changed and after==frozen['head']}
    write(evidence/'final-integrity.json',integrity)
    planned=[]
    from run import batches
    for batch,kind,data in batches('formal'):
        for row in data:
            if kind in {'p85','multi'}:
                planned.extend({'batch':batch,'id':f"{row['id']}-t{n+1}"} for n in range(len(row['turns'])))
            else: planned.append({'batch':batch,'id':row['id']})
    formal=sorted((ROUND/'runs').glob('formal-*'))
    actual=[]; requests=[]; completions=[]
    for run in formal:
        actual+=load(run/'cases.jsonl'); requests+=load(run/'requests.jsonl')
        if (run/'complete.json').exists(): completions.append(json.loads((run/'complete.json').read_text(encoding='utf-8')))
    executed={(r['batch'],r['id']) for r in actual}
    pending=[{**r,'status':'BLOCKED','reason':'not executed after stop or interrupted run; see completion'} for r in planned if (r['batch'],r['id']) not in executed]
    write(ROUND/'reports/not-executed.json',pending)
    ledger=Path(os.environ['LOCALAPPDATA'])/'GarinAIModelTest/baselines/3f007ba/budget.sqlite'
    budget_audit={'cap_cny':5,'all_live_http':0,'ledger_calls_delta':None,'request_ledger_match':None}
    live=[]
    for directory in (ROUND/'runs').glob('*'):
        if directory.is_dir(): live+= [r for r in load(directory/'requests.jsonl') if r.get('provenance')=='live']
    budget_audit['all_live_http']=len(live)
    if ledger.exists():
        import sqlite3
        db=sqlite3.connect(f'file:{ledger.as_posix()}?mode=ro',uri=True)
        calls,used,pending_usage=db.execute('SELECT COUNT(*),COALESCE(SUM(COALESCE(actual,reserved)),0),COALESCE(SUM(actual IS NULL),0) FROM calls').fetchone(); db.close()
        policy=json.loads((ledger.parent/'garin-20261029-five-cny.json').read_text(encoding='utf-8'))
        spent=used-float(policy['initial_conservative_cost_cny'])
        smoke=sorted((ROUND/'runs').glob('smoke-*/complete.json'))
        start_calls=json.loads(smoke[0].read_text(encoding='utf-8'))['budget_before']['calls'] if smoke else None
        delta=calls-start_calls if start_calls is not None else None
        budget_audit.update(new_conservative_cost_cny=spent,cap_respected=spent<=5,unknown_usage_calls=pending_usage,
            ledger_calls_delta=delta,request_ledger_match=delta==len(live),supplier_invoice_reconciled=False)
    write(evidence/'budget-audit.json',budget_audit)
    tests=[]
    for file in evidence.glob('*tests*.xml'):
        cases=ET.parse(file).findall('.//testcase')
        tests.append({'file':file.name,'n':len(cases),'pass':sum(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in cases)})
    write(evidence/'verification-summary.json',tests)
    handoff=REPO/'tests/交接文件夹/2026-10-29_DeepSeek单模型基线'; handoff.mkdir(parents=True,exist_ok=True)
    text=['# Garin DeepSeek 单模型基线交接','',
        '本轮源码为3f007ba，Jev未启用。主测P8.4，P8.5另表。所有家庭、库存和历史均为测试合成数据，未访问业务服务器和真实用户数据库。','',
        f"正式计划1200轮；已有记录{len(actual)}轮；尚无记录{len(pending)}轮。最终状态和中止原因见模型目录的完整批次记录。",
        f"本轮所有实际HTTP请求{len(live)}次；保守新增费用{budget_audit.get('new_conservative_cost_cny','未知')}元，用户上限5元。供应商账单尚未核对。",'',
        '## 文件位置','',f"详细材料：tests/jev模型测试/{ROUND.name}/。先读 reports/测试记录.md，再查 summary.json、issues.json 和 not-executed.json。",
        '逐条原输入、预期、实际、HTTP响应、用量与耗时保存在 runs 各批次文件夹。Word工作记录在模型目录 reports 下。','',
        '## 请团队继续核对','',
        '1. AI负责人核对批次 b1 到规划商品 milk 的选择映射，以及当前规划契约所需的库存核对资料。旧宽口径把部分内部计算错误也判成通过，需结合新增字段审核查看。',
        '2. Garin与团队确认新风险样本中的绿色预期。源码随附规则未满足当前审核要求，unknown不能直接视为模型错误；原预期保留，人工待复核。',
        '3. 补货用例还需确认当前风险规则和可用库存条件；数学上的待购覆盖量不能覆盖安全前提。',
        '4. 查看真实模型非通过逐条记录。自动归因只是定位线索；先核对输入、原始输出、规则结果，再决定修改程序还是标注。',
        '5. 以后接入Jev，沿用本轮输入、时钟和评分，固定主版本并同期重跑DeepSeek对照；P8.4与P8.5不能合并成绩。','',
        '## 边界','',
        '本轮只测AI阶段。App完整响应耗时、后台保存、数据库事务、实际并发、自然度人工评分和正式用户泛化均需另外验收。未代签任何人工复核，未修改队友源码。',
        f"源码完整性：范围外{integrity['outside_owned_checked']}个文件及副本{integrity['snapshot_checked']}个文件已核对，source_unchanged={integrity['source_unchanged']}。"]
    (handoff/'README.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    index=REPO/'tests/交接文件夹/README.md'; original=index.read_text(encoding='utf-8')
    entry='- [2026年10月29日 DeepSeek单模型基线](2026-10-29_DeepSeek单模型基线/README.md)'
    if entry not in original: index.write_text(original.rstrip()+'\n\n'+entry+'\n',encoding='utf-8')
    write(ROUND/'reports/delivery-status.json',{'formal_completions':completions,'planned_formal_turns':len(planned),'recorded_formal_turns':len(actual),
        'not_executed_formal_turns':len(pending),'counts':dict(collections.Counter(x['status'] for x in actual)),
        'integrity':integrity,'budget':budget_audit,'handoff':str(handoff)})
    print(json.dumps({'source_unchanged':integrity['source_unchanged'],'formal_recorded':len(actual),'not_executed':len(pending),'budget':budget_audit},ensure_ascii=True))
if __name__=='__main__': main()
