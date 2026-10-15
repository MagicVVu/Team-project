"""P1 in-process HTTP, rules and scope-filtered read-only test snapshot."""
import copy
from datetime import datetime, timezone

def evaluate(case, config):
    if config['engine'] != 'rules':
        raise NotImplementedError('This P1 adapter is offline/rules only')
    if case['kind'] != 'message':
        raise NotImplementedError('P1 is read-only; legacy P0 writes/scenarios require separate drivers')
    if case['fixture'] != 'seed-v1':
        raise NotImplementedError('unknown fixture')
    from fastapi.testclient import TestClient
    from p0.mock import MockBackend
    from p1.app import create_app
    from p1.engines import RuleEngine
    from p1.schemas import Batch
    from p0.domain import DomainError
    import os
    os.environ['AI_SERVICE_TOKEN'] = 'offline-p1-test'
    os.environ['P1_ENGINE'] = 'rules'
    class Reader:
        def __init__(self):
            self.batches = {k: Batch.model_validate(v.model_dump(mode='json')) for k, v in MockBackend().state['batches'].items()}
            self.reads = []
        def snapshot(self):
            return {k: b.model_dump(mode='json') for k, b in self.batches.items()}
        async def search(self, scope, name):
            self.reads.append({'operation': 'search', 'scope': scope.model_dump(), 'name': name})
            return [b.model_copy(deep=True) for b in self.batches.values() if b.household_id == scope.household_id and (name is None or name.casefold() in b.name.casefold())]
        async def get_batch(self, scope, batch_id):
            self.reads.append({'operation': 'get_batch', 'scope': scope.model_dump(), 'id': batch_id})
            batch = self.batches.get(batch_id)
            if batch is None or batch.household_id != scope.household_id:
                raise DomainError('BATCH_NOT_FOUND', 'Test batch unavailable', 404)
            return batch.model_copy(deep=True)
    reader = Reader()
    before = reader.snapshot()
    now = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
    with TestClient(create_app(engine=RuleEngine(), reader=reader, now=lambda: now)) as client:
        response = client.post('/agent/message', json={'text': case['text'], 'request_id': case['id'], 'household_timezone': 'Asia/Shanghai'}, headers={'Authorization': 'Bearer offline-p1-test', 'X-User-Id': case['scope']['user_id'], 'X-Household-Id': case['scope']['household_id']})
    response.raise_for_status()
    raw = response.json()
    result = copy.deepcopy(raw)
    # Project declared P1 variants to the legacy comparison schema. Keep raw.
    if result['draft'] and result['draft']['action'] in {'ADD', 'PLAN_ADD', 'CONSUME'}:
        for key in ('batch_id', 'expected_version', 'location', 'purchased_at', 'label_expiry'):
            result['draft'].setdefault(key, None)
    for field in ('facts', 'candidates'):
        for batch in result[field]:
            batch.pop('opened_at', None)
    return {'result': result, 'raw_result': raw, 'http': response.status_code, 'before': before, 'after': reader.snapshot(), 'reads': reader.reads, 'fixture_now': now.isoformat(), 'execution': 'P1 in-process HTTP + rules + read-only fixture; no live DB/model', 'mapping': 'P1 omitted legacy nullable command fields -> null; opened_at retained in raw_result; no lifecycle fields discarded from drafts'}
