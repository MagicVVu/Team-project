"""Current physical inventory, authenticated local HTTP and database snapshots."""
import json,sys
from pathlib import Path
from uuid import UUID,uuid4
import httpx,pytest
from sqlalchemy import select,func
from prepare import ROUND
sys.path.insert(0,str(ROUND/'.snapshot/backend/server/tests'))
from test_physical_inventory import state,add,inventory,draft,commit
from autonomous_fixtures import execution_state
from test_autonomous import autonomous_ai,reading,moving
from test_session_memory import start,send,ok,BASE
from test_v09_execution import headers
from app.models import InventoryItem,AITask,AIDraft
from app.execution_models import BusinessEvent,DraftOperation
from app.conversation_models import ConversationTurn
from p0.domain import DomainError

@pytest.fixture(autouse=True)
def synthetic_access(monkeypatch):
 monkeypatch.setenv('MAGICVVU_APP_API_KEY','synthetic-team-key')
 for cls in (httpx.Client,httpx.AsyncClient):
  orig=cls.__init__
  def init(self,*a,_orig=orig,**kw):
   hdr=httpx.Headers(kw.pop('headers',None));hdr.setdefault('X-MagicVVu-App-Key','synthetic-team-key');kw['headers']=hdr;_orig(self,*a,**kw)
  monkeypatch.setattr(cls,'__init__',init)

def snapshot(Session):
 with Session() as db:
  return {'inventory':[{'id':str(b.id),'name':b.name,'location':b.storage_location,'status':b.status,'quantity':str(b.quantity),'version':b.version} for b in db.scalars(select(InventoryItem).order_by(InventoryItem.id))], 'events':db.scalar(select(func.count()).select_from(BusinessEvent)), 'operations':db.scalar(select(func.count()).select_from(DraftOperation)),'tasks':db.scalar(select(func.count()).select_from(AITask)),'drafts':db.scalar(select(func.count()).select_from(AIDraft))}
def evidence(name,value):
 p=ROUND/'runs/backend-special-evidence';p.mkdir(exist_ok=True)
 (p/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def test_ai_draft_and_status_do_not_change_physical_facts(execution_state,autonomous_ai):
 client,Session,ids=execution_state;engine,requests=autonomous_ai;engine.steps=[moving()]
 before=snapshot(Session);value=ok(send(client,ids,ok(start(client,ids)),'把牛奶移到书房'));after=snapshot(Session)
 assert value['task']['status']=='needs_confirmation'
 assert before['inventory']==after['inventory'] and before['events']==after['events'] and before['operations']==after['operations']==0
 assert after['tasks']==before['tasks']+1 and after['drafts']==before['drafts']+1
 follow=ok(send(client,ids,value,'为什么还没有移动'))
 assert follow['model_calls']==0 and snapshot(Session)['inventory']==before['inventory']
 evidence('draft-before-after',{'before':before,'after':after,'task':value['task'],'status_followup':follow,'internal_paths':requests})

def test_four_step_local_chain_persists_and_recovery_does_not_recall_model(execution_state,autonomous_ai):
 client,Session,ids=execution_state;engine,requests=autonomous_ai;engine.steps=[reading(),reading('location'),reading('dates'),{'action':'finish'}]
 from datetime import date
 with Session.begin() as db:
  item=db.get(InventoryItem,ids['batch']);item.opened_at=date(2026,10,1);item.expires_on=date(2026,12,1)
 before=snapshot(Session);request_id='garin-'+uuid4().hex;session=ok(start(client,ids));value=ok(send(client,ids,session,'核对牛奶数量、位置和日期',request_id=request_id))
 replay=ok(send(client,ids,session,'核对牛奶数量、位置和日期',request_id=request_id))
 recovered=ok(client.get(BASE+'conversation-turns/'+request_id,headers=headers(),params={'household_id':str(ids['home'])}))
 assert value==replay and recovered['phase']=='completed' and engine.calls==4
 with Session() as db:
  saved=db.scalar(select(ConversationTurn).where(ConversationTurn.request_id==request_id));assert saved.binding_json['autonomous_v1']['result']['model_calls']==4
 after=snapshot(Session);assert before['inventory']==after['inventory'] and after['operations']==0
 evidence('persist-recovery',{'before':before,'after':after,'response':value,'recovery':recovered,'engine_calls':engine.calls,'paths':requests})

def test_current_intake_and_confirmation_replay_changes_db_once(state):
 client,Session,ids=state
 response,body=add(client,ids,quantity=2);assert response.status_code==201,response.text
 before=snapshot(Session);assert len(before['inventory'])==2
 assert client.post(inventory(ids),headers={'Authorization':'Bearer test-owner'},json=body).json()==response.json()
 assert snapshot(Session)==before
 batch=before['inventory'][0];command={'action':'MOVE','name':batch['name'],'batch_id':batch['id'],'to_location':'书房','expected_version':batch['version']}
 did=draft(Session,ids,command);first,submitted=commit(client,did);second,_=commit(client,did,submitted)
 assert first.status_code==second.status_code==200,(first.text,second.text)
 after=snapshot(Session);assert sum(b['location']=='书房' for b in after['inventory'])==1
 assert after['events']==before['events']+1 and after['operations']==1
 assert first.json()==second.json()
 evidence('commit-idempotency',{'before':before,'after':after,'first':first.json(),'second':second.json()})

def test_foreign_family_is_rejected_without_business_change(state):
 client,Session,ids=state;response,_=add(client,ids);assert response.status_code==201
 before=snapshot(Session);foreign=client.get(inventory(ids),headers={'Authorization':'Bearer test-outsider'})
 assert foreign.status_code in {403,404}
 assert snapshot(Session)==before
 evidence('family-isolation',{'http_status':foreign.status_code,'before':before,'after':snapshot(Session)})

def test_ended_object_cleanup_keeps_committed_event_and_receipt(state):
 client,Session,ids=state;response,_=add(client,ids);assert response.status_code==201
 before=snapshot(Session);item=before['inventory'][0]
 command={'action':'CONSUME','name':item['name'],'batch_id':item['id'],'quantity':'1','unit':'个','expected_version':item['version']}
 did=draft(Session,ids,command);first,body=commit(client,did);assert first.status_code==200,first.text
 repeat,_=commit(client,did,body);assert repeat.json()==first.json()
 after=snapshot(Session);assert after['inventory']==[] and after['operations']==1 and after['events']==before['events']+1
 with Session() as db:
  events=[{'id':str(e.id),'event_type':e.event_type,'inventory_item_id':str(e.inventory_item_id) if e.inventory_item_id else None} for e in db.scalars(select(BusinessEvent))]
 assert any(e['event_type']=='Consumed' for e in events)
 evidence('ended-cleanup-contract',{'before':before,'after':after,'events':events,'receipt':first.json(),'repeat':repeat.json(),'legacy_assertion':'旧测试期待终态库存行仍存在；当前cleanup会删除终态行，历史原FAIL保留。'})

def test_current_planning_serializer_and_ai_adapter_preserve_unknowns(state,monkeypatch):
 import asyncio
 from conversation.planning_schemas import BackendSnapshot
 from conversation.manager import Manager
 from conversation.engines import RuleEngine
 from p2.knowledge import RuleCatalog
 from p3.schemas import Query
 client,Session,ids=state;response,_=add(client,ids,name='牛奶',quantity=2,unit='盒');assert response.status_code==201,response.text
 token='synthetic-version-planning';monkeypatch.setenv('BACKEND_TOOL_TOKEN',token)
 before=snapshot(Session)
 response=client.get('/internal/v1/planning/context',headers={'Authorization':'Bearer '+token,'X-User-Id':str(ids['owner']),'X-Household-Id':str(ids['home'])})
 assert response.status_code==200,response.text
 payload=response.json();value=BackendSnapshot.model_validate({**payload['data'],'provenance':payload['provenance']})
 class ActualSerializedReader:
  async def planning_context(self,scope,**kw):return value.model_copy(deep=True)
 owner=Manager(RuleEngine(),ActualSerializedReader(),RuleCatalog.load(),now=lambda:value.as_of)
 result=asyncio.run(owner.query(Query(name='牛奶'),value.scope,'QUERY_FORECAST'))
 assert result.product_planning and result.product_planning[0].product.total_quantity==2
 assert result.product_planning[0].reference_date is None and result.product_planning[0].remaining_days is None
 assert not result.inventory_writes and not result.shopping_writes
 assert snapshot(Session)==before
 evidence('actual-planning-dto-and-ai-adapter',{'before':before,'after':snapshot(Session),'http_status':response.status_code,'backend_response':payload,'ai_result':result.model_dump(mode='json'),'note':'真实本地序列化，当前逐件记录；新增事件不当消费，无覆盖与可用量证明时不制造耗尽日。'})
