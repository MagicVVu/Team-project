"""Integration checks for new adapters, including observed isolation evidence."""
import copy
import json
import pathlib
import pytest
from adapters import local_p1, android_gateway, local_p0

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASES = {r['id']:r for r in map(json.loads,(ROOT/'cases'/'extended.jsonl').read_text(encoding='utf-8').splitlines())}

@pytest.mark.parametrize('adapter',[local_p1,android_gateway])
def test_output_is_independent_of_expected_and_fixture_is_fresh(adapter):
    case=copy.deepcopy(CASES['ext-001'])
    case['expected']={'intent':'fabricated','draft':{'name':'fabricated'}}
    observation=adapter.evaluate(case,{'engine':'rules'})
    assert observation['result']['draft']['name']=='牛奶'
    assert observation['before']==observation['after']
    # A mutated returned evidence object cannot affect the next case.
    observation['before'].clear()
    fresh=adapter.evaluate(CASES['ext-001'],{'engine':'rules'})
    assert len(fresh['before']) in (5,6)
    assert fresh['before']==fresh['after']

def test_p1_projects_contract_fields_but_preserves_raw_http():
    result=local_p1.evaluate(CASES['ext-001'],{'engine':'rules'})
    assert 'batch_id' not in result['raw_result']['draft']
    assert result['result']['draft']['batch_id'] is None
    assert result['http']==200 and result['raw_result']['trace_id']

def test_android_observes_server_reader_and_keeps_raw_device_scope():
    result=android_gateway.evaluate(CASES['ext-067'],{'engine':'rules'})
    assert result['result']['status']=='needs_clarification'
    assert {b['household_id'] for b in result['raw_response']['data']['candidates']}=={'device-snapshot'}
    assert {b['household_id'] for b in result['result']['candidates']}=={'h1'}
    assert 'private-1' not in result['before']

@pytest.mark.parametrize('adapter',[local_p1,android_gateway])
def test_legacy_confirm_flow_is_blocked_not_passed(adapter):
    with pytest.raises(NotImplementedError):
        adapter.evaluate({'kind':'flow'}, {'engine':'rules'})

def test_p0_confirm_flow_saves_actual_request_and_both_states():
    case=next(r for r in map(json.loads,(ROOT/'cases'/'flows.jsonl').read_text(encoding='utf-8').splitlines()) if r['id']=='flow-002')
    result=local_p0.evaluate(case,{'engine':'rules'})
    assert not result['failures']
    assert result['steps'][-1]['before']['batches']!=result['steps'][-1]['after']['batches']
    assert result['steps'][-1]['request']['method']=='POST'
