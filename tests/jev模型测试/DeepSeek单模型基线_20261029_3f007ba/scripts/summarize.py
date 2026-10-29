"""No calls. Summaries retain errors, group dependence and incomplete-run status."""
import collections, hashlib, json, math, random, statistics
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from prepare import ROUND,write
from audit_existing import audit

CATEGORY_LABELS=dict(zip(
    'greeting family_advice complaint hypothesis negation half_consume all_consume literal_consume vague_amount whole_move opening discard_partial discard_all add manual_plan quantity_location dates_query risk consumption_stats forecast purchase_advice multiple_writes correction_quantity correction_location pending_status committed_status cancelled_status unknown_status expired_reference ordinal_query pronoun_query reported_speech new_task injection missing_unit excess incompatible_unit stale_draft recall basis'.split(),
    '问候 家务建议 用户反馈 假设讨论 否定表达 半数消耗 全部消耗 定量消耗 模糊数量 整批移动 开封 部分丢弃 全部丢弃 新增 采购草稿 数量位置 日期查询 风险 消费统计 耗尽预测 补货建议 多操作 数量改口 位置改口 待确认状态 已执行状态 已取消状态 结果未知 过期引用 候选选择 指代查询 转述 新任务 提示注入 缺少单位 超出库存 单位冲突 陈旧草稿 历史回顾 建议依据'.split()))

def load(path): return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
def percentile(values,p): return sorted(values)[max(0,math.ceil(len(values)*p)-1)] if values else None
def distribution(values):
    return {'n':len(values),'mean':statistics.mean(values) if values else None,'p50':percentile(values,.5),'p90':percentile(values,.9),
        'p95':percentile(values,.95),'max':max(values) if values else None,'min':min(values) if values else None,
        'stddev':statistics.pstdev(values) if values else None}
def ci(rows):
    groups=collections.defaultdict(list)
    for r in rows:
        if r['status'] in {'PASS','FAIL'}: groups[r['group_id']].append(int(r['status']=='PASS'))
    if len(groups)<2: return None
    rng=random.Random(20261029); values=list(groups.values()); simulations=[]
    for _ in range(10000):
        selected=[values[rng.randrange(len(values))] for _ in values]
        simulations.append(sum(sum(x) for x in selected)/sum(len(x) for x in selected))
    return {'method':'group bootstrap, seed 20261029, 10000 resamples','groups':len(groups),'low':percentile(simulations,.025),'high':percentile(simulations,.975)}
def cost(event):
    usage=event.get('usage') or {}; prompt=usage.get('prompt_tokens'); output=usage.get('completion_tokens')
    if not all(isinstance(x,int) and not isinstance(x,bool) and x>=0 for x in [prompt,output]): return {'known':False,'cny':None}
    hit=usage.get('prompt_cache_hit_tokens'); miss=usage.get('prompt_cache_miss_tokens')
    if not all(isinstance(x,int) and not isinstance(x,bool) and x>=0 for x in [hit,miss]) or hit+miss!=prompt:
        return {'known':True,'cny':None,'upper_peak_cny':float((Decimal(prompt)*2+Decimal(output)*8)/1000000),
                'reason':'cache split not returned; exact cache-adjusted price unavailable','prompt_tokens':prompt,'completion_tokens':output}
    # Public official weekday windows; local public holiday overrides require invoice reconciliation.
    started=datetime.fromisoformat(event['started_at']).astimezone(ZoneInfo('Asia/Shanghai'))
    finished=datetime.fromisoformat(event['finished_at']).astimezone(ZoneInfo('Asia/Shanghai'))
    def peak(t): return t.weekday()<5 and (9<=t.hour<12 or 14<=t.hour<18)
    if peak(started)!=peak(finished): return {'known':True,'cny':None,'reason':'request spans rate band boundary','upper_peak_cny':float((Decimal(prompt)*2+Decimal(output)*8)/1000000)}
    factor=Decimal('1') if peak(started) else Decimal('.5')
    amount=(Decimal(hit)*Decimal('.04')+Decimal(miss)*2+Decimal(output)*8)*factor/1000000
    return {'known':True,'cny':str(amount),'prompt_tokens':prompt,'completion_tokens':output,'cache_hit_tokens':hit,'cache_miss_tokens':miss,
        'tariff':'weekday_peak' if peak(started) else 'offpeak','holiday_calendar_checked':False,'invoice_reconciled':False,
        'upper_peak_cny':str((Decimal(prompt)*2+Decimal(output)*8)/1000000)}
def summarize(cases,requests,stages,extractions=None):
    extractions=extractions or []
    scored=[r for r in cases if r['status'] in {'PASS','FAIL'}]; passes=sum(r['status']=='PASS' for r in scored)
    counts=collections.Counter(r['status'] for r in cases)
    scenarios=collections.defaultdict(list)
    for r in cases: scenarios[r.get('scenario_id',r['id'])].append(r)
    expected=sum(r.get('clarification_expected',False) for r in cases)
    observed=sum(r.get('clarification_actual',False) for r in cases if r.get('clarification_expected'))
    clear=[r for r in cases if 'clarification_expected' in r and not r['clarification_expected']]
    redundant=sum(r.get('clarification_actual',False) for r in clear)
    fieldchecks=collections.defaultdict(list)
    for r in cases:
        for k,v in r['checks'].items(): fieldchecks[k].append(v)
    categories=collections.defaultdict(list)
    for r in cases:categories[CATEGORY_LABELS.get(r.get('category'),r.get('category','未分类'))].append(r)
    by_category={}
    for name,group in categories.items():
        c=collections.Counter(r['status'] for r in group); denominator=c['PASS']+c['FAIL']
        by_category[name]={'counts':dict(c),'n':len(group),'accuracy':c['PASS']/denominator if denominator else None,
            'ai_latency_ms':distribution([r['latency_ms'] for r in group]),'actual_http_attempts':sum(r['actual_http_attempts'] for r in group)}
    prices=[cost(r) for r in requests]
    exact=[Decimal(r['cny']) for r in prices if r.get('cny') is not None]
    completed=sum(all(r['status']=='PASS' for r in rs) for rs in scenarios.values())
    hit_tokens=sum(r.get('cache_hit_tokens',0) for r in prices); miss_tokens=sum(r.get('cache_miss_tokens',0) for r in prices)
    finish_reasons=collections.Counter()
    for req in requests:
        for choice in (req.get('response') or {}).get('choices',[]): finish_reasons[choice.get('finish_reason','unknown')]+=1
    bysize={}
    for label,low,high in [('under_2k',0,2000),('2k_to_8k',2000,8000),('8k_and_more',8000,float('inf'))]:
        selected=[r for r in requests if isinstance((r.get('usage') or {}).get('prompt_tokens'),int) and low<=r['usage']['prompt_tokens']<high]
        bysize[label]={'requests':len(selected),'wire_latency_ms':distribution([r['latency_ms'] for r in selected])}
    raw=[]; prohibited=0; blocked=0
    audited=[(r,audit(r)) for r in cases if r['id'].startswith('p84-')]
    covered=[(r,a) for r,a in audited if a['covered']]
    bycase={r.get('turn_id',r['id']):r for r in cases}
    for event in requests:
        if event.get('stage')!='understanding': continue
        target=bycase.get(event.get('turn_id') or event.get('scenario_id'))
        try:
            value=json.loads(event['response']['choices'][0]['message']['content'])
        except (ValueError,TypeError,KeyError,IndexError): continue
        if target and isinstance(target.get('expected'),dict) and target['expected'].get('draft'):
            raw.append(value.get('action')==target['expected']['draft']['action'])
        if target and target.get('category') in {'否定假设','提示注入'} and value.get('action'):
            prohibited+=1; blocked+=int(not (target.get('frame',{}).get('result') or {}).get('draft'))
    return {'counts':dict(counts),'evaluated_denominator':len(scored),'turn_accuracy':passes/len(scored) if scored else None,
        'conservative_all_executed_pass_fraction':passes/len(cases) if cases else None,
        'human_review_status':'pending; automated score is provisional','accuracy_95ci':ci(cases),
        'legacy_additional_audit':{'covered':len(covered),'pass':sum(a['passed'] for r,a in covered),
            'original_pass_but_extra_failed':sum(r['status']=='PASS' and not a['passed'] for r,a in covered),
            'coverage_note':'field audit subset; cannot call original legacy success rate full correctness'},
        'scenario_count':len(scenarios),'complete_scenario_pass':completed,
        'ai_turn_latency_ms':distribution([r['latency_ms'] for r in cases]),'wire_latency_ms':distribution([r['latency_ms'] for r in requests]),
        'stage_latency_ms':{name:distribution([s['latency_ms'] for s in stages if s['stage']==name]) for name in ['understanding','resolve','response']},
        'actual_http_attempts':len(requests),'non_200_http':sum(r['http_status']!=200 for r in requests),
        'transport_errors':dict(collections.Counter(r['transport_error'] for r in requests if r['transport_error'])),
        'engine_errors':dict(collections.Counter(r['error_code'] for r in extractions if r.get('error_code'))),
        'http_statuses':dict(collections.Counter(str(r.get('http_status')) for r in requests)),
        'raw_action_only_accuracy':{'pass':sum(raw),'n':len(raw),'rate':sum(raw)/len(raw) if raw else None,'note':'new write samples with an actual understanding response only; not whole-task accuracy'},
        'prohibited_raw_actions':prohibited,'prohibited_raw_actions_blocked':blocked,
        'requests_per_turn':len(requests)/len(cases) if cases else None,'zero_wire_turns':sum(r['actual_http_attempts']==0 for r in cases),
        'fallback_turns':sum(r.get('frame',{}).get('fallback_used',False) for r in cases),
        'truncated_turns':sum(r.get('frame',{}).get('truncated',False) for r in cases),
        'clarification_recall':{'numerator':observed,'denominator':expected,'rate':observed/expected if expected else None},
        'unnecessary_clarification_proxy':{'numerator':redundant,'denominator':len(clear),'rate':redundant/len(clear) if clear else None,'note':'automatic proxy, requires human review'},
        'field_checks':{k:{'pass':sum(v),'n':len(v),'rate':sum(v)/len(v)} for k,v in fieldchecks.items()},
        'by_function':by_category,
        'returned_models':dict(collections.Counter(r.get('returned_model') or 'unknown' for r in requests)),
        'finish_reasons':dict(finish_reasons),'latency_by_input_tokens':bysize,
        'measured_cache_hit_tokens':hit_tokens,'measured_cache_miss_tokens':miss_tokens,
        'cache_hit_fraction':hit_tokens/(hit_tokens+miss_tokens) if hit_tokens+miss_tokens else None,
        'measured_prompt_tokens':sum(r.get('prompt_tokens',0) for r in prices),'measured_completion_tokens':sum(r.get('completion_tokens',0) for r in prices),
        'known_calculated_cost_cny':str(sum(exact)) if exact else None,'cost_unknown_or_inexact_requests':len(prices)-len(exact),
        'cost_per_correct_turn_cny':str(sum(exact)/passes) if passes and len(exact)==len(prices) and prices else None,
        'cost_per_correct_complete_scenario_cny':str(sum(exact)/completed) if completed and len(exact)==len(prices) and prices else None,
        'http_per_correct_complete_scenario':len(requests)/completed if completed else None,
        'invoice_cost_cny':None,'invoice_status':'NOT_RECONCILED','no_business_writes':all(r.get('inventory_unchanged_by_ai',False) for r in cases)}
def main():
    summaries=[]; failures=[]; repeat=collections.defaultdict(list)
    for directory in sorted((ROUND/'runs').glob('*')):
        if not directory.is_dir(): continue
        cases=load(directory/'cases.jsonl'); requests=load(directory/'requests.jsonl'); stages=load(directory/'stages.jsonl'); extractions=load(directory/'extractions.jsonl')
        request_costs=[]
        for req in requests:
            request_costs.append({k:req.get(k) for k in ['wire_id','batch','scenario_id','turn_id','stage','http_status','started_at','finished_at']})
            request_costs[-1].update(cost(req))
        if request_costs:
            (directory/'request-costs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in request_costs),encoding='utf-8')
        per_case=[]
        for case in cases:
            matched=[(req,c) for req,c in zip(requests,request_costs) if req.get('batch')==case['batch'] and (req.get('turn_id') or req.get('scenario_id'))==case['id']]
            precise=[Decimal(c['cny']) for _,c in matched if c.get('cny') is not None]
            per_case.append({'id':case['id'],'batch':case['batch'],'status':case['status'],'actual_http_attempts':len(matched),
                'wire_ids':[req['wire_id'] for req,_ in matched], 'ai_latency_ms':case['latency_ms'],
                'calculated_cny':str(sum(precise)) if len(precise)==len(matched) else None,
                'cost_unknown_requests':len(matched)-len(precise),'supplier_invoice_cny':None,
                'prompt_tokens_measured':sum(c.get('prompt_tokens',0) for _,c in matched),
                'completion_tokens_measured':sum(c.get('completion_tokens',0) for _,c in matched),
                'provenance':case.get('provenance'),'human_review_status':'pending'})
        (directory/'case-metrics.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in per_case),encoding='utf-8')
        complete=json.loads((directory/'complete.json').read_text(encoding='utf-8')) if (directory/'complete.json').exists() else {'complete':False}
        def batch_order(name):
            if name=='p84-regression':return (0,0)
            if name=='p85-regression':return (1,0)
            if name.startswith('new-'):return (2+int(name[-1]),0 if name.startswith('new-single') else 1)
            return (9,name)
        batches=sorted({r['batch'] for r in cases},key=batch_order)
        result={'run':directory.name,'completion':complete,'batches':{}}
        for batch in batches:
            cs=[r for r in cases if r['batch']==batch]; req=[r for r in requests if r.get('batch')==batch]; ss=[s for s in stages if s.get('batch')==batch]
            ee=[e for e in extractions if e.get('batch')==batch]
            result['batches'][batch]=summarize(cs,req,ss,ee)
            for r in cs:
                if r['status']!='PASS': failures.append({'run':directory.name,'batch':batch,'id':r['id'],'status':r['status'],'category':r.get('issue_category'),'failed_checks':[k for k,v in r['checks'].items() if not v],'evidence':str((directory/'cases.jsonl').relative_to(ROUND))})
                if r['id'].startswith('p84-'):
                    extra=audit(r)
                    if extra.get('covered') and not extra['passed']:
                        failures.append({'run':directory.name,'batch':batch,'id':r['id'],'status':'FAIL_SUPPLEMENTAL_AUDIT','category':'additional field or calculation check; needs root-cause review','legacy_status':r['status'],'failed_checks':extra['failed_checks'],'expected':extra['expected'],'evidence':str((directory/'cases.jsonl').relative_to(ROUND))})
                if batch.startswith('new-'): repeat[r['id']].append({'batch':batch,'status':r['status'],'frame':r.get('frame'), 'latency_ms':r['latency_ms']})
        write(directory/'metrics.json',result); summaries.append(result)
    stability={}
    def signature(frame):
        # Compare business meaning; generated IDs and natural connective prose are excluded.
        draft=(frame.get('result') or {}).get('draft') or {}
        draft={k:v for k,v in draft.items() if k not in {'id','draft_id'}}
        return json.dumps({'kind':frame.get('kind'),'draft':draft,'facts':sorted((frame.get('facts') or {}).values()),'error':frame.get('error_code')},sort_keys=True,ensure_ascii=False)
    eligible={k:v for k,v in repeat.items() if len(v)==3}
    stability={'cases_with_three_repeats':len(eligible),'all_three_pass':sum(all(x['status']=='PASS' for x in v) for v in eligible.values()),
        'same_semantic_output':sum(len({signature(x['frame']) for x in v})==1 for v in eligible.values()),
        'per_case':{k:{'statuses':[x['status'] for x in v],'latency_ms':distribution([x['latency_ms'] for x in v])} for k,v in eligible.items()}}
    write(ROUND/'reports/summary.json',{'runs':summaries,'stability':stability,'interpretation':'Do not combine offline, smoke, regression, and repeated evaluation into one accuracy.'})
    write(ROUND/'reports/issues.json',failures)
    lines=['# DeepSeek 当前方案测试记录','', '源码：3f007ba。Jev 未启用；未访问业务服务器或真实用户数据库。',
        '','所有模型成绩均以实际 live 批次为准。离线夹具成绩不代表 DeepSeek 正确率。人工复核仍为 pending。','',
        '| 批次 | 类型 | PASS | FAIL | REVIEW | 实际 HTTP |','|---|---|---:|---:|---:|---:|']
    for run in summaries:
        for name,b in run['batches'].items():
            c=b['counts']; lines.append(f"| {name} | {run['completion'].get('provenance','incomplete')} | {c.get('PASS',0)} | {c.get('FAIL',0)} | {c.get('REVIEW',0)} | {b['actual_http_attempts']} |")
    live_runs=[r for r in summaries if r['run'].startswith('formal-')]
    def n(value,d=3):return '未测' if value is None else f'{value:.{d}f}'
    lines+=['','## 正式批次正确性','',
        '| 批次 | 已评分分母 | 自动通过率 | 完整场景通过 | 场景总数 |','|---|---:|---:|---:|---:|']
    for run in live_runs:
        for name,b in run['batches'].items():
            lines.append(f"| {name} | {b['evaluated_denominator']} | {n(b['turn_accuracy']*100 if b['turn_accuracy'] is not None else None,2)}% | {b['complete_scenario_pass']} | {b['scenario_count']} |")
    lines+=['','通过率分母只含PASS和FAIL；REVIEW及未执行项单列。全部标签仍未人工确认。旧评分宽于新增字段断言，各表不能合并成一个准确率。',
        '', '## 旧评分的补充检查','', '| 批次 | 补充覆盖 | 补充通过 | 原PASS但补充失败 |','|---|---:|---:|---:|']
    for run in live_runs:
        for name,b in run['batches'].items():
            a=b['legacy_additional_audit']
            if a['covered']:lines.append(f"| {name} | {a['covered']} | {a['pass']} | {a['original_pass_but_extra_failed']} |")
    lines+=['','## 正式批次耗时','', '| 批次 | 平均秒 | 中位秒 | P95秒 | 最大秒 | 实际HTTP |','|---|---:|---:|---:|---:|---:|']
    for run in live_runs:
        for name,b in run['batches'].items():
            t=b['ai_turn_latency_ms']
            lines.append('| '+name+' | '+' | '.join(n(t[k]/1000 if t[k] is not None else None) for k in ['mean','p50','p95','max'])+f" | {b['actual_http_attempts']} |")
    lines+=['','耗时仅含本机AI阶段。不是App全链路P95，也不是并发压测容量。',
        '', '## 正式批次Token与费用','', '| 批次 | 已知输入Token | 已知输出Token | 缓存命中比例 | 可计算费用小计 元 | 费用未精确请求数 |','|---|---:|---:|---:|---:|---:|']
    for run in live_runs:
        for name,b in run['batches'].items():
            lines.append(f"| {name} | {b['measured_prompt_tokens']} | {b['measured_completion_tokens']} | {n(b['cache_hit_fraction']*100 if b['cache_hit_fraction'] is not None else None,2)}% | {b['known_calculated_cost_cny'] or '未知'} | {b['cost_unknown_or_inexact_requests']} |")
    lines+=['','用量费用小计不包含未知或时段不确定部分，不能直接当作实扣总额。逐请求和逐条费用在各批次request-costs.jsonl、case-metrics.jsonl。',
        '', '## 三次重复测试','',f"有完整三次记录的输入{stability['cases_with_three_repeats']}条；三次均PASS的{stability['all_three_pass']}条；业务结果和事实内容一致的{stability['same_semantic_output']}条。结果一致时忽略随机ID、自然连接语和事实展示顺序。"]
    auditpath=ROUND/'evidence/budget-audit.json'
    if auditpath.exists():
        money=json.loads(auditpath.read_text(encoding='utf-8'))
        lines+=['','## 5元上限核对','',f"含小批量在内，实际HTTP共{money['all_live_http']}次；新增保守费用{money.get('new_conservative_cost_cny')}元；cap_respected={money.get('cap_respected')}。账本与请求数一致={money.get('request_ledger_match')}。平台账单未核对。"]
    if not any(r['completion'].get('provenance')=='live_deepseek' for r in summaries):
        lines+=['','**真实模型测试 BLOCKED：本机尚未提供脚本可读取的 API Key。正确率、真实网络耗时和实际模型费用尚无成绩。**']
    lines+=['','## 已发现的测试条件问题','',
        '- 风险用例初始标注绿色，但随源码提供的适用规则未满足当前审核条件；当前返回 unknown 有依据。原预期和首次失败均保留，列为样本标注 REVIEW。',
        '- 统计、预测和补货通过当前对话入口传递批次 b1，而旧规划夹具商品键为 milk，返回 ITEM_NOT_FOUND。列为版本契约或适配问题，尚不能认定为线上程序缺陷或模型错误。',
        '- 旧评分有些只判断存在草稿；旧回归保留原评分，新用例增加字段与计算检查，两者不合并成统一严格正确率。',
        '', '初次离线检查和后续分类修订是同一套数据，原预期未改变，不能算成两套独立样本。',
        '', '## 验收边界','', '真实模型执行范围以正式批次记录为准；未执行清单见not-executed.json。供应商账单、自然度人工评分、App全链路、后端数据库和真实并发仍待各自验收。',
        '', '价格来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ 。按执行日价格、缓存和时段计算，预算账本是保守上界。']
    (ROUND/'reports/测试记录.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    detailed=['# 分功能自动评分','', '这是待人工复核的合成样本成绩。旧评分与新增字段评分不同；各批次不合并。REVIEW不计入正确率分母，但完整列出。','']
    for run in live_runs:
        for name,b in run['batches'].items():
            detailed += ['## '+name,'','| 功能 | PASS | FAIL | REVIEW | 自动正确率 | 实际HTTP |','|---|---:|---:|---:|---:|---:|']
            for function,data in b['by_function'].items():
                c=data['counts'];detailed.append(f"| {function} | {c.get('PASS',0)} | {c.get('FAIL',0)} | {c.get('REVIEW',0)} | {n(data['accuracy']*100 if data['accuracy'] is not None else None,2)}% | {data['actual_http_attempts']} |")
            detailed += ['']
    (ROUND/'reports/功能分项.md').write_text('\n'.join(detailed)+'\n',encoding='utf-8')
    print(json.dumps({'runs':len(summaries),'nonpass_records':len(failures),'report':'reports/测试记录.md'},ensure_ascii=False))
if __name__=='__main__': main()
