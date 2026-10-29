"""No-model controlled contrasts for fixture version and batch/item selection."""
import asyncio,json,sys
from decimal import Decimal
from pathlib import Path
from prepare import ROUND,write
sys.path.insert(0,str(ROUND/'.snapshot/agent'))
from run import OracleEngine,fixture,NOW,SCOPE
from telemetry import network_guard
from eval.v1.fixtures import fixture as v1fixture
from p3.schemas import Query

async def main():
    results=[]
    with network_guard(False):
        for version in ['old_p3','current_v1']:
            for selector in ['name','batch_id_as_item_key']:
                for intent in ['QUERY_CONSUMPTION','QUERY_FORECAST','SUGGEST_PURCHASE']:
                    owner,ctx,reader=fixture('reference',OracleEngine())
                    if version=='current_v1':
                        data=v1fixture(name='牛奶');data.scope=SCOPE
                        for b in data.items[0].batches: b.household_id=SCOPE.household_id;b.location='冰箱';b.quantity=Decimal(10)
                        reader.data=data
                    else: reader.data.items[0].batches[0].quantity=Decimal(10)
                    query=Query(name='牛奶') if selector=='name' else Query(item_key='b1')
                    result=await owner.query(query,SCOPE,intent)
                    results.append({'fixture':version,'selector':selector,'intent':intent,'result':result.model_dump(mode='json')})
    by={(r['fixture'],r['selector'],r['intent']):r['result'] for r in results}
    assert all(by[(v,'batch_id_as_item_key',i)]['error_code']=='ITEM_NOT_FOUND' for v in ['old_p3','current_v1'] for i in ['QUERY_CONSUMPTION','QUERY_FORECAST','SUGGEST_PURCHASE'])
    consumption=by[('current_v1','name','QUERY_CONSUMPTION')]['consumption_summary'][0]
    assert consumption['observed_days']==28 and Decimal(consumption['effective_quantity'])==7
    forecast=by[('current_v1','name','QUERY_FORECAST')]['forecast'][0]
    assert Decimal(forecast['daily_recorded_consumption'])==Decimal('.25') and Decimal(forecast['remaining_days'])==40
    recommendation=by[('current_v1','name','SUGGEST_PURCHASE')]['recommendations'][0]
    assert recommendation['status']=='needs_review'
    write(ROUND/'evidence/planning-contract-diagnosis.json',{'provenance':'direct_structured_queries_without_model','actual_http_attempts':0,
        'controlled_comparisons':results,'findings':[
            'Passing batch b1 as planning item_key returns ITEM_NOT_FOUND under both old and current fixture contracts.',
            'Current V1 fixture queried by product name computes seven boxes across 28 complete days, daily .25 and 40 days at stock ten.',
            'Current rules require human review for procurement. New sample covered expectation is conditional and requires label review, not automatic PASS.',
            'These are synthetic local direct-call contrasts; do not claim production backend defect or paid LLM success.'
        ]})
    print(json.dumps({'controlled_queries':len(results),'model_http_attempts':0,'formula_checks':'passed','batch_item_mapping':'ITEM_NOT_FOUND','procurement':'needs_review'}))
if __name__=='__main__': asyncio.run(main())
