"""Offline candidate smoke with SQLite in memory; never use the real DB engine."""
import asyncio
from datetime import datetime,timedelta,timezone
import json
from uuid import uuid4
from unittest.mock import patch
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

isolated=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
with patch('sqlalchemy.create_engine',return_value=isolated):
    from app.main import app
    from app.database import Base
    from app.dependencies import get_db
    from app.models import User,Household,HouseholdMember,AuthSession,AITask,InventoryItem
    from app.security import digest_token
    from app.services import dialogue
    from app.routers.draft_execution import capabilities

assert dialogue.enabled()
caps=capabilities(None)
assert caps['maintenance_release']=='V1-P9' and caps['conversation_dialogue_protocol']=='p84-dialogue-1'
assert caps['automatic_planning_commit'] is False
assert all(caps['actions'].values())
Base.metadata.create_all(isolated)
Session=sessionmaker(bind=isolated,autoflush=False)
user,home=uuid4(),uuid4()
with Session.begin() as db:
    db.add(User(id=user,email='p84-smoke@example.invalid',password_hash='synthetic',display_name='synthetic'))
    db.flush()
    db.add(Household(id=home,name='synthetic',created_by_user_id=user));db.flush()
    db.add(HouseholdMember(household_id=home,user_id=user,role='owner'))
    db.add(AuthSession(user_id=user,token_hash=digest_token('p84-synthetic-login'),expires_at=datetime.now(timezone.utc)+timedelta(minutes=5)))


def dependency():
    with Session() as db:yield db


calls=[]
async def stages(identity,household,stage,payload,seconds):
    assert household==home and identity.user.id==user
    calls.append(stage)
    if stage=='understand':
        return {'protocol_version':'p84-dialogue-1','original_text':payload['text'],'plan':{'speech_act':'social'},'understanding_calls':0}
    assert stage=='resolve'
    return {'protocol_version':'p84-dialogue-1','original_text':payload['text'],'kind':'explain',
        'reply':'合成会话阶段校验','facts':{'f0':'合成会话阶段校验'},'model_calls':0}


async def check():
    app.dependency_overrides[get_db]=dependency
    with patch.object(dialogue,'call',stages):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://offline-backend') as client:
            base='/api/v1/agent/'
            denied=await client.get(base+'conversation',params={'household_id':str(home)})
            assert denied.status_code==401
            headers={'Authorization':'Bearer p84-synthetic-login'}
            started=await client.post(base+'conversation/reset',headers=headers,json={'household_id':str(home),'request_id':'smoke-reset'})
            assert started.status_code==200,started.text
            session=started.json()
            body={'household_id':str(home),'request_id':'smoke-message','text':'你好',
                'conversation_id':session['conversation_id'],'conversation_revision':session['conversation_revision']}
            first=await client.post(base+'conversation-turns',headers=headers,json=body)
            assert first.status_code==200,first.text
            first=first.json();assert first['dialogue']['protocol_version']=='p84-dialogue-1' and first['model_calls']==0
            repeated=await client.post(base+'conversation-turns',headers=headers,json=body)
            assert repeated.status_code==200 and repeated.json()==first
            recovered=await client.get(base+'conversation-turns/smoke-message',headers=headers,params={'household_id':str(home)})
            assert recovered.status_code==200 and recovered.json()['phase']=='completed'
            assert calls==['understand','resolve']
    with Session() as db:
        assert db.query(AITask).count()==0 and db.query(InventoryItem).count()==0
    app.dependency_overrides.clear()
    return {'backend_base_release':'V1-P9','dialogue_protocol':'p84-dialogue-1','real_database_accessed':False,
        'authentication_verified':True,'stage_persistence_verified':True,'idempotent_recovery_verified':True,
        'inventory_mutations':0,'model_calls':0,'automatic_planning_commit':False}


print(json.dumps(asyncio.run(check())))
