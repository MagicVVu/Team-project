"""Independent arithmetic, contract and adapter checks; no real model."""
import asyncio,json,sys
from decimal import Decimal
from datetime import timedelta
import pytest
from prepare import ROUND
sys.path[:0]=[str(ROUND/'scripts'),str(ROUND/'.snapshot/agent/tests')]
import live
from p3.forecast import evaluate
from p3.history import consumption
from p3.procurement import suggest
from eval.p3.fixtures import snapshot,NOW
from p3.schemas import Event
from conversation.autonomous.schemas import RunRequest
from interaction.schemas import Message,InputProvenance
from test_interaction import service as input_service,send as input_send
from p0.engines import RuleEngine

@pytest.mark.parametrize('profile',['reference','empty','multiple','multiple_no_ref','risk_missing','risk_expired','planning','planning_unknown','planning_adjusted','archive','history_stale','move_pending','unknown','location_multiple'])
def test_current_fixture_shapes(profile):
 owner,ctx,reader,clock,archive=live.state(profile,live.Oracle())
 body=RunRequest(text='核对牛奶',request_id='adapter-shape',context=ctx)
 assert body.context.scope==live.SCOPE
 assert all(b.quantity==1 for i in reader.data.items for b in i.batches)
 assert owner.inventory_model=='single-object-1'

def test_scoring_rejects_wrong_quantity_and_target():
 result={'inventory_writes':False,'shopping_writes':False,'status':'needs_confirmation','resolved':{'result':{'draft':{'action':'MOVE','batch_id':'wrong','quantity':'99'}}}}
 score=live.score({'draft':{'batch_id':'b1','quantity':'1'}},result,True,None)
 assert score['draft.batch_id'] is False and score['draft.quantity'] is False

def test_foreign_reference_is_rejected_before_any_model_or_read():
 owner,ctx,reader,clock,archive=live.state('foreign',live.Oracle())
 with pytest.raises(Exception,match='Cross-scope reference'):RunRequest(text='它在哪里',request_id='foreign-shape',context=ctx)
 assert reader.reads==0

def test_archive_fixture_has_valid_original_reference_lifetime():
 from archive_recheck import corrected_state
 owner,ctx,reader,clock,archive=corrected_state('archive',live.Oracle())
 live.P85Archive(scope=live.SCOPE,conversation_id=ctx.conversation_id,revision=ctx.revision,episodes=archive)
 assert ctx.reference.expires_at-ctx.reference.issued_at==timedelta(minutes=15)
 assert all(not e.reference or e.reference.issued_at<=e.created_at for e in archive)

def test_fixed_reference_arithmetic_and_pending_deduction():
 data=snapshot();r=evaluate(data.items[0],data,'Asia/Shanghai')
 assert r.summary.observed_days==28 and r.summary.effective_quantity==7
 assert r.daily_recorded_consumption==Decimal('.25') and r.remaining_days==8
 assert str(r.reference_date)=='2026-10-23'
 suggestion=suggest(data.items[0],data,r,[])
 assert suggestion.suggested_quantity==1

@pytest.mark.parametrize('kind',['Discarded','Adjusted','Moved','Opened','Added','Finished','Purchased'])
def test_nonconsumption_events_do_not_change_fixed_arithmetic(kind):
 data=snapshot();event=data.items[0].events[0].model_copy(update={'id':'not-consumption','kind':kind,'quantity':Decimal('999')})
 data.items[0].events.append(event)
 assert evaluate(data.items[0],data,'Asia/Shanghai').summary.effective_quantity==7

def test_duplicate_event_does_not_change_arithmetic():
 data=snapshot();data.items[0].events.append(data.items[0].events[0].model_copy(deep=True))
 assert evaluate(data.items[0],data,'Asia/Shanghai').summary.effective_quantity==7

def test_missing_complete_history_never_makes_date():
 data=snapshot();data.history_complete=False
 assert evaluate(data.items[0],data,'Asia/Shanghai').reference_date is None

def test_final_edited_input_and_unconfirmed_gate():
 manager,engine,reader=input_service();provenance=InputProvenance(source='voice',input_session_id='garin-new-review',transcript_revision=2,user_confirmed=False,user_edited=True)
 unconfirmed=input_send(manager,'添加2盒牛奶',input=provenance)
 assert unconfirmed.error_code=='INPUT_NOT_REVIEWED' and engine.calls==0 and reader.reads==0
 confirmed=input_send(manager,'添加2盒牛奶',input=provenance.model_copy(update={'user_confirmed':True}))
 assert confirmed.draft.quantity==2 and confirmed.original_text=='添加2盒牛奶' and engine.calls==1

def test_frozen_data_counts_and_no_missing_expectations():
 single=live.readrows('single');multi=live.readrows('multi')
 assert len(single)==128 and len(multi)==32 and sum(len(x['turns']) for x in multi)==128
 assert all(r['expected'] for r in single)
 live.verify()
