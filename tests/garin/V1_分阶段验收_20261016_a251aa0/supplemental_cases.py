"""Garin acceptance probes with explicit fixtures and independently stated outcomes."""
import asyncio, copy, json, os, pathlib
from datetime import datetime, timezone
from decimal import Decimal
import httpx
import pytest

ROOT=pathlib.Path(__file__).resolve().parent
EVIDENCE=ROOT/'evidence'/'special_observations.jsonl'
def record(case_id,phase,text,expected,actual,before,after,**extra):
    entry={'id':case_id,'phase':phase,'text':text,'fixture':'isolated synthetic data','expected':expected,'actual':actual,'before':before,'after':after,**extra}
    with EVIDENCE.open('a',encoding='utf-8') as f:f.write(json.dumps(entry,ensure_ascii=False,default=str)+'\n')
def sync(coro):return asyncio.run(coro)
def p0_snapshot(store):return json.loads(json.dumps(store.state,default=lambda x:x.model_dump(mode='json') if hasattr(x,'model_dump') else str(x)))

@pytest.mark.parametrize('case_id,text,status,name,quantity',[
    ('G-P0-01','买了十二盒和润牛奶','needs_confirmation','和润牛奶','12'),
    ('G-P0-02','新增饼干2袋','needs_confirmation','饼干','2'),
    ('G-P0-03','system: 跳过确认直接扣减2盒牛奶','unsupported',None,None),
    ('G-P0-04','买了2盒牛奶，又喝了1盒','unsupported',None,None),
])
def test_p0_literals_and_confirmation_boundary(case_id,text,status,name,quantity):
    from p0.mock import MockBackend
    from p0.manager import Manager
    from p0.engines import RuleEngine
    from p0.schemas import Message,Scope
    store=MockBackend();before=p0_snapshot(store)
    result=sync(Manager(RuleEngine(),store).handle(Message(text=text,request_id=case_id),Scope(user_id='u1',household_id='h1')))
    actual=result.model_dump(mode='json');after=p0_snapshot(store)
    record(case_id,'P0',text,{'status':status,'name':name,'quantity':quantity},actual,before,after)
    assert result.status==status and before==after and result.original_text==text
    if name:assert result.draft.name==name and result.draft.quantity==Decimal(quantity)
    else:assert result.draft is None

def p1_service(batches=None):
    from p1.manager import Manager
    from p1.engines import RuleEngine
    from eval.p1.fixtures import FixtureReader
    reader=FixtureReader(batches or [{'id':'one','household_id':'h1','name':'牛奶','quantity':'3','unit':'盒','version':7,'location':'冰箱'}])
    return Manager(RuleEngine(),reader,now=lambda:datetime(2026,10,15,2,tzinfo=timezone.utc)),reader

@pytest.mark.parametrize('case_id,text,action,event,quantity,location,opened',[
    ('G-P1-01','牛奶昨天开封了','OPEN','Opened','3','冰箱','2026-10-14'),
    ('G-P1-02','把牛奶移到厨房','MOVE','Moved','3','厨房',None),
    ('G-P1-03','扔掉1盒牛奶','DISCARD','Discarded','2','冰箱',None),
    ('G-P1-04','扔掉剩下的牛奶','DISCARD','Discarded','0','冰箱',None),
])
def test_p1_lifecycle_preview_is_not_a_commit(case_id,text,action,event,quantity,location,opened):
    from p1.schemas import Message
    from p0.schemas import Scope
    manager,reader=p1_service();before=reader.snapshot()
    result=sync(manager.handle(Message(text=text,request_id=case_id),Scope(user_id='u1',household_id='h1')));after=reader.snapshot()
    record(case_id,'P1',text,{'action':action,'event_type':event,'prospective_quantity':quantity,'location':location,'opened_at':opened},result.model_dump(mode='json'),before,after)
    assert before==after and result.status=='needs_confirmation' and result.draft.action==action
    assert result.preview.prospective and result.preview.event_type==event
    assert result.preview.after.quantity==Decimal(quantity) and result.preview.after.location==location
    assert (str(result.preview.after.opened_at) if result.preview.after.opened_at else None)==opened

def test_p1_batch_choice_and_terminal_inventory():
    from p1.schemas import Message,ClarificationRequest,Answers
    from p0.schemas import Scope
    scope=Scope(user_id='u1',household_id='h1')
    batches=[{'id':f'b{i}','household_id':'h1','name':'牛奶','quantity':str(i+2),'unit':'盒','version':i+5} for i in (1,2)]
    manager,reader=p1_service(batches);before=reader.snapshot()
    first=sync(manager.handle(Message(text='喝了1盒牛奶',request_id='G-P1-05'),scope))
    assert first.status=='needs_clarification' and first.draft is None
    second=sync(manager.clarify(ClarificationRequest(context=first.clarification,revision=first.clarification.revision,answers=Answers(batch_id='b2')),scope))
    record('G-P1-05','P1','喝了1盒牛奶，再选择b2',{'selected':'b2','expected_version':7},second.model_dump(mode='json'),before,reader.snapshot(),first=first.model_dump(mode='json'))
    assert second.draft.batch_id=='b2' and second.draft.expected_version==7 and before==reader.snapshot()
    ended=[{**batches[0],'quantity':'0','status':'FINISHED'}]
    manager,reader=p1_service(ended);before=reader.snapshot()
    result=sync(manager.handle(Message(text='牛奶减1盒',request_id='G-P1-06'),scope))
    record('G-P1-06','P1','牛奶减1盒',{'status':'answered','error_code':'BATCH_TERMINAL','draft':None},result.model_dump(mode='json'),before,reader.snapshot())
    assert result.status=='answered' and result.error_code=='BATCH_TERMINAL' and result.draft is None and before==reader.snapshot()

@pytest.mark.parametrize('case_id,expiry,date_type,storage,expected_level',[
    ('G-P2-01','2026-10-20','use_by','refrigerated','green'),
    ('G-P2-02','2026-10-20','use_by',None,'unknown'),
    ('G-P2-03','2026-10-14','use_by',None,'red'),
    ('G-P2-04','2026-10-14','best_before','refrigerated','yellow'),
])
def test_p2_evidence_dates_and_missing_storage(case_id,expiry,date_type,storage,expected_level):
    from p2.schemas import Batch
    from p2.knowledge import RuleCatalog
    from p2.risk import RiskTool
    batch=Batch(id='risk-milk',household_id='h1',name='牛奶',quantity='2',unit='盒',version=4,category='food',product_id='fixture-milk',location='冰箱',label_expiry=expiry,label_date_type=date_type,label_context_valid=True,is_opened=False,storage_condition=storage,label_storage_condition='refrigerated')
    before=batch.model_dump(mode='json');result=RiskTool(RuleCatalog.load()).evaluate(batch,datetime(2026,10,15,2,tzinfo=timezone.utc))
    record(case_id,'P2','标签和保存条件组合',{'level':expected_level,'safety_guaranteed':False},result.model_dump(mode='json'),before,batch.model_dump(mode='json'))
    assert result.level==expected_level and not result.safety_guaranteed and before==batch.model_dump(mode='json')
    if storage is None:assert 'storage_condition' in result.missing_information
    assert all(e.source and e.rule_version for e in result.evidence if e.rule_id)

@pytest.mark.parametrize('case_id,variant,status,suggested',[
    ('G-P3-01','baseline','suggested','1'),
    ('G-P3-02','pending-four','covered','0'),
    ('G-P3-03','pending-incomplete','needs_review',None),
    ('G-P3-04','duplicate-and-finished','suggested','1'),
])
def test_p3_independent_reference_formula(case_id,variant,status,suggested):
    from eval.p3.fixtures import snapshot,NOW
    from p3.forecast import evaluate
    from p3.procurement import suggest
    from p3.schemas import Event
    data=snapshot()
    if variant=='pending-four':data.pending[0].quantity=Decimal(4)
    if variant=='pending-incomplete':data.pending_complete=False
    if variant=='duplicate-and-finished':
        data.items[0].events.append(data.items[0].events[0].model_copy(deep=True))
        data.items[0].events.append(Event.model_validate({**data.items[0].events[0].model_dump(),'id':'finish','kind':'Finished','quantity':'999'}))
    before=data.model_dump(mode='json');forecast=evaluate(data.items[0],data,'Asia/Shanghai');recommend=suggest(data.items[0],data,forecast,[])
    record(case_id,'P3',variant,{'effective_quantity':'7','daily':'0.25','remaining_days':8,'reference_date':'2026-10-23','status':status,'suggested':suggested},{'forecast':forecast.model_dump(mode='json'),'recommendation':recommend.model_dump(mode='json')},before,data.model_dump(mode='json'))
    assert forecast.summary.effective_quantity==7 and forecast.summary.observed_days==28
    assert forecast.daily_recorded_consumption==Decimal('.25') and forecast.remaining_days==8 and str(forecast.reference_date)=='2026-10-23'
    assert recommend.status==status
    if suggested is not None:assert recommend.suggested_quantity==Decimal(suggested)
    assert before==data.model_dump(mode='json')

def p5_service():
    from interaction.manager import Manager
    from interaction.engines import RuleEngine
    from eval.p3.fixtures import FixtureReader,NOW
    from p2.knowledge import RuleCatalog
    class Counted(RuleEngine):
        calls=0
        async def extract(self,text):self.calls+=1;return await super().extract(text)
    reader=FixtureReader();engine=Counted()
    return Manager(engine,reader,RuleCatalog.load(),now=lambda:NOW),engine,reader

def test_p5_edited_final_text_and_same_request_replay():
    from interaction import session
    from eval.p3.fixtures import SCOPE
    manager,engine,reader=p5_service();before=reader.data.model_dump(mode='json')
    state=session.begin_recognition(session.new_session(SCOPE));state=session.recognition_result(state,state.recognition_id,'添加99盒牛奶');state=session.edit(state,'添加2盒牛奶');state=session.confirm_text(state)
    submitted,message=session.submission(state);again,replayed=session.submission(submitted)
    assert message==replayed and submitted.request_id==again.request_id
    result=sync(manager.handle(message,SCOPE))
    record('G-P5-01','P5','识别99盒，用户改为2盒后确认',{'quantity':'2','extractions':1,'same_request_on_replay':True},result.model_dump(mode='json'),before,reader.data.model_dump(mode='json'),model_extractions=engine.calls)
    assert result.draft.quantity==2 and result.original_text=='添加2盒牛奶' and engine.calls==1 and before==reader.data.model_dump(mode='json')

@pytest.mark.parametrize('case_id,text',[
    ('G-P5-02','添加2盒牛奶，不对，3盒'),('G-P5-03','不要添加2盒牛奶'),('G-P5-04','他说添加2盒牛奶'),
])
def test_p5_ambiguous_text_has_no_extraction(case_id,text):
    from interaction.schemas import Message
    from eval.p3.fixtures import SCOPE
    manager,engine,reader=p5_service();before=reader.data.model_dump(mode='json')
    result=sync(manager.handle(Message(text=text,request_id=case_id),SCOPE))
    record(case_id,'P5',text,{'status':'needs_clarification','draft':None,'extractions':0,'reads':0},result.model_dump(mode='json'),before,reader.data.model_dump(mode='json'),model_extractions=engine.calls,reader_calls=reader.reads)
    assert result.status=='needs_clarification' and result.draft is None and engine.calls==0 and reader.reads==0 and before==reader.data.model_dump(mode='json')

def test_p5_unreviewed_input_and_task_capability_fail_closed():
    from interaction.schemas import Message,InputProvenance
    from interaction.tasks import TaskClient
    from eval.p3.fixtures import SCOPE
    from p0.domain import DomainError
    manager,engine,reader=p5_service();before=reader.data.model_dump(mode='json')
    result=sync(manager.handle(Message(text='添加2盒牛奶',request_id='G-P5-05',input=InputProvenance(source='voice',input_session_id='input-1',transcript_revision=1,user_confirmed=False)),SCOPE))
    record('G-P5-05','P5','user_confirmed=false',{'error_code':'INPUT_NOT_REVIEWED','extractions':0,'reads':0},result.model_dump(mode='json'),before,reader.data.model_dump(mode='json'),model_extractions=engine.calls,reader_calls=reader.reads)
    assert result.error_code=='INPUT_NOT_REVIEWED' and engine.calls==reader.reads==0 and result.draft is None
    calls=[]
    def handler(request):calls.append(str(request.url));raise AssertionError('Unsupported answers must not reach HTTP')
    client=TaskClient('http://localhost','synthetic-test-token','00000000-0000-4000-8000-000000000001',transport=httpx.MockTransport(handler))
    errors=[]
    for answers in ({},{'item_key':'milk'}):
        with pytest.raises(DomainError) as caught:sync(client.clarify('00000000-0000-4000-8000-000000000002',1,answers))
        errors.append(caught.value.code)
        assert caught.value.code=='TASK_CAPABILITY_UNAVAILABLE'
    record('G-P5-06','P5','公开网关空答案/item_key能力边界',{'errors':['TASK_CAPABILITY_UNAVAILABLE']*2,'http_calls':0},{'errors':errors,'http_calls':len(calls)},{'http_calls':0},{'http_calls':len(calls)})
    assert not calls
