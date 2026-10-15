"""Android gateway HTTP contract; actual request-local reader is observed."""
import copy
from unittest.mock import patch

def evaluate(case, config):
    if config['engine'] != 'rules':
        raise NotImplementedError('Android adapter is offline/rules only')
    if case['kind'] != 'message':
        raise NotImplementedError('Android gateway has no legacy P0 confirm/undo routes; device driver required')
    if case['fixture'] != 'seed-v1' or case['scope']['household_id'] != 'h1':
        raise NotImplementedError('Gateway is single-device, not a household-auth acceptance target')
    from fastapi.testclient import TestClient
    from p0.mock import MockBackend
    from backend import app as gateway
    items = [{'id': b.id, 'name': b.name, 'quantity': str(b.quantity), 'unit': b.unit, 'location': b.location, 'expiry': b.label_expiry} for b in MockBackend().state['batches'].values() if b.household_id == 'h1']
    request = {'inventory_revision': 0, 'items': items, 'text': case['text'], 'request_id': case['id']}
    observed = []
    original = gateway.SnapshotReader
    def snapshot(reader):
        return {b.id: b.model_dump(mode='json') for b in reader.batches}
    class RecordingReader(original):
        def __init__(self, body):
            super().__init__(body)
            self.before = snapshot(self)
            observed.append(self)
    with patch.object(gateway, 'SnapshotReader', RecordingReader):
        with TestClient(gateway.create_app()) as client:
            response = client.post('/api/v1/agent/messages', json=request, headers={'Authorization': 'Bearer local-development'})
    response.raise_for_status()
    raw = response.json()
    if len(observed) != 1:
        raise RuntimeError('Cannot independently observe gateway snapshot reader')
    result = copy.deepcopy(raw['data'])
    for field in ('facts', 'candidates'):
        for batch in result[field]:
            if batch['household_id'] != 'device-snapshot':
                raise RuntimeError('Unexpected gateway scope')
            batch['household_id'] = 'h1'
    return {'result': result, 'raw_response': raw, 'request': request, 'http': response.status_code, 'before': observed[0].before, 'after': snapshot(observed[0]), 'execution': 'Android gateway in-process HTTP + rules + observed request-local SnapshotReader; no phone storage tested', 'mapping': 'device-snapshot -> h1 solely for seed comparison; does not test multi-household isolation; revision=0 gives batch version=1'}
