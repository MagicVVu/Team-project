"""Authenticated bilingual conversations over the actual AI and task adapter."""
from uuid import uuid4
import pytest
from test_autonomous import autonomous_ai
from sqlalchemy import select
from app.models import InventoryItem,AIDraft
from app.conversation_models import ConversationTurn
from app.assistant_language import request_dump
from app.memory_schemas import Message
from app.services import conversation as routing
from autonomous_fixtures import execution_state,multiple
from test_session_memory import BASE,ok
from test_v09_execution import headers,body as commit_body,post


def start_en(client,ids):
    return ok(client.post(BASE+'conversation/reset',headers={**headers(),'Accept-Language':'en'},json={
        'household_id':str(ids['home']),'request_id':uuid4().hex,'locale':'en'}))


def send_en(client,ids,session,text,request_id=None,locale='en'):
    return client.post(BASE+'conversation-turns',headers={**headers(),'Accept-Language':locale},json={
        'household_id':str(ids['home']),'conversation_id':session['conversation_id'],
        'conversation_revision':session.get('current_conversation_revision',session['conversation_revision']),
        'request_id':request_id or uuid4().hex,'locale':locale,'text':text})


def plan(speech='question',action=None,**extra):
    return {'action':'resolve','plan':{'speech_act':speech,'action':action,**extra},'finish_after_resolve':True}


def test_original_digest_is_unchanged_without_locale():
    legacy={'household_id':str(uuid4()),'request_id':'original','conversation_id':str(uuid4()),'conversation_revision':0,'text':'hello'}
    parsed=Message.model_validate(legacy)
    original={**legacy,'task_id':None,'revision':None}
    assert request_dump(parsed)==original
    assert routing.digest({'memory_message':request_dump(parsed)})==routing.digest({'memory_message':original})
    assert request_dump(Message.model_validate({**legacy,'locale':'en'}))['locale']=='en'


def test_english_query_canonical_stock_and_idempotent_recovery(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,requests=autonomous_ai
    engine.steps=[plan(selector={'name':'milk'},reads=[{'kind':'location'}])]
    session=start_en(client,ids);request_id=uuid4().hex
    first=ok(send_en(client,ids,session,'Where is milk?',request_id))
    assert first['locale']=='en' and 'location' in first['reply'] and '冰箱' in first['reply']
    assert first['task']['result']['facts'][0]['name']=='牛奶' and engine.calls==1
    replay=ok(send_en(client,ids,session,'Where is milk?',request_id))
    assert replay==first and engine.calls==1
    recovered=ok(client.get(BASE+'conversation-turns/'+request_id,headers={**headers(),'Accept-Language':'zh-CN'},params={'household_id':str(ids['home'])}))
    assert recovered['response']['locale']=='en' and recovered['response']['reply']==first['reply']
    with Session() as db:assert db.query(AIDraft).count()==0


def test_english_candidates_move_confirm_and_execution_explanation(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    multiple(Session,ids)
    engine.steps=[plan(selector={'name':'milk'},reads=[{'kind':'location'}]),
        plan('request','MOVE',write_count=1,selector={'use_reference':True},fields={'to_location':{'value':'study','quote':'study'}})]
    first=ok(send_en(client,ids,start_en(client,ids),'Where is milk?'))
    assert first['task']['status']=='needs_clarification'
    selected_id=first['task']['result']['candidates'][1]['id']
    second=ok(send_en(client,ids,first,'the second one'))
    assert second['model_calls']==0 and second['task']['result']['facts'][0]['id']==selected_id
    moved=ok(send_en(client,ids,second,'Move it to the study'))
    assert moved['task']['status']=='needs_confirmation' and moved['task']['result']['draft']['batch_id']==selected_id
    assert 'Nothing has been written' in moved['reply']
    committed=ok(post(client,moved['task']['draft_id'],commit_body(task_revision=moved['task']['revision'])))
    assert committed['status']=='committed'
    status=ok(send_en(client,ids,moved,'Has it been executed?'))
    assert status['model_calls']==0 and 'verified business receipt' in status['reply']


def test_untrusted_translation_is_not_saved_as_a_draft(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[plan('request','MOVE',write_count=1,selector={'name':'dairy drink','search_terms':['牛奶']},fields={'to_location':{'value':'study','quote':'study'}})]
    result=ok(send_en(client,ids,start_en(client,ids),'Move the dairy drink to the study'))
    assert result['task']['status']=='needs_clarification' and result['task']['result']['draft'] is None
    with Session() as db:assert db.query(AIDraft).count()==0


def test_language_switch_keeps_task_and_original_request(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[plan('request','MOVE',write_count=1,selector={'name':'milk'},fields={'to_location':{'value':'study','quote':'study'}})]
    first=ok(send_en(client,ids,start_en(client,ids),'Move milk to the study'))
    second=ok(send_en(client,ids,first,'执行了吗',locale='zh-CN'))
    assert second['locale']=='zh-CN' and '待确认' in second['reply']
    assert second['active_task']['task']['task_id']==first['task']['task_id'] and second['model_calls']==0
    with Session() as db:assert db.query(AIDraft).count()==1


def test_invalid_language_and_unknown_errors_do_not_leak_internals(execution_state):
    client,Session,ids=execution_state;session=start_en(client,ids)
    response=send_en(client,ids,session,'hello',locale='fr')
    assert response.status_code==422
    english=client.get(BASE+'conversation',headers={**headers(),'Accept-Language':'en'},params={'household_id':str(uuid4())})
    assert english.status_code in (403,404) and 'message' in english.json()['detail']


def test_local_backend_contract_matches_current_factory(execution_state):
    import json
    from pathlib import Path
    from app.main import app
    path=Path(__file__).resolve().parents[3]/'docs/versions/V1-P8.7/contracts/backend-openapi.json'
    exported=json.loads(path.read_text(encoding='utf-8'))
    for key in ('x-deployment-status','x-conversation-memory-protocol','x-conversation-dialogue-protocol'):exported.pop(key)
    assert exported==app.openapi()


def test_confirmed_model_alias_continues_without_repeating_model(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[plan('request','MOVE',write_count=1,selector={'name':'dairy drink','search_terms':['牛奶']},fields={'to_location':{'value':'study','quote':'study'}})]
    first=ok(send_en(client,ids,start_en(client,ids),'Move the dairy drink to the study'))
    second=ok(send_en(client,ids,first,'yes that one'))
    assert second['model_calls']==0 and engine.calls==1
    assert second['task']['result']['draft']['batch_id']==str(ids['batch'])
    assert second['task']['result']['draft']['name']=='牛奶'


def test_dictionary_miss_hint_remains_untrusted(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    with Session.begin() as db:db.get(InventoryItem,ids['batch']).name='鲜乳'
    engine.steps=[plan(selector={'name':'milk','search_terms':['鲜乳']},reads=[{'kind':'location'}])]
    value=ok(send_en(client,ids,start_en(client,ids),'Where is milk?'))
    assert value['task']['status']=='needs_clarification' and value['task']['result']['candidates'][0]['name']=='鲜乳'
    with Session() as db:assert db.query(AIDraft).count()==0
