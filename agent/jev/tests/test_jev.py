import asyncio
import copy
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from jev import Engine
from jev.budget import Budget, RESERVATION
from jev.config import Config, MODEL, MAX_INPUT_TOKENS, BUDGET_NANODOLLARS
from jev.datasets.generate import build_samples
from jev.evaluation import Sample, load_dataset, evaluate, summarize, write_reports
from jev.providers import LiveProvider, MockProvider, ReplayProvider
from jev.schemas import (DecisionRequest, NodeState, Node, Action, CallTrace,
                         Answer, JevError)

ROOT = Path(__file__).resolve().parents[2]


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture
def request_data():
    return copy.deepcopy(build_samples()[3]["request"])


def evaluate_request(raw, overrides=None):
    return run(Engine(MockProvider(overrides=overrides)).evaluate(raw))


def trace():
    return CallTrace(phase=1, source="mock", fingerprint="unused")


async def fake_http_response(request):
    payload = json.loads(request.content)
    response = await MockProvider().ask(payload, trace())
    return httpx.Response(200, json=response.model_dump(mode="json"))


def live_provider(tmp_path, handler=fake_http_response):
    return LiveProvider(Config(api_key="synthetic-test-key"), budget=Budget(tmp_path / "budget.sqlite"),
                        transport=httpx.MockTransport(handler), recordings=tmp_path / "recordings")


def test_import_and_construction_have_no_side_effects(tmp_path):
    script = """
import os,sqlite3,socket,asyncio,httpx,pydantic
from pathlib import Path
def forbidden(*a,**kw): raise AssertionError('unexpected side effect')
original_getenv=os.getenv
def getenv(key,*a,**kw):
    if key.startswith(('TYPESAFE_', 'DEEPSEEK_', 'BACKEND_', 'AI_SERVICE_')): forbidden()
    return original_getenv(key,*a,**kw)
os.getenv=getenv
sqlite3.connect=forbidden
socket.socket=forbidden
Path.mkdir=forbidden
Path.write_text=forbidden
import jev
from jev.config import Config
from jev.providers import LiveProvider,ReplayProvider
jev.Engine()
LiveProvider(Config())
ReplayProvider()
print('clean')
"""
    completed = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "clean"


def test_two_rounds_provenance_and_input_immutability(request_data):
    before = copy.deepcopy(request_data)
    result = evaluate_request(request_data)
    assert result.status == "ok" and result.final_action == Action.CONFIRM
    assert len(result.calls) == 2 and all(c.source == "mock" for c in result.calls)
    assert all(n.status == "ok" and n.source == "mock" and n.model is None for n in result.nodes.values())
    assert result.charged_usd == 0 and not result.inventory_writes and not result.shopping_writes
    assert request_data == before


@pytest.mark.parametrize("field,value,reason", [
    ("scope_valid", False, "SCOPE_UNVERIFIED"), ("known", False, "FACTS_UNKNOWN"),
    ("task_status", "processing", "TASK_NOT_READY"), ("capabilities", [], "CAPABILITY_UNAVAILABLE"),
])
def test_unavailable_facts_override_confident_model(request_data, field, value, reason):
    request_data["facts"][field] = value
    result = evaluate_request(request_data, {Node.CLARIFICATION.value: "PASS", Node.ACTION.value: "READ"})
    assert result.final_action == Action.WAIT and reason in result.reasons


@pytest.mark.parametrize("change,reason", [
    ({"missing_fields": ["quantity"]}, "MISSING_FIELDS"),
    ({"conflicts": ["unit"]}, "FACT_CONFLICT"),
])
def test_hard_clarification_cannot_be_cleared(request_data, change, reason):
    request_data["facts"].update(change)
    result = evaluate_request(request_data, {Node.CLARIFICATION.value: "PASS", Node.ACTION.value: "CONFIRM"})
    assert result.final_action == Action.CLARIFY and reason in result.reasons


def consumption_request():
    return copy.deepcopy(next(s for s in build_samples() if s["category"] == "consume")["request"])


@pytest.mark.parametrize("case,reason,expected", [
    ("multiple", "TARGET_NOT_UNIQUE", Action.CLARIFY),
    ("version", "VERSION_UNVERIFIED", Action.WAIT),
    ("unit", "UNIT_UNVERIFIED", Action.CLARIFY),
    ("reference", "REFERENCE_INVALID", Action.WAIT),
    ("excess", "QUANTITY_EXCEEDS_STOCK_OR_UNIT_MISSING", Action.CLARIFY),
    ("terminal", "BATCH_TERMINAL", Action.WAIT),
])
def test_batch_constraints(case, reason, expected):
    request = consumption_request()
    facts = request["facts"]
    if case == "multiple":
        facts["selected_id"] = None
        facts["candidates"].append({**facts["candidates"][0], "id": "other"})
    if case == "version": facts["version_current"] = False
    if case == "unit": facts["unit_compatible"] = False
    if case == "reference": facts.update(has_reference=True, reference_valid=False)
    if case == "excess": facts["fields"]["quantity"] = "5"
    if case == "terminal": facts["candidates"][0]["status"] = "FINISHED"
    result = evaluate_request(request, {Node.CLARIFICATION.value: "PASS", Node.ACTION.value: "CONFIRM"})
    assert result.final_action == expected and reason in result.reasons


@pytest.mark.parametrize("text", ["牛奶是不是喝完了", "不要把牛奶喝完", "假如牛奶喝完了", "牛奶没喝完", "明天牛奶喝完了"])
def test_false_confident_affirmative_does_not_make_query_a_change(text):
    request = consumption_request()
    request["text"] = text
    result = evaluate_request(request, {Node.INTENT.value: "CONSUME", Node.EVENT.value: "FINISHED",
        "speech_act": "FACT", Node.CLARIFICATION.value: "PASS", Node.ACTION.value: "CONFIRM"})
    assert result.final_action == Action.CLARIFY and "NON_AFFIRMATIVE_TEXT" in result.reasons


def test_inconsistent_intent_event_and_read_cannot_bypass_confirmation(request_data):
    result = evaluate_request(request_data, {Node.EVENT.value: "DISCARDED", Node.ACTION.value: "READ"})
    assert result.final_action == Action.CLARIFY and "INTENT_EVENT_CONFLICT" in result.reasons
    result = evaluate_request(request_data, {Node.ACTION.value: "READ"})
    assert result.final_action == Action.CONFIRM and "ACTION_POLICY_OVERRIDE" in result.reasons


def test_missing_facts_are_not_assumed_complete(request_data):
    request_data.pop("facts")
    result = evaluate_request(request_data)
    assert result.final_action == Action.WAIT and "FACTS_UNKNOWN" in result.reasons


def test_single_nodes_require_explicit_upstream(request_data):
    engine = Engine()
    result = run(engine.evaluate_node(Node.INTENT, DecisionRequest.model_validate(request_data)))
    assert len(result.calls) == 1 and result.nodes[Node.INTENT].status == "ok"
    assert result.nodes[Node.EVENT].status == "skipped" and result.final_action == Action.WAIT
    result = run(engine.evaluate_node(Node.ACTION, NodeState(request=request_data)))
    assert result.reasons == ["UPSTREAM_REQUIRED"] and result.calls == []
    full = run(engine.evaluate(request_data))
    upstream = {n.value: full.nodes[n].answer for n in (Node.INTENT, Node.EVENT)} | full.auxiliary
    result = run(engine.evaluate_node(Node.ACTION, NodeState(request=request_data, upstream=upstream)))
    assert result.nodes[Node.ACTION].status == "ok" and len(result.calls) == 1
    assert result.final_action == Action.WAIT  # single-node advice is not full policy


def test_first_round_failure_skips_dependents(request_data):
    class Broken:
        source = "mock"
        async def ask(self, payload, record): raise JevError("SYNTHETIC_FAILURE")
    result = run(Engine(Broken()).evaluate(request_data))
    assert len(result.calls) == 1 and result.status == "unavailable"
    assert result.nodes[Node.INTENT].status == "error"
    assert result.nodes[Node.CLARIFICATION].status == result.nodes[Node.ACTION].status == "skipped"


def test_total_timeout_is_traced(request_data):
    class Slow:
        source = "mock"
        async def ask(self, payload, record): await asyncio.sleep(1)
    result = run(Engine(Slow(), total_timeout=.01).evaluate(request_data))
    assert result.status == "unavailable" and result.reasons == ["TOTAL_TIMEOUT"]
    assert result.calls[0].error_code == "TOTAL_TIMEOUT"


@pytest.mark.parametrize("changes", [
    {"confidence": float("nan")}, {"confidence": 1.1},
    {"probabilities": {"a": .6, "b": .6}}, {"choice": "c"},
    {"probabilities": {"a": .1, "b": .9}}, {"confidence": "0.9"},
])
def test_invalid_probabilities_are_rejected(changes):
    value = {"type": "choice", "choice": "a", "confidence": 1., "probabilities": {"a": 1., "b": 0.}}
    with pytest.raises(ValidationError): Answer.model_validate(value | changes)


def test_noul_has_no_confidence():
    with pytest.raises(ValidationError):
        Answer(type="noul", noul=.5, confidence=.9)


@pytest.mark.parametrize("kind,code", [
    ("429", "MODEL_RATE_LIMITED"), ("401", "MODEL_HTTP_401"), ("302", "MODEL_HTTP_302"),
    ("invalid_json", "INVALID_MODEL_RESPONSE"), ("missing_answer", "ANSWER_SET_MISMATCH"),
    ("wrong_model", "MODEL_VERSION_MISMATCH"), ("wrong_options", "ANSWER_OPTIONS_MISMATCH"),
    ("timeout", "MODEL_TIMEOUT"), ("connection", "MODEL_UNAVAILABLE"),
])
def test_live_errors_no_retry_and_conservative_billing(tmp_path, request_data, kind, code):
    attempts = []
    async def handler(request):
        attempts.append(request)
        if kind.isdigit(): return httpx.Response(int(kind), text="secret-body-must-not-leak")
        if kind == "invalid_json": return httpx.Response(200, text="invalid-secret-body")
        if kind == "timeout": raise httpx.ReadTimeout("secret", request=request)
        if kind == "connection": raise httpx.ConnectError("secret", request=request)
        response = await fake_http_response(request)
        data = response.json()
        if kind == "missing_answer": data["answers"].pop("event_classifier")
        if kind == "wrong_model": data["model"] = "jev-latest"
        if kind == "wrong_options":
            answer = data["answers"]["intent_router"]
            answer["probabilities"]["INVENTED"] = 0.
        return httpx.Response(200, json=data)
    provider = live_provider(tmp_path, handler)
    result = run(Engine(provider).evaluate(request_data))
    assert result.status == "unavailable" and result.reasons == [code]
    assert len(attempts) == 1
    assert provider.budget.summary()["unknown_usage_calls"] == 1
    assert result.calls[0].charged_usd > 0 and not result.calls[0].usage_measured
    assert "secret" not in result.model_dump_json()


def test_live_recording_replay_and_real_cost_separation(tmp_path, request_data):
    attempts = []
    async def handler(request):
        attempts.append(json.loads(request.content))
        response = await fake_http_response(request)
        data = response.json()
        data["usage"] = {"input_tokens": 100, "output_tokens": 3}
        return httpx.Response(200, json=data)
    provider = live_provider(tmp_path, handler)
    first = run(Engine(provider).evaluate(request_data))
    assert first.status == "ok" and len(attempts) == 2
    assert first.charged_usd == Decimal("0.0000084")
    assert provider.budget.summary()["unknown_usage_calls"] == 0
    for path in (tmp_path / "recordings").glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert request_data["text"] not in text and "synthetic-test-key" not in text
    replay = run(Engine(ReplayProvider(tmp_path / "recordings")).evaluate(request_data))
    assert replay.final_action == first.final_action and replay.charged_usd == 0
    assert all(c.source == "replay" and not c.attempted and not c.usage_measured for c in replay.calls)
    request_data["text"] += "修改输入"
    missing = run(Engine(ReplayProvider(tmp_path / "recordings")).evaluate(request_data))
    assert missing.reasons == ["REPLAY_MISS"]


def test_missing_key_does_not_create_budget(tmp_path, request_data):
    provider = LiveProvider(Config(), budget=Budget(tmp_path / "absent.sqlite"))
    result = run(Engine(provider).evaluate(request_data))
    assert result.reasons == ["MODEL_NOT_CONFIGURED"] and not provider.budget.path.exists()


def test_budget_read_does_not_create_files(tmp_path):
    budget = Budget(tmp_path / "no" / "budget.sqlite")
    assert budget.summary()["calls"] == 0 and not budget.path.parent.exists()


def test_budget_restart_idempotent_settlement_and_unknown_usage(tmp_path):
    path = tmp_path / "budget.sqlite"
    budget = Budget(path)
    call, reserved = budget.reserve()
    assert reserved == Decimal(RESERVATION) / Decimal(1_000_000_000)
    assert Budget(path).summary()["unknown_usage_calls"] == 1
    assert budget.settle(call, 100) == budget.settle(call, 100) == Decimal("0.0000042")
    with pytest.raises(JevError, match="ALREADY_SETTLED"): budget.settle(call, 101)
    assert Budget(path).summary()["charged_or_reserved_usd"] == "0.0000042"
    for invalid in [True, -1, MAX_INPUT_TOKENS + 1]:
        with pytest.raises(JevError, match="INVALID_USAGE"): budget.settle(call, invalid)


def test_budget_concurrent_reservations_never_exceed_one_dollar(tmp_path):
    path = tmp_path / "budget.sqlite"
    # Initialize once, then exercise independent ledger instances/process-like connections.
    Budget(path).reserve()
    def reserve(_):
        try:
            Budget(path).reserve()
            return True
        except JevError as error:
            assert error.code in {"BUDGET_EXCEEDED", "BUDGET_UNAVAILABLE"}
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(reserve, range(400)))
    summary = Budget(path).summary()
    assert Decimal(summary["charged_or_reserved_usd"]) <= 1
    assert summary["calls"] == 1 + sum(outcomes)
    with pytest.raises(JevError, match="BUDGET_EXCEEDED"): Budget(path).reserve()


def test_dataset_count_manifest_and_split_isolation():
    import hashlib
    from collections import Counter
    samples = load_dataset()
    assert len(samples) == 300 and len({s.group for s in samples}) == 100
    assert Counter(s.split for s in samples) == {"dev": 180, "calibration": 60, "test": 60}
    assert all(not s.human_reviewed for s in samples)
    assert all(len({s.split for s in samples if s.group == group}) == 1 for group in {s.group for s in samples})
    path = ROOT / "jev" / "datasets"
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sha256"] == hashlib.sha256((path / "samples.jsonl").read_bytes()).hexdigest()


def test_group_leakage_is_rejected(tmp_path):
    samples = build_samples()[:2]
    samples[1]["split"] = "test"
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join(json.dumps(s) for s in samples), encoding="utf-8")
    with pytest.raises(JevError, match="GROUP_LEAKAGE"): load_dataset(path)


def test_evaluation_never_sends_expected_labels_and_reports_failures(tmp_path):
    class Observed(MockProvider):
        async def ask(self, payload, record):
            assert "expected" not in json.dumps(payload) and "human_reviewed" not in json.dumps(payload)
            return await super().ask(payload, record)
    samples = [Sample.model_validate(s) for s in build_samples()[:3]]
    run_data = run(evaluate(Engine(Observed()), samples, split="dev"))
    report = write_reports(run_data, tmp_path / "report")
    assert report["completed"] == 3 and not report["is_live_accuracy_measurement"]
    assert report["charged_or_reserved_usd"] == "0" and report["actual_or_recorded_models"] == []
    assert {p.name for p in (tmp_path / "report").iterdir()} == {"run.json", "summary.json", "report.md", "cases.csv"}


def test_cli_mock_and_replay_never_use_network(monkeypatch, capsys, tmp_path):
    from jev.__main__ import main
    def forbidden(*a, **kw): raise AssertionError("network forbidden")
    monkeypatch.setattr(httpx.AsyncClient, "post", forbidden)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert main(["decide", "--input", str(ROOT / "jev/datasets/example.json")]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["calls"][0]["source"] == "mock"
    assert main(["decide", "--provider", "live", "--input", str(ROOT / "jev/datasets/example.json")]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "MODEL_NOT_CONFIGURED"


def test_check_and_budget_do_not_create_an_event_loop_or_read_other_keys(monkeypatch, capsys):
    from jev.__main__ import main
    original = os.getenv
    def guarded(key, *a, **kw):
        assert not key.startswith(("DEEPSEEK_", "BACKEND_", "AI_SERVICE_"))
        return original(key, *a, **kw)
    monkeypatch.setattr(os, "getenv", guarded)
    monkeypatch.setattr(asyncio, "run", lambda *a, **kw: pytest.fail("read-only command made event loop"))
    assert main(["check"]) == 0
    assert json.loads(capsys.readouterr().out)["network_requested"] is False
    assert main(["budget"]) == 0


def test_second_round_failure_retains_first_round(request_data):
    class SecondFails(MockProvider):
        async def ask(self, payload, record):
            if Node.ACTION.value in payload["questions"]: raise JevError("SECOND_PHASE_FAILED")
            return await super().ask(payload, record)
    result = run(Engine(SecondFails()).evaluate(request_data))
    assert result.nodes[Node.INTENT].status == result.nodes[Node.EVENT].status == "ok"
    assert result.nodes[Node.ACTION].status == result.nodes[Node.CLARIFICATION].status == "error"
    assert result.final_action == Action.WAIT and result.reasons == ["SECOND_PHASE_FAILED"]


def test_replay_corruption_is_closed(tmp_path, request_data):
    provider = live_provider(tmp_path)
    first = run(Engine(provider).evaluate(request_data))
    path = tmp_path / "recordings" / (first.calls[0].fingerprint + ".json")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["question_version"] = "old"
    path.write_text(json.dumps(record), encoding="utf-8")
    result = run(Engine(ReplayProvider(tmp_path / "recordings")).evaluate(request_data))
    assert result.reasons == ["INVALID_REPLAY"] and len(result.calls) == 1


@pytest.mark.parametrize("change", [{"synthetic": False}, {"synthetic": 1}, {"timezone": "invalid/zone"}])
def test_invalid_request_is_rejected(request_data, change):
    with pytest.raises(ValidationError): DecisionRequest.model_validate(request_data | change)


def test_date_and_unit_constraints(request_data):
    request_data["facts"]["fields"].update(purchased_at="2026-10-23", label_expiry="2026-10-22", unit="未知单位")
    result = evaluate_request(request_data)
    assert result.final_action == Action.CLARIFY
    assert {"DATE_CONFLICT", "UNIT_CONFLICT"} <= set(result.reasons)


def test_dangerous_raw_suggestion_is_reported_and_overridden():
    raw = next(s for s in build_samples() if s["category"] == "missing")
    sample = Sample.model_validate(raw)
    run_data = run(evaluate(Engine(MockProvider(overrides={Node.CLARIFICATION.value: "PASS", Node.ACTION.value: "CONFIRM"})), [sample], split="dev"))
    report = summarize(run_data)
    assert report["dangerous_raw_suggestions"] == report["blocked_dangerous_suggestions"] == 1


def test_partial_run_reports_unattempted_samples():
    class NoBudget:
        source = "live"
        async def ask(self, payload, record): raise JevError("BUDGET_EXCEEDED")
    samples = [Sample.model_validate(s) for s in build_samples()[:3]]
    report = summarize(run(evaluate(Engine(NoBudget()), samples, split="dev")))
    assert report["completed"] == 1 and report["unattempted"] == 2 and not report["all_completed"]
    assert report["nodes"][Node.INTENT.value]["accuracy"] == 0


def test_choices_are_matched_by_key_not_option_order(request_data):
    class Reordered(MockProvider):
        async def ask(self, payload, record):
            payload = copy.deepcopy(payload)
            for question in payload["questions"].values():
                if question["type"] == "choice":
                    question["criteria"] = dict(reversed(list(question["criteria"].items())))
            return await super().ask(payload, record)
    baseline = evaluate_request(request_data)
    result = run(Engine(Reordered()).evaluate(request_data))
    assert result.final_action == baseline.final_action
    assert result.nodes[Node.INTENT].answer.choice == baseline.nodes[Node.INTENT].answer.choice


def test_replay_fingerprint_preserves_choice_order():
    from jev.providers import fingerprint
    from jev.questions import first_questions
    payload = {"model": MODEL, "state": {"text": "synthetic"}, "questions": first_questions()}
    reordered = copy.deepcopy(payload)
    question = reordered["questions"][Node.INTENT.value]
    question["criteria"] = dict(reversed(list(question["criteria"].items())))
    assert fingerprint(payload) != fingerprint(reordered)


def test_wrong_outbound_model_rejected_before_reserving(tmp_path):
    provider = live_provider(tmp_path)
    with pytest.raises(JevError, match="INVALID_MODEL_REQUEST"):
        run(provider.ask({"model": "other", "state": {}, "questions": {}}, trace()))
    assert not provider.budget.path.exists()


@pytest.mark.skipif(os.getenv("JEV_RUN_LIVE_SMOKE") != "1" or not os.getenv("TYPESAFE_API_KEY"),
                    reason="Real paid Jev smoke requires explicit opt-in and a configured key")
def test_real_jev_smoke():
    provider = LiveProvider(Config.from_environment())
    result = run(Engine(provider).evaluate(build_samples()[0]["request"]))
    assert result.status != "unavailable", result.reasons
    assert len(result.calls) == 2 and all(c.source == "live" and c.usage_measured for c in result.calls)
