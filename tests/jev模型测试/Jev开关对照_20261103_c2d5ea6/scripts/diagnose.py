"""Evidence-based triage, no extra model requests and no replacement gold."""
import collections,json,csv
from prepare import ROUND,write
d=json.loads((ROUND/'reports/analysis.json').read_text(encoding='utf-8'))
cases=[]
for q in d['questions']:
    if q['status']=='PASS':continue
    out=q['output'];plan=out.get('plan') or {};fields=plan.get('fields') or {};audits=q['jev_audit'];failed=q['failed_checks'];notes=[]
    category=q['issue_category']
    if out.get('error_code') in {'INVALID_MODEL_OUTPUT','EMPTY_MODEL_OUTPUT'}:notes.append('响应结构或解析失败；核对API原文及解析错误，不归为业务数据库问题。')
    if plan.get('action')=='MOVE' and 'location' in fields and 'to_location' not in fields:
        notes.append('模型将移动目的地放在location字段，缺少to_location；源码因缺目标位置追问。')
        category='模型字段理解问题'
    if plan.get('action') and plan.get('speech_act')=='new_task':
        notes.append('计划同时带业务动作与new_task语气，可能被当成开始新话题；检查理解输出和归一化。')
        category='模型意图与流程交互'
    if failed and all(k in {'status','stop_reason','error_code'} for k in failed):
        notes.append('只差状态或错误码，业务事实可能正确；先由团队核对当前契约，不直接称计算错误。')
        category='版本契约或标注待复核'
    if any(a.get('status')=='guarded' for a in audits):
        notes.append('Jev保护确实介入；原文含计划或询问语气时，先核对产品允许何时生成采购草稿，保护性澄清不应直接称程序错误。')
        category='Jev保护与预期契约待复核'
    if any(a.get('reason')=='JEV_TIMEOUT' for a in audits):notes.append('Jev已超时回退。这证明新增延迟，但后续DeepSeek答错不能仅凭同时发生就认定由Jev造成。')
    if out.get('stop_reason') in {'no_progress','repeated_plan'}:notes.append('自主循环因无进展或重复停止，核对每步观察与计划是否变化。')
    if not notes:notes.append('需将原文、已知库存、模型计划与失败断言一起人工复核，当前不确定根因。')
    cases.append({'id':q['id'],'repeat':q['repeat'],'mode':q['mode'],'group':q['group_id'],'category':category,'notes':notes,'failed_checks':failed,'evidence':q['evidence'],'human_review_status':'pending'})
stable=[]
for a in d['averages']:
    if a['off']['questions']==a['assist']['questions']==2:
        stable.append({'id':a['id'],'off_pass':a['off']['pass'],'assist_pass':a['assist']['pass'],'stable_regression':a['off']['pass']==2 and a['assist']['pass']==0,'stable_improvement':a['off']['pass']==0 and a['assist']['pass']==2,'any_run_variation':a['off']['pass']==1 or a['assist']['pass']==1})
zero_mismatch=[p['id'] for p in d['pairs'] if p['off'].get('turn')==p['assist'].get('turn')==1 and p['off']['actual_http_calls']==p['assist']['actual_http_calls']==0 and p['off']['checks']!=p['assist']['checks']]
gate_failures=[]
for q in d['questions']:
    if q['mode']!='assist' or not q['id'].startswith('JEV-'):continue
    for audit in q['jev_audit']:
        if audit.get('reason')!='UNCERTAIN_SEMANTICS':continue
        weak=[]
        for key,node in audit.get('nodes',{}).items():
            if node.get('type')!='choice':continue
            confidence=node.get('confidence',0);probability=(node.get('probabilities') or {}).get(node.get('choice'),0)
            if confidence<.8 or probability<.9:weak.append({'node':key,'choice':node.get('choice'),'confidence':confidence,'selected_probability':probability})
        gate_failures.append({'id':q['id'],'repeat':q['repeat'],'below_current_thresholds':weak,'evidence':q['evidence']})
summary={'issue_occurrences':len(cases),'distinct_failed_case_ids':len({c['id'] for c in cases}),'category_occurrences':dict(collections.Counter(c['category'] for c in cases)),'fully_repeated_case_count':len(stable),'stable_regression_ids':[s['id'] for s in stable if s['stable_regression']],'stable_improvement_ids':[s['id'] for s in stable if s['stable_improvement']],'variable_case_count':sum(s['any_run_variation'] for s in stable),'zero_call_assertion_mismatch_ids':zero_mismatch,'no_extra_model_calls':True,'not_human_signoff':True,'issues':cases,'repeat_consistency':stable,'jev_special_confidence_gate_evidence':gate_failures}
write(ROUND/'reports/diagnostics.json',summary)
lookup={(q['id'],q['repeat'],q['mode']):q for q in d['questions']}
with (ROUND/'reports/问题清单.csv').open('w',encoding='utf-8-sig',newline='') as handle:
    writer=csv.writer(handle);writer.writerow(['用例编号','遍数','模式','功能','自动结果','问题分类','实际回复','未满足断言','定位线索','证据','人工复核'])
    for item in cases:
        q=lookup[(item['id'],item['repeat'],item['mode'])]
        writer.writerow([item['id'],item['repeat'],item['mode'],item['group'],q['status'],item['category'],q['output'].get('reply',''),'；'.join(item['failed_checks']),'；'.join(item['notes']),item['evidence'],'待确认'])
print(json.dumps({k:v for k,v in summary.items() if k not in {'issues','repeat_consistency'}},ensure_ascii=False))
