"""Per-question, per-request and extremum analysis without any model calls."""
import collections,hashlib,json,math,statistics
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from prepare import ROUND,write

def load(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
def percentile(a,p):
    if not a:return None
    a=sorted(a);x=(len(a)-1)*p;lo=int(x);hi=min(lo+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(x-lo)
def stats(a):return {'n':len(a),'mean':statistics.mean(a) if a else None,'min':min(a) if a else None,'p50':percentile(a,.5),'p90':percentile(a,.9),'p95':percentile(a,.95),'p99':percentile(a,.99),'max':max(a) if a else None,'stddev':statistics.pstdev(a) if a else None}
def prices(req):
    u=req.get('usage') or {};hit=u.get('prompt_cache_hit_tokens');miss=u.get('prompt_cache_miss_tokens');out=u.get('completion_tokens');prompt=u.get('prompt_tokens')
    result={'input_tokens':prompt,'output_tokens':out,'cache_hit_tokens':hit,'cache_miss_tokens':miss,'cost_cny':None,'cost_known':False,
        'hit_rate':None,'miss_rate':None,'output_rate':None,'pricing_note':None}
    if not all(isinstance(v,int) and not isinstance(v,bool) and v>=0 for v in [hit,miss,out,prompt]) or hit+miss!=prompt:
        result['pricing_note']='usage或缓存分项缺失，不能记为零费用';return result
    begin=datetime.fromisoformat(req['started_at']).astimezone(ZoneInfo('Asia/Shanghai'));end=datetime.fromisoformat(req['finished_at']).astimezone(ZoneInfo('Asia/Shanghai'))
    def band(t):return t.weekday()<5 and (9<=t.hour<12 or 14<=t.hour<18)
    if band(begin)!=band(end):result['pricing_note']='跨价格时段，实际计费时点未确认';return result
    factor=Decimal(1) if band(begin) else Decimal('.5');a,b,c=Decimal('.04')*factor,2*factor,8*factor
    value=(hit*a+miss*b+out*c)/1000000
    result.update(cost_cny=float(value),cost_exact_decimal=str(value),cost_known=True,hit_rate=float(a),miss_rate=float(b),output_rate=float(c),
        pricing_note='按官方周末空闲费率及返回usage估算，未核对供应商账单' if begin.weekday()>=5 else '按工作日时段估算，法定节假日及账单待核对')
    return result
def jsonlines(path,rows):path.write_text(''.join(json.dumps(r,ensure_ascii=False,default=str)+'\n' for r in rows),encoding='utf-8')
def semantic(out):
    frame=out.get('resolved') or {};d=(frame.get('result') or {}).get('draft') or {}
    chat=(out.get('plan') or {}).get('speech_act') in {'social','discuss','negation','hypothesis'}
    return json.dumps({'status':out.get('status'),'reason':out.get('stop_reason'),'draft':d,'facts':[] if chat else sorted((frame.get('facts') or {}).values()),'error':out.get('error_code')},sort_keys=True,ensure_ascii=False)

def explain(q,apis):
    out=q['output'];trace=out.get('trace',[]);codes=[s.get('error_code') for s in trace if s.get('error_code')]
    matched=[a for a in apis if a['execution_id']==q['execution_id']]
    network=sum(a['seconds'] for a in matched);slow=max(matched,key=lambda a:a['seconds']) if matched else None
    reasons=[]
    if not matched:reasons.append('规则或结构化续接直接处理，实际API为0；不能解释为模型推理特别快')
    else:
        reasons.append(f"实际{len(matched)}次API，网络请求累计{network:.3f}秒，占整题{network/q['seconds']*100:.1f}%")
        if slow:reasons.append(f"最慢第{slow['step']}次请求{slow['seconds']:.3f}秒，输入{slow['input_tokens']} Token")
        if len(matched)>2:reasons.append('自主循环实际超过两次；逐次决策与观察见原始trace')
        if codes:reasons.append('循环中记录校验错误：'+','.join(dict.fromkeys(codes)))
        decisions=[str(a['step'])+':'+str(a.get('decision_action'))+(('/'+a['plan_action']) if a.get('plan_action') else '') for a in matched]
        reasons.append('决策顺序 '+', '.join(decisions))
        if any(a.get('decision_action')=='finish' for a in matched):reasons.append('包含单独的结束决策请求，结束本身也占一次API')
        if any(a.get('observation_error') for a in matched):reasons.append('后续请求携带了前轮校验错误反馈，允许模型修正计划')
        if all(a['cost_known'] for a in matched):
            h=sum(a['cache_hit_tokens'] for a in matched);p=sum(a['input_tokens'] for a in matched)
            reasons.append(f"输入总量{p} Token，缓存命中{h/p*100:.1f}%" if p else '输入Token为0')
    reasons.append('停止原因：'+str(q['stop_reason']))
    return '；'.join(reasons),('费用可由调用次数、Token及缓存分项解释；请求慢的更深原因无法仅凭客户端日志区分供应商排队、推理或公网延迟' if matched else '零调用属于程序路径，不参与单次API耗时平均值')

def main():
    formal=sorted((ROUND/'runs').glob('formal-*'))
    questions=[];apis=[];runs=[];run_counts=[]
    for directory in formal:
        raw=load(directory/'questions.jsonl');reqs=load(directory/'requests.jsonl')
        local_steps=collections.Counter()
        completion=json.loads((directory/'complete.json').read_text(encoding='utf-8')) if (directory/'complete.json').exists() else {'complete':False,'stop_reason':'RUNNING'}
        runs.append({'run':directory.name,'completion':completion})
        for number,a in enumerate(reqs,1):
            execution_id=f"r{a['repeat']}-{a['question_id']}";local_steps[execution_id]+=1
            pr=prices(a)
            try:payload=json.loads(a['request']['messages'][-1]['content'])
            except (ValueError,KeyError,TypeError):payload={}
            try:decision=json.loads(a['response']['choices'][0]['message']['content'])
            except (ValueError,KeyError,TypeError,IndexError):decision={}
            if not isinstance(decision,dict):decision={}
            r={'execution_id':execution_id,'question_id':a['question_id'],'repeat':a['repeat'],'batch':a['batch'],
                'wire_id':a['wire_id'],'step':local_steps[execution_id],'recorded_cumulative_step':a.get('decision_step'),'http_status':a['http_status'],'seconds':a['latency_ms']/1000,
                'started_at':a['started_at'],'finished_at':a['finished_at'],'model':a.get('returned_model'),'transport_error':a.get('transport_error'),
                'evidence':f'runs/{directory.name}/requests.jsonl:{number}',
                'decision_action':decision.get('action'),'plan_action':(decision.get('plan') or {}).get('action'),
                'finish_after_resolve':decision.get('finish_after_resolve',False),
                'read_kinds':','.join(r.get('kind','') for r in (decision.get('plan') or {}).get('reads',[]) if isinstance(r,dict)),
                'observation_error':(payload.get('observations') or {}).get('error_code'),
                'history_turns':len((payload.get('context') or {}).get('history',[])),
                'retrieved_episodes':len(payload.get('retrieved_episodes',[])),**pr};apis.append(r)
        for number,q in enumerate(raw,1):
            key=f"r{q['repeat']}-{q['id']}";attached=[a for a in apis if a['execution_id']==key]
            known=all(a['cost_known'] for a in attached);network=sum(a['seconds'] for a in attached)
            value={**q,'execution_id':key,'seconds':q['question_ms']/1000,'api_seconds':network,'non_api_seconds':q['question_ms']/1000-network,
                'cost_known':known,'cost_cny':float(sum(Decimal(str(a['cost_cny'])) for a in attached)) if known else None,
                'input_tokens':sum(a['input_tokens'] or 0 for a in attached),'output_tokens':sum(a['output_tokens'] or 0 for a in attached),
                'cache_hit_tokens':sum(a['cache_hit_tokens'] or 0 for a in attached),'cache_miss_tokens':sum(a['cache_miss_tokens'] or 0 for a in attached),
                'stop_reason':q['output'].get('stop_reason'),'tool_reads':q['output'].get('tool_reads'),'failed_checks':[k for k,v in q['checks'].items() if not v],
                'reply':q['output'].get('reply',''),'evidence':f'runs/{directory.name}/questions.jsonl:{number}'}
            if not attached:behavior='规则零调用'
            elif any(a.get('observation_error') for a in attached):behavior='校验反馈后再决策'
            elif sum(a.get('decision_action')=='resolve' for a in attached)>1:behavior='追加读取后再决策'
            elif len(attached)>1 and any(a.get('decision_action')=='finish' for a in attached):behavior='核对后单独结束'
            elif len(attached)==1:behavior='一次模型决策'
            else:behavior='其他多次决策'
            value['call_behavior']=behavior
            questions.append(value)
    measured=[q for q in questions if q['status']!='BLOCKED' or q['actual_http_calls']>0]
    grouped=collections.defaultdict(list)
    for q in measured:grouped[q['id']].append(q)
    averages=[]
    for ident,rs in grouped.items():
        costs=[q['cost_cny'] for q in rs if q['cost_known']];out={'id':ident,'category':rs[0]['category'],'text':rs[0]['text'],'runs':len(rs),
            'counts':dict(collections.Counter(q['status'] for q in rs)),'time':stats([q['seconds'] for q in rs]),'calls':stats([q['actual_http_calls'] for q in rs]),
            'total_calls':sum(q['actual_http_calls'] for q in rs),'cost':stats(costs),'all_cost_known':len(costs)==len(rs),
            'total_cost_cny':sum(costs) if len(costs)==len(rs) else None,'all_runs_pass':len(rs)==3 and all(q['status']=='PASS' for q in rs),
            'same_result':len({semantic(q['output']) for q in rs})==1,'evidence_ids':[q['execution_id'] for q in rs]};averages.append(out)
    scored=[q for q in questions if q['status'] in {'PASS','FAIL'}]
    knowncosts=[q['cost_cny'] for q in measured if q['cost_known']]
    totalcost=sum(a['cost_cny'] for a in apis if a['cost_known']);knownapis=[a for a in apis if a['cost_known']]
    by_repeat=[]
    for repeat in sorted({q['repeat'] for q in questions}):
        all_rs=[q for q in questions if q['repeat']==repeat];rs=[q for q in measured if q['repeat']==repeat];calls=sum(q['actual_http_calls'] for q in rs);counts=collections.Counter(q['status'] for q in all_rs)
        by_repeat.append({'repeat':repeat,'questions':len(rs),'recorded_questions':len(all_rs),'counts':dict(counts),'calls':calls,'mean_calls':calls/len(rs),
            'accuracy':counts['PASS']/(counts['PASS']+counts['FAIL']) if counts['PASS']+counts['FAIL'] else None,
            'time':stats([q['seconds'] for q in rs]),'known_cost_cny':sum(q['cost_cny'] for q in rs if q['cost_known'])})
    distribution=dict(sorted(collections.Counter(q['actual_http_calls'] for q in measured).items()))
    summary={'version':'V1-P8.6','source':'733d339','inventory_model':'single-object-1','protocol':'inventory-autonomous-1',
        'runs':runs,'planned_formal_questions':720,'recorded_formal_questions':len(questions),'not_run_questions':720-len(measured),
        'blocked_records':[{'execution_id':q['execution_id'],'id':q['id'],'repeat':q['repeat'],'reason':q['issue_category'],'actual_http_calls':q['actual_http_calls']} for q in questions if q['status']=='BLOCKED'],
        'unique_questions':len(grouped),'measured_questions':len(measured),'counts':dict(collections.Counter(q['status'] for q in questions)),
        'scored_denominator':len(scored),'automatic_accuracy':sum(q['status']=='PASS' for q in scored)/len(scored) if scored else None,
        'question_seconds':stats([q['seconds'] for q in measured]),'api_seconds':stats([a['seconds'] for a in apis]),
        'actual_http_calls':len(apis),'api_calls_per_question':len(apis)/len(measured) if measured else None,'call_distribution':distribution,
        'known_cost_cny':totalcost,'unknown_cost_requests':len(apis)-len(knownapis),'cost_per_question_cny':totalcost/len(measured) if measured and len(knownapis)==len(apis) else None,
        'cost_per_api_call_cny':totalcost/len(apis) if apis and len(knownapis)==len(apis) else None,
        'input_tokens':sum(a['input_tokens'] or 0 for a in apis),'output_tokens':sum(a['output_tokens'] or 0 for a in apis),
        'zero_call_questions':sum(q['actual_http_calls']==0 for q in measured),'over_two_call_questions':sum(q['actual_http_calls']>2 for q in measured),
        'three_repeat_questions':sum(len(r)==3 for r in grouped.values()),'all_three_pass':sum(q['all_runs_pass'] for q in averages),'same_semantic_result':sum(q['same_result'] and q['runs']==3 for q in averages),
        'by_repeat':by_repeat,'stop_reasons':dict(collections.Counter(q['stop_reason'] for q in questions)),'human_review_status':'pending',
        'call_behaviors':dict(collections.Counter(q['call_behavior'] for q in measured)),
        'error_feedback_then_pass':sum(q['call_behavior']=='校验反馈后再决策' and q['status']=='PASS' for q in questions),
        'cost_is_usage_estimate_not_invoice':True,'app_or_real_database_acceptance':False}
    outliers=[];thresholds={};seen=set()
    for metric,label in [('seconds','整题耗时'),('cost_cny','整题费用'),('actual_http_calls','API次数')]:
        candidates=[q for q in measured if q.get(metric) is not None];values=[q[metric] for q in candidates]
        q1,q3=percentile(values,.25),percentile(values,.75);limit=q3+1.5*(q3-q1) if values else None;thresholds[metric]={'q1':q1,'q3':q3,'iqr_upper':limit,'method':'linear quantile, Q3+1.5 IQR; top5 retained even below threshold'}
        for rank,q in enumerate(sorted(candidates,key=lambda r:r[metric],reverse=True)[:5],1):
            observed,hypothesis=explain(q,apis);outliers.append({'metric':label,'rank':rank,'kind':'最大值' if rank==1 else '高值','value':q[metric],
                'execution_id':q['execution_id'],'id':q['id'],'repeat':q['repeat'],'text':q['text'],'seconds':q['seconds'],'api_calls':q['actual_http_calls'],
                'cost_cny':q['cost_cny'],'status':q['status'],'stop_reason':q['stop_reason'],'above_iqr_threshold':q[metric]>limit if limit is not None else False,
                'observed_explanation':observed,'unconfirmed_cause':hypothesis,'evidence':q['evidence']})
    if measured:
        q=min(measured,key=lambda r:r['seconds']);a,h=explain(q,apis);outliers.append({'metric':'整题耗时','rank':1,'kind':'最小值','value':q['seconds'],'execution_id':q['execution_id'],'id':q['id'],'repeat':q['repeat'],'text':q['text'],'seconds':q['seconds'],'api_calls':q['actual_http_calls'],'cost_cny':q['cost_cny'],'status':q['status'],'stop_reason':q['stop_reason'],'observed_explanation':a,'unconfirmed_cause':h,'evidence':q['evidence']})
    if apis:
        slow=max(apis,key=lambda a:a['seconds']);summary['slowest_api_request']=slow
    audit={'requests_equal_question_sum':len(apis)==sum(q['actual_http_calls'] for q in questions),
        'known_question_costs_equal_request_costs':abs(sum(knowncosts)-totalcost)<1e-8,
        'network_time_not_above_question_time':all(q['non_api_seconds']>=-.005 for q in questions),
        'all_inventory_unchanged':all(q['inventory_unchanged'] for q in questions),
        'declared_vs_wire_disagreements':[q['execution_id'] for q in questions if q['declared_model_invocations'] is not None and q['declared_model_invocations']!=q['actual_http_calls']]}
    report=ROUND/'reports';report.mkdir(exist_ok=True)
    jsonlines(report/'逐题记录.jsonl',questions);jsonlines(report/'每题均值.jsonl',averages);jsonlines(report/'API明细.jsonl',apis)
    write(report/'summary.json',summary);write(report/'extremes.json',{'thresholds':thresholds,'records':outliers});write(report/'audit.json',audit)
    write(report/'workbook-data.json',{'summary':summary,'questions':measured,'averages':averages,'apis':apis,'extremes':outliers,'audit':audit})
    write(report/'未执行.json',summary['blocked_records'])
    lines=['# P8.6 DeepSeek 基线结果','', '所有数据均为合成数据；本地AI流程真实调用DeepSeek，Jev未启用。人工标注复核待完成。','',
        f"正式记录{len(questions)}/720题次，其中实际执行{len(measured)}题次，未执行{summary['not_run_questions']}题次；独立输入{len(grouped)}个，实际HTTP {len(apis)}次。零调用题{summary['zero_call_questions']}题，超过两次调用{summary['over_two_call_questions']}题。",'',
        '| 统计项 | 数值 |','|---|---:|',
        f"| 每题平均耗时 秒 | {summary['question_seconds']['mean']} |",f"| 每题P95 秒 | {summary['question_seconds']['p95']} |",f"| 单次API平均耗时 秒 | {summary['api_seconds']['mean']} |",f"| 每题平均API次数 | {summary['api_calls_per_question']} |",f"| 每题平均费用 元 | {summary['cost_per_question_cny']} |",f"| 单次API平均费用 元 | {summary['cost_per_api_call_cny']} |",f"| 已知用量费用小计 元 | {totalcost} |",'',
        '费用按返回Token、缓存及实际请求时段估算，不是平台账单。失败请求计入实际调用次数和耗时；未知用量不按零费用计算。每题平均包含合法零调用路径，单次API平均只含实际出站请求。','',
        '## 分遍结果','', '| 遍数 | 题次 | PASS | FAIL | REVIEW | API | 平均秒 | P95秒 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in by_repeat:lines.append(f"| {r['repeat']} | {r['questions']} | {r['counts'].get('PASS',0)} | {r['counts'].get('FAIL',0)} | {r['counts'].get('REVIEW',0)} | {r['calls']} | {r['time']['mean']:.3f} | {r['time']['p95']:.3f} |")
    lines+=['','## 极端值与原因','']
    for e in outliers:lines += [f"### {e['metric']} {e['kind']} 第{e['rank']}名 {e['execution_id']}",'',e['text'],'',f"整题{e['seconds']:.3f}秒；API {e['api_calls']}次；费用{e['cost_cny']}元；状态{e['status']}。",'',e['observed_explanation'],'',e['unconfirmed_cause'],'',f"证据：{e['evidence']}",'']
    lines+=['## 比较边界','', '当前逐件模型不支持半件扣减，旧批次数量基线不直接作为同样本对照。后续Jev比较需固定源码、库存语义、用例和价格时段；如用这些结果调优，应另备独立评估集。']
    (report/'测试结果与极端值.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'questions':len(questions),'api_calls':len(apis),'outlier_records':len(outliers),'audit':audit},ensure_ascii=True))
if __name__=='__main__':main()
