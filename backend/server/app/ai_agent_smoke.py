"""Strictly read-only v0.6 live network smoke: verify P1 rules and two-way auth.

The UUIDs used here intentionally do not exist. No test users, households,
inventory, task, or draft are written to PostgreSQL. Does NOT call DeepSeek.
"""
import asyncio
import os
from uuid import uuid4

import httpx


async def run() -> None:
    if os.getenv('P1_ENGINE') not in (None, 'rules'):
        print('WARNING: ensure the AI service is running in rules mode before testing')
    internal = os.getenv('AI_SERVICE_URL', '').rstrip('/')
    auth = os.getenv('AI_SERVICE_TOKEN', '')
    if internal != 'http://agent:8767' or len(auth) < 32:
        raise RuntimeError('AI_SERVICE_URL / AI_SERVICE_TOKEN not safely configured')
    async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
        r = await client.get(internal + '/health')
        r.raise_for_status()
        data = r.json()
        if data.get('release_version') != 'V1-P1' or data.get('engine') != 'rules' or data.get('inventory_writes') is not False:
            raise RuntimeError('Unexpected AI service mode: safe rules mode required')
        print('P1 HEALTH PASSED: rules, no inventory writes')
        # Fake scope deliberately cannot pass real v0.5 membership verification.
        # AI should call the real inventory tool, receive a denial, and not invent facts.
        uid, hid = str(uuid4()), str(uuid4())
        r = await client.post(internal + '/agent/message', json={
            'text': '库存有什么', 'request_id': 'smoke-' + uuid4().hex,
            'household_timezone': 'Asia/Shanghai',
        }, headers={'Authorization': 'Bearer ' + auth,
                    'X-User-Id': uid, 'X-Household-Id': hid})
        r.raise_for_status()
        result = r.json()
        if result.get('status') != 'error' or result.get('draft') or result.get('facts'):
            raise RuntimeError('AI returned inventory facts for a nonmember; fail closed')
        print('P1 -> BACKEND READ AUTH PASSED: nonexistent scope cannot read inventory')
        print('READ-ONLY AI CONNECTIVITY SMOKE PASSED; NO DATABASE TEST DATA CREATED')


if __name__ == '__main__':
    asyncio.run(run())
