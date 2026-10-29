"""Additional independent assertions; original legacy pass/fail remains intact."""
from decimal import Decimal
from scoring import checks

def expected_for(row):
    ident=row['id']
    if not ident.startswith('p84-'): return None
    group=int(ident.split('-')[1]); v=int(ident.split('-')[2])-1
    result={'no_inventory_write':True}
    draft=None
    if group in {6,7,8,12,13}:
        quantity='3' if group==6 else '6' if group in {7,13} else ['1','2','0.5','1','1','2'][v] if group==8 else ['1','2','0.5','1','1','1'][v]
        draft={'action':'DISCARD' if group in {12,13} else 'CONSUME','batch_id':'b1','quantity':quantity,'unit':'盒','expected_version':4}
        if group==13: draft['discard_mode']='all'
    if group==10:
        draft={'action':'MOVE','batch_id':'b1','to_location':['冷藏室','厨房','餐边柜','冰箱上层','储物柜','书房'][v],'expected_version':4}
        result['absent_fields']=['quantity']
    if group==11:
        draft={'action':'OPEN','batch_id':'b1','opened_at':'2026-10-14' if v in {0,2,4} else '2026-10-15','expected_version':4}
        result['absent_fields']=['quantity']
    if group in {14,15}:
        draft={'action':'ADD' if group==14 else 'PLAN_ADD','name':'牛奶','quantity':['2','1','3','2','1','2'][v],'unit':'盒'}
        if group==14: draft['location']=['冰箱','厨房','储物柜','冰箱上层','厨房','餐边柜'][v]
    if group==23: draft={'action':'CONSUME','batch_id':'b1','quantity':'2','unit':'盒','expected_version':4}; result['kind']='edit'
    if group==24:
        draft={'action':'MOVE','batch_id':'b1','to_location':['厨房','冰箱','餐边柜','储物柜','书房','冷藏室'][v],'expected_version':4}; result['kind']='edit'
    if draft: result.update(draft=draft,status='needs_confirmation')
    if group==16: result.update(no_draft=True,batch_id='b1',fact_contains=['登记数量 6 盒','位置 冰箱'])
    if group==17: result.update(no_draft=True,reads=['dates'],fact_contains=['2026-11-20'] if v!=1 else ['开封日期 未知'])
    if group in {18,19,20,21}: result.update(no_draft=True,reads=[{18:'risk',19:'consumption',20:'forecast',21:'purchase'}[group]])
    return result if len(result)>1 else None

def audit(row):
    expected=expected_for(row)
    if expected is None: return {'covered':False,'note':'original oracle retained; no additional independent field gold'}
    checked=checks(expected,row.get('frame',{}),row.get('inventory_unchanged_by_ai',False))
    calculations=[x.get('result',{}) for x in row.get('frame',{}).get('evidence',[]) if x.get('kind')=='verified_calculation']
    group=int(row['id'].split('-')[1])
    if group in {19,20,21}:
        checked['calculation_available']=bool(calculations) and all(c.get('status')!='error' for c in calculations)
    return {'covered':True,'passed':all(checked.values()),'expected':expected,'checks':checked,
        'failed_checks':[k for k,v in checked.items() if not v],
        'note':'additional contract audit; original legacy result retained; no score based on wording naturalness'}
