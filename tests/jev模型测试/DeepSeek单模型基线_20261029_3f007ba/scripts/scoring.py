"""Detailed checks are independent of model output normalization."""
from decimal import Decimal, InvalidOperation

def equal(actual,expected):
    if actual is None: return expected is None
    if isinstance(expected,(str,int,float)) and not isinstance(expected,bool):
        try: return Decimal(str(actual))==Decimal(str(expected))
        except (InvalidOperation,ValueError,TypeError): pass
    return actual==expected

def checks(expected,frame,unchanged=True,previous_draft=None):
    domain=frame.get('result') or {}; draft=domain.get('draft') or {}
    out={'inventory_unchanged':unchanged}
    if 'draft' in expected:
        out['draft_exists']=bool(draft)
        for k,v in expected['draft'].items(): out['draft.'+k]=equal(draft.get(k),v)
    if expected.get('no_draft'): out['no_draft']=not draft
    if 'kind' in expected: out['kind']=frame.get('kind')==expected['kind']
    if 'status' in expected: out['status']=domain.get('status')==expected['status']
    if 'error_code' in expected: out['error_code']=frame.get('error_code')==expected['error_code']
    if 'preserve_active' in expected: out['preserve_active']=frame.get('preserve_active')==expected['preserve_active']
    for field in expected.get('absent_fields',[]): out['absent.'+field]=field not in draft
    if 'batch_id' in expected:
        facts=domain.get('facts',[])
        out['target_batch']=len(facts)==1 and facts[0].get('id')==expected['batch_id']
    allfacts='\n'.join(str(v) for v in frame.get('facts',{}).values())
    for text in expected.get('fact_contains',[]): out['fact.'+text]=text in allfacts
    if expected.get('clarification'):
        out['clarification']=not draft and (frame.get('kind') in {'needs_input','clarify'} or domain.get('status')=='needs_clarification')
    if 'reads' in expected:
        actual={r['kind'] for r in frame.get('plan',{}).get('reads',[])}
        out['read_routing']=set(expected['reads'])<=actual
    if expected.get('same_draft'):
        out['same_draft']=bool(previous_draft) and (frame.get('edit') or {}).get('draft_id')==previous_draft
    kind=expected.get('calculation_kind')
    calculations=[e.get('result',{}) for e in frame.get('evidence',[]) if e.get('kind')=='verified_calculation']
    if kind=='risk':
        risks=[r for c in calculations for r in c.get('risks',[])]
        out['risk_evidence']=len(risks)==1 and risks[0].get('level')==expected['risk_level'] and bool(risks[0].get('evidence')) and bool(risks[0].get('ruleset_version'))
    elif kind:
        key={'consumption':'consumption_summary','forecast':'forecast','purchase':'recommendations'}[kind]
        records=[r for c in calculations for r in c.get(key,[])]
        out['calculation_present']=len(records)==1
        for field,value in expected.get('calculation_fields',{}).items():
            out['calculation.'+field]=len(records)==1 and equal(records[0].get(field),value)
    return out

def classify(row,frame,check_result,error=None):
    code=error or frame.get('error_code') or (frame.get('result') or {}).get('error_code')
    if code in {'BUDGET_EXCEEDED','MODEL_NOT_CONFIGURED','PRICING_NOT_VERIFIED'}: return 'BLOCKED','环境问题：调用前预算或配置保护停止'
    if not error and all(check_result.values()): return 'PASS',None
    calculations=[e.get('result',{}) for e in frame.get('evidence',[]) if e.get('kind')=='verified_calculation']
    if row.get('category')=='风险查询' and any(r.get('level')=='unknown' and 'NO_APPLICABLE_RULE' in r.get('reason_codes',[]) for c in calculations for r in c.get('risks',[])):
        return 'REVIEW','样本标注问题：预期绿色，但当前没有适用的已审核规则'
    if any(c.get('error_code')=='ITEM_NOT_FOUND' for c in calculations):
        return 'FAIL','版本契约或适配问题：批次 b1 与规划商品 milk 未对应，需定位'
    if code and any(t in code for t in ('NOT_CONFIGURED','BUDGET','HTTP_401','HTTP_402','HTTP_429','UNAVAILABLE','TIMEOUT')): return 'FAIL','环境问题'
    plan=frame.get('plan',{})
    if code and any(t in code for t in ('UNSUPPORTED','CONTEXT_UNAVAILABLE')): return 'FAIL','未支持功能'
    if not plan or error and ('INVALID' in error or 'PLAN' in error): return 'FAIL','模型输出问题'
    if check_result.get('read_routing') is False: return 'FAIL','模型理解问题'
    # Automated attribution is a lead, not a developer-confirmed root cause.
    return 'FAIL','程序或模型问题待定位'
