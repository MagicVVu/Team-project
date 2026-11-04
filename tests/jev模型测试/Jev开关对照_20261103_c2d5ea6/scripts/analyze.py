"""Auditable paired analysis. Never erase failures, timeouts, or unknown costs."""
import collections,csv,json,math,random,statistics
from datetime import datetime,timedelta
from decimal import Decimal
from pathlib import Path
from prepare import ROUND,HEAD,write

def rows(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
def distribution(values):
    a=sorted(values)
    return {'n':len(a),'mean':statistics.mean(a) if a else None,'min':a[0] if a else None,'p50':a[math.ceil(.5*len(a))-1] if a else None,'p90':a[math.ceil(.9*len(a))-1] if a else None,'p95':a[math.ceil(.95*len(a))-1] if a else None,'max':a[-1] if a else None}
def money(w):
    u=w.get('usage') or {};provider=w['provider'];known=False;estimate=None;native=None;cache_hit=None;cache_miss=None
    if provider=='deepseek':
        prompt=u.get('prompt_tokens');output=u.get('completion_tokens')
        cache_hit=u.get('prompt_cache_hit_tokens',(u.get('prompt_tokens_details') or {}).get('cached_tokens'))
        cache_miss=u.get('prompt_cache_miss_tokens')
        if isinstance(prompt,int) and isinstance(output,int):
            native=(Decimal(prompt)*2+Decimal(output)*8)/1000000
            if cache_miss is None and isinstance(cache_hit,int):cache_miss=prompt-cache_hit
            if isinstance(cache_hit,int) and isinstance(cache_miss,int) and cache_hit>=0 and cache_miss>=0 and cache_hit+cache_miss==prompt:
                local=datetime.fromisoformat(w['started_at'])+timedelta(hours=8)
                # Run is November 3/4, ordinary weekdays; timestamps retained for audit.
                peak=local.weekday()<5 and (9<=local.hour<12 or 14<=local.hour<18)
                scale=Decimal(1) if peak else Decimal('.5')
                estimate=(Decimal(cache_hit)*Decimal('.04')+Decimal(cache_miss)*2+Decimal(output)*8)/1000000*scale;known=True
        if native is None:
            req=w['request'];size=len(json.dumps(req,ensure_ascii=False).encode('utf-8'))
            native=(Decimal(size+1024)*2+Decimal(req.get('max_tokens',768))*8)/1000000
        reserve_cny=native
    else:
        prompt=u.get('input_tokens');output=u.get('output_tokens')
        if isinstance(prompt,int) and prompt>=0:
            estimate=Decimal(prompt)*Decimal('.042')/1000000;native=estimate;known=True
        else:native=Decimal(65536)*Decimal('.042')/1000000
        reserve_cny=native*8
    return {'cost_known':known,'cost_native':float(estimate) if known else None,'currency':'CNY' if provider=='deepseek' else 'USD','budget_cny':float(reserve_cny),'prompt_tokens':prompt,'output_tokens':output,'cache_hit':cache_hit,'cache_miss':cache_miss}

def explain(q,api):
    reasons=[]
    if q['jev_http_calls']:reasons.append(f"增加Jev请求{q['jev_http_calls']}次")
    jev=q['jev_audit']
    reasons += list(dict.fromkeys('Jev回退：'+str(a.get('reason')) for a in jev if a.get('status')=='fallback' and a.get('reason')))
    if q['deepseek_http_calls']>1:reasons.append(f"DeepSeek自主循环{q['deepseek_http_calls']}次，步骤和反馈见原始trace")
    if any(a.get('transport_error') for a in api):reasons.append('包含超时或取消请求，用量未知部分保留预留')
    if q['actual_http_calls']==0:reasons.append('原规则或保护路径零HTTP调用')
    if api:reasons.append(f"HTTP累计{sum(a['latency_ms'] for a in api)/1000:.3f}秒")
    reasons.append('客户端数据不能进一步区分公网延迟与供应商排队')
    return '；'.join(reasons)

def csvout(name,headers,data):
    with (ROUND/'reports'/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(headers);writer.writerows(data)

def main():
    formal=sorted((ROUND/'runs').glob('formal-*/started.json'))
    if len(formal)!=1:raise SystemExit('Need one formal run')
    folder=formal[0].parent
    folders=[folder]+[p.parent for p in sorted((ROUND/'runs').glob('continuation-*/started.json'))]
    raw_questions=[];apis=[];all_inputs=[]
    for source in folders:
        for a in rows(source/'requests.jsonl'):
            a['original_wire_id']=a['wire_id'];a['wire_id']=source.name+'/'+a['wire_id'];a['source_folder']=str(source.relative_to(ROUND));apis.append(a)
        for q in rows(source/'questions.jsonl'):
            q['wire_ids']=[source.name+'/'+w for w in q['wire_ids']];q['source_folder']=str(source.relative_to(ROUND));raw_questions.append(q)
        all_inputs.extend(rows(source/'inputs.jsonl'))
    selected={};superseded=[]
    for q in raw_questions:
        key=(q['mode'],q['repeat'],q['id'])
        if key in selected:
            prior=selected[key]
            if prior['status']!='BLOCKED':raise RuntimeError('A completed PASS/FAIL was rerun; do not silently select results')
            superseded.append(prior)
        selected[key]=q
    qs=list(selected.values())
    latest=folders[-1]/'complete.json'
    complete=json.loads(latest.read_text(encoding='utf-8')) if latest.exists() else {'complete':False,'stop_reason':'RUNNING'}
    if len(folders)>1:
        complete={**complete,'phase':'formal_with_authorized_continuation','original_run_stop_reason':json.loads((folder/'complete.json').read_text(encoding='utf-8'))['stop_reason'],'original_results_not_modified':True,'continued_only_missing_or_budget_blocked':True}
        complete.update(batch_questions=complete.get('questions'),batch_status_counts=complete.get('status_counts'),questions=len(qs),actual_http_calls=len(apis),raw_question_executions=len(raw_questions),status_counts=dict(collections.Counter(q['status'] for q in qs)))
    bywire={a['wire_id']:a for a in apis}
    for a in apis:
        a.update(money(a));a['seconds']=a['latency_ms']/1000;a['evidence']=a['source_folder']+'/requests.jsonl#'+a['original_wire_id']
    for q in qs:
        wires=[bywire[w] for w in q['wire_ids']];q['seconds']=q['question_ms']/1000
        q['api_seconds']=sum(w['seconds'] for w in wires)
        q['known_cny']=sum(w['cost_native'] for w in wires if w['provider']=='deepseek' and w['cost_known'])
        q['known_usd']=sum(w['cost_native'] for w in wires if w['provider']=='jev' and w['cost_known'])
        q['unknown_calls']=sum(not w['cost_known'] for w in wires)
        q['estimated_cny_at_budget_fx']=q['known_cny']+8*q['known_usd'] if not q['unknown_calls'] else None
        q['conservative_cny']=sum(w['budget_cny'] for w in wires)
        q['failed_checks']=[k for k,v in q['checks'].items() if not v]
        q['evidence']=q['source_folder']+'/questions.jsonl#'+q['mode']+':'+str(q['repeat'])+':'+q['id']
        q['explanation']=explain(q,wires)
        q['issue_category']='自动断言待人工复核' if q['status']=='FAIL' else '预算/环境' if q['status']=='BLOCKED' else ''
        if q['error_code']:q['issue_category']='环境或适配异常'
        elif q['output'].get('error_code') in {'INVALID_MODEL_OUTPUT','EMPTY_MODEL_OUTPUT'}:q['issue_category']='模型结构输出'
        elif q['output'].get('stop_reason') in {'repeated_plan','no_progress'}:q['issue_category']='自主循环无进展'
        elif q['failed_checks'] and all(k in {'status','stop_reason','error_code'} for k in q['failed_checks']):q['issue_category']='状态/错误码契约待复核'
    def summarize(data):
        data=[q for q in data if q['status'] in {'PASS','FAIL'}]
        wires=[bywire[w] for q in data for w in q['wire_ids']]
        result={'questions':len(data),'pass':sum(q['status']=='PASS' for q in data),'fail':sum(q['status']=='FAIL' for q in data),'pass_rate':sum(q['status']=='PASS' for q in data)/len(data) if data else None,'question_seconds':distribution([q['seconds'] for q in data]),'api_seconds':distribution([w['seconds'] for w in wires]),'api_calls':sum(q['actual_http_calls'] for q in data),'mean_calls':statistics.mean(q['actual_http_calls'] for q in data) if data else None,'deepseek_calls':sum(q['deepseek_http_calls'] for q in data),'jev_calls':sum(q['jev_http_calls'] for q in data),'zero_call_questions':sum(q['actual_http_calls']==0 for q in data),'known_cny':sum(q['known_cny'] for q in data),'known_usd':sum(q['known_usd'] for q in data),'unknown_calls':sum(q['unknown_calls'] for q in data),'conservative_cny':sum(q['conservative_cny'] for q in data),'known_estimated_cny_at_budget_fx':sum(q['known_cny']+8*q['known_usd'] for q in data),'mean_estimated_cny_at_budget_fx':sum(q['estimated_cny_at_budget_fx'] for q in data)/len(data) if data and all(q['estimated_cny_at_budget_fx'] is not None for q in data) else None,'jev_status':dict(collections.Counter(a['status'] for q in data for a in q['jev_audit'])),'jev_reason':dict(collections.Counter(str(a.get('reason')) for q in data for a in q['jev_audit']))}
        result['mean_conservative_cny_per_question']=result['conservative_cny']/len(data) if data else None
        result['mean_conservative_cny_per_api']=result['conservative_cny']/len(wires) if wires else None
        result['mean_known_cost_lower_bound_per_api']=result['known_estimated_cny_at_budget_fx']/len(wires) if wires else None
        return result
    index={(q['mode'],q['repeat'],q['id']):q for q in qs};pairs=[]
    for q in qs:
        if q['mode']!='off':continue
        other=index.get(('assist',q['repeat'],q['id']))
        if other and q['status'] in {'PASS','FAIL'} and other['status'] in {'PASS','FAIL'}:
            pairs.append({'id':q['id'],'repeat':q['repeat'],'scenario_id':q['scenario_id'],'group_id':q['group_id'],'stratum':q['stratum'],'text':q['text'],'off':q,'assist':other,'accuracy_delta':int(other['status']=='PASS')-int(q['status']=='PASS'),'seconds_delta':other['seconds']-q['seconds'],'calls_delta':other['actual_http_calls']-q['actual_http_calls'],'conservative_cny_delta':other['conservative_cny']-q['conservative_cny']})
    def paired_summary(data):
        improve=sum(p['accuracy_delta']==1 for p in data);regress=sum(p['accuracy_delta']==-1 for p in data);n=improve+regress
        pvalue=min(1,2*sum(math.comb(n,k) for k in range(min(improve,regress)+1))/(2**n)) if n else 1
        clusters=collections.defaultdict(list)
        for p in data:clusters[p['scenario_id']].append(p['accuracy_delta'])
        rng=random.Random(20261103);groups=list(clusters.values());bootstrap=[]
        if groups:
            for _ in range(2000):
                selected=[rng.choice(groups) for _ in groups];bootstrap.append(sum(sum(x) for x in selected)/sum(len(x) for x in selected))
        bootstrap.sort()
        return {'pairs':len(data),'improved':improve,'regressed':regress,'both_pass':sum(p['off']['status']==p['assist']['status']=='PASS' for p in data),'both_fail':sum(p['off']['status']==p['assist']['status']=='FAIL' for p in data),'accuracy_delta':statistics.mean(p['accuracy_delta'] for p in data) if data else None,'cluster_bootstrap_95':[bootstrap[49],bootstrap[1949]] if bootstrap else None,'mcnemar_exact_descriptive_p':pvalue,'seconds_delta':distribution([p['seconds_delta'] for p in data]),'calls_delta':distribution([p['calls_delta'] for p in data]),'clusters':len(groups)}
    comparison_rows=[p[mode] for p in pairs for mode in ['off','assist']]
    summaries={stratum:{mode:summarize([q for q in comparison_rows if q['stratum']==stratum and q['mode']==mode]) for mode in ['off','assist']} for stratum in ['主功能集','Jev专项']}
    paired={s:paired_summary([p for p in pairs if p['stratum']==s]) for s in summaries}
    repeat_summaries={str(repeat):{s:{mode:summarize([q for q in comparison_rows if q['repeat']==repeat and q['stratum']==s and q['mode']==mode]) for mode in ['off','assist']} for s in summaries} for repeat in [1,2]}
    task_ids={r['id'] for r in rows(ROUND/'datasets/multi.jsonl')}
    task_results=[]
    for mode in ['off','assist']:
        for repeat in [1,2]:
            for ident in task_ids:
                steps=[q for q in comparison_rows if q['mode']==mode and q['repeat']==repeat and q['scenario_id']==ident]
                if len(steps)==4:task_results.append({'mode':mode,'repeat':repeat,'id':ident,'passed':all(q['status']=='PASS' for q in steps)})
        summaries['主功能集'][mode]['complete_four_turn_tasks']=sum(t['mode']==mode for t in task_results)
        summaries['主功能集'][mode]['passed_four_turn_tasks']=sum(t['mode']==mode and t['passed'] for t in task_results)
    groups=[]
    for group in dict.fromkeys(q['group_id'] for q in qs):
        for mode in ['off','assist']:groups.append({'group':group,'mode':mode,**summarize([q for q in comparison_rows if q['group_id']==group and q['mode']==mode])})
    averages=[]
    for ident in dict.fromkeys(q['id'] for q in qs):
        values=[q for q in comparison_rows if q['id']==ident]
        if not values:continue
        one=values[0]
        averages.append({'id':ident,'text':one['text'],'group':one['group_id'],'stratum':one['stratum'],**{mode:summarize([q for q in values if q['mode']==mode]) for mode in ['off','assist']}})
    extremes=[]
    for mode in ['off','assist']:
        valid=[q for q in qs if q['mode']==mode and q['status'] in {'PASS','FAIL'}]
        for field in ['seconds','actual_http_calls','conservative_cny']:
            values=sorted(q[field] for q in valid)
            q1=values[math.ceil(len(values)*.25)-1] if values else 0;q3=values[math.ceil(len(values)*.75)-1] if values else 0
            threshold=q3+1.5*(q3-q1)
            for q in sorted(valid,key=lambda q:q[field],reverse=True)[:5]:extremes.append({'mode':mode,'metric':field,'value':q[field],'iqr_threshold':threshold,'above_iqr':q[field]>threshold,'id':q['id'],'repeat':q['repeat'],'explanation':q['explanation'],'evidence':q['evidence']})
    # First-turn premises must match exactly before comparing; subsequent context is allowed to diverge.
    inputs=all_inputs;ih={(x['mode'],x['repeat'],x['question_id']):x for x in inputs if x.get('turn')==1}
    bad=[]
    for (mode,repeat,ident),x in ih.items():
        y=ih.get(('assist',repeat,ident))
        if mode=='off' and y and x['initial_state_sha256']!=y['initial_state_sha256']:bad.append((repeat,ident))
    planned=[]
    for kind in ['single','multi','jev_special']:
        for row in rows(ROUND/'datasets'/f'{kind}.jsonl'):
            identifiers=[row['id']+f'-t{i+1}' for i in range(len(row['turns']))] if kind=='multi' else [row['id']]
            for mode in ['off','assist']:
                for repeat in [1,2]:
                    planned.extend({'id':ident,'mode':mode,'repeat':repeat,'status':'BLOCKED','reason':complete.get('stop_reason') or 'not_executed'} for ident in identifiers if (mode,repeat,ident) not in index)
    write(ROUND/'reports/unexecuted.json',planned)
    provider_summaries=[]
    for mode in ['off','assist']:
        for provider in ['deepseek','jev']:
            values=[w for w in apis if w['mode']==mode and w['provider']==provider];known=[w for w in values if w['cost_known']]
            provider_summaries.append({'mode':mode,'provider':provider,'requests':len(values),'request_seconds':distribution([w['seconds'] for w in values]),'known_usage_requests':len(known),'unknown_usage_requests':len(values)-len(known),'known_cost_native':sum(w['cost_native'] for w in known),'known_requests_mean_cost_native':statistics.mean(w['cost_native'] for w in known) if known else None,'currency':'CNY' if provider=='deepseek' else 'USD','conservative_cny':sum(w['budget_cny'] for w in values)})
    result={'source':HEAD,'run':str(folder.relative_to(ROUND)),'run_folders':[str(p.relative_to(ROUND)) for p in folders],'complete':complete,'summaries':summaries,'repeat_summaries':repeat_summaries,'provider_summaries':provider_summaries,'paired':paired,'formal_questions':len(qs),'raw_question_executions':len(raw_questions),'superseded_budget_blocked_attempts':superseded,'formal_apis':len(apis),'unpaired_executions':len(qs)-2*len(pairs),'unexecuted':len(planned),'initial_premise_mismatches':bad,'both_modes_fail_does_not_mean_jev_regression':True,'platform_bill_verified':False,'usd_budget_fx':8,'fx_is_budget_assumption':True,'human_review_status':'pending','groups':groups,'averages':averages,'extremes':extremes,'questions':qs,'apis':apis,'pairs':pairs,'comparison_uses_only_completed_pairs':True,'all_execution_totals':{mode:summarize([q for q in qs if q['mode']==mode]) for mode in ['off','assist']}}
    write(ROUND/'reports/analysis.json',result)
    write(ROUND/'reports/summary.json',{k:v for k,v in result.items() if k not in {'questions','apis','pairs','averages'}})
    csvout('逐题开关对照.csv',['编号','遍数','分组','输入','关闭结果','开启结果','关闭秒','开启秒','耗时差秒','关闭DeepSeek次数','开启DeepSeek次数','开启Jev次数','关闭保守元','开启保守折算元','关闭未知用量次数','开启未知用量次数'],[[p['id'],p['repeat'],p['group_id'],p['text'],p['off']['status'],p['assist']['status'],p['off']['seconds'],p['assist']['seconds'],p['seconds_delta'],p['off']['deepseek_http_calls'],p['assist']['deepseek_http_calls'],p['assist']['jev_http_calls'],p['off']['conservative_cny'],p['assist']['conservative_cny'],p['off']['unknown_calls'],p['assist']['unknown_calls']] for p in pairs])
    csvout('问题清单.csv',['编号','遍数','模式','分组','类别','未满足断言','实际回复','停止原因','Jev状态','证据','人工复核'],[[q['id'],q['repeat'],q['mode'],q['group_id'],q['issue_category'],'；'.join(q['failed_checks']),q['output'].get('reply'),q['output'].get('stop_reason'),json.dumps(q['jev_audit'],ensure_ascii=False),q['evidence'],'待确认'] for q in qs if q['status']!='PASS'])
    print(json.dumps({'formal_questions':len(qs),'pairs':len(pairs),'summary':summaries,'mismatched_initial_premises':len(bad)},ensure_ascii=False))
if __name__=='__main__':main()
