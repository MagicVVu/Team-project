"""Checks the delivered P1 service's actual HTTP schema used by gateway.

Read-only test only, no external HTTP or database. Imports the shipped source.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

AGENT_ROOT = Path(__file__).resolve().parents[2] / 'agent'
if not AGENT_ROOT.exists():
    # Repository keeps this deployable server under backend/server/.
    AGENT_ROOT = Path(__file__).resolve().parents[3] / 'agent'
sys.path.insert(0, str(AGENT_ROOT))
from p1.app import create_app
from p1.engines import RuleEngine
from p1.schemas import Batch


class FakeReader:
    async def search(self, scope, name):
        return [Batch(id=str(uuid4()), household_id=scope.household_id, name='牛奶',
                      quantity='2.000001', unit='盒', location='冰箱', version=2)]
    async def get_batch(self, scope, batch_id):
        raise AssertionError('unexpected')


def test_real_p1_message_contract_is_read_only():
    with patch.dict(os.environ, {'AI_SERVICE_TOKEN': 'test-verified-internal-token', 'P1_ENGINE': 'rules'}):
        app = create_app(engine=RuleEngine(), reader=FakeReader())
        with TestClient(app) as client:
            assert client.get('/health').json()['inventory_writes'] is False
            scope = {'Authorization': 'Bearer test-verified-internal-token',
                     'X-User-Id': str(uuid4()), 'X-Household-Id': str(uuid4())}
            text = '库存有什么'
            r = client.post('/agent/message', json={'text': text, 'request_id': 'unit-real-p1',
                            'household_timezone': 'Asia/Shanghai'}, headers=scope)
            assert r.status_code == 200, r.text
            result = r.json()
            assert result['status'] == 'answered' and result['original_text'] == text
            assert result['facts'][0]['quantity'] == '2.000001'
            assert result['draft'] is None
            assert client.post('/agent/message', json={'text': text, 'request_id': 'unit-real-p1',
                               'household_timezone': 'Asia/Shanghai'}).status_code == 401
