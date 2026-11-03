"""Audit saved synthetic-model outputs; makes no provider or inventory calls."""
import json
import math
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/ai-english'


def audit(label):
    cases={c['id']:c for c in json.loads((REPORT/'cases.json').read_text(encoding='utf-8'))}
    rows=[json.loads(line) for line in (REPORT/(label+'.jsonl')).read_text(encoding='utf-8').splitlines()]
    summary={'label':label,'synthetic_only':True,'post_fix_nonblind_regression':label=='real-final-regression',
        'human_review_status':'pending','joint_app_acceptance':False,'by_locale':{}}
    summary['post_fix_nonblind_regression']='regression' in label or label=='real-selection-final'
    for locale in ('zh-CN','en'):
        selected=[r for r in rows if r['locale']==locale];problems=[];drafts=0;boundary=needed=clarified=0;calls=Counter();stops=Counter();latencies=[];bad_language=[]
        for row in selected:
            case=cases[row['id']];original=row.get('text',case[locale]);o=row.get('output') or {};frame=o.get('resolved') or {};domain=frame.get('result') or {};draft=domain.get('draft')
            def check(condition,code):
                if not condition:problems.append({'id':row['id'],'code':code})
            check(o.get('inventory_writes') is False and o.get('shopping_writes') is False,'write_boundary')
            check(o.get('original_text')==original and o.get('locale')==locale,'original_and_locale')
            calls[o.get('model_calls',0)]+=1;stops[o.get('stop_reason','missing')]+=1
            if 'elapsed_ms' in o:latencies.append(o['elapsed_ms'])
            if case['expected']=='input':
                needed+=1;clarified+=int(o.get('status')=='needs_input' and not draft)
            if draft:
                drafts+=1;g=case['group'];expected={'ADD_PORTION':'ADD','edit':'MOVE'}.get(case['expected'],case['expected'])
                check(draft.get('action')==expected,'action')
                check(expected in {'ADD','PLAN_ADD','MOVE','OPEN','CONSUME','DISCARD'},'unexpected_draft')
                if expected in {'MOVE','OPEN','CONSUME','DISCARD'}:
                    check(draft.get('batch_id')=='b1' and draft.get('expected_version')==4 and draft.get('name')=='牛奶','target_version')
                if expected in {'CONSUME','DISCARD'}:check(Decimal(draft['quantity'])==1 and draft['unit']=='盒','whole_item_unit')
                if expected=='OPEN':check(draft.get('opened_at')==('2026-10-14' if g=='open_yesterday' else '2026-10-15'),'opening_date')
                if expected=='MOVE':check(draft.get('to_location') in ({'study','the study'} if locale=='en' else {'书房'}),'destination')
                if expected=='ADD':
                    check(Decimal(draft['quantity'])==Decimal(500 if g=='add_weight' else 2) and draft['unit']==('g' if g=='add_weight' else '瓶'),'add_amount_unit')
                if expected=='PLAN_ADD':check(Decimal(draft['quantity'])==2 and draft['unit']=='瓶','shopping_amount_unit')
                for key,source in frame.get('field_sources',{}).items():
                    if source.get('source')=='current_text':check(bool(source.get('quote')) and source['quote'] in original,'quote_source_'+key)
            if case['expected'] in {'input','no_write','pending','new_task','query','empty'}:
                boundary+=1;check(not draft,'read_or_blocked_created_draft')
            for fact in domain.get('facts',[]):
                check(fact['name']=='牛奶' and Decimal(fact['quantity'])==1 and fact['version']==4 and fact['id'] in {'b1','b2'},'query_fact')
                if case['group']=='ordinal':check(fact['id']=='b2','ordinal_target')
            if locale=='en':
                reply=o.get('reply','')
                # Only verified real names/locations and quoted history may be
                # Chinese. This dataset contains no quoted-history scenario.
                for value in ('牛奶','冰箱','厨房','书房'):reply=reply.replace(value,'')
                if re.search('[\u4e00-\u9fff]',reply):bad_language.append(row['id'])
        latencies.sort()
        summary['by_locale'][locale]={'inputs':len(selected),'outcome_passed':sum(bool(r.get('passed')) for r in selected),
            'outcome_rate':sum(bool(r.get('passed')) for r in selected)/len(selected),'clarification_required':needed,'clarification_recalled':clarified,
            'clarification_recall':clarified/needed if needed else None,'returned_drafts':drafts,'read_or_boundary_cases':boundary,
            'semantic_fact_violations':problems,'unlocalized_system_reply_cases':bad_language,
            'model_calls_distribution':dict(sorted(calls.items())),'stop_reason_distribution':dict(stops),
            'p95_ms':latencies[math.ceil(.95*len(latencies))-1] if latencies else None,
            'failed_outcomes':[r['id'] for r in selected if not r.get('passed')]}
    (REPORT/(label+'-audit.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary


if __name__=='__main__':
    for label in ('real-dev-first','real-holdout-first','real-final-regression','real-corrected-regression','real-selection-regression','real-selection-final'):
        if (REPORT/(label+'-summary.json')).exists():print(json.dumps(audit(label),ensure_ascii=True))
