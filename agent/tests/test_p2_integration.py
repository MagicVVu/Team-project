"""Contract tests only. HTTP transports here are never runtime inventory tools."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from eval.p2.fixtures import FixtureReader
from integration.agent_health import validate as validate_health
from integration.backend_v06 import BackendProbe, CheckFailure, message_result, validate_base_url
from p0.domain import DomainError
from p0.schemas import Scope
from p1.schemas import Answers
from p2.app import create_app
from p2.engines import RuleEngine
from p2.knowledge import RuleCatalog
from p2.manager import Manager
from p2.schemas import AgentResult, ClarificationRequest, RiskMessage, RiskSelectionContext
from p2.tools import RemoteInventoryReader


NOW = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)
SCOPE = Scope(user_id="test-user", household_id="test-household")
HEADERS = {"Authorization": "Bearer test-service", "X-User-Id": SCOPE.user_id,
           "X-Household-Id": SCOPE.household_id}


def setup_manager():
    reader = FixtureReader([{"id": "test-batch", "household_id": SCOPE.household_id, "name": "牛奶",
        "quantity": "2", "unit": "盒", "version": 3, "category": "food", "label_expiry": "2026-10-20",
        "label_date_type": "use_by", "label_context_valid": True, "storage_condition": "refrigerated",
        "label_storage_condition": "refrigerated", "is_opened": False}])
    class Counted(RuleEngine):
        calls = 0
        async def extract(self, text):
            self.calls += 1
            return await super().extract(text)
    engine = Counted()
    return Manager(engine, reader, RuleCatalog.load(), now=lambda: NOW), reader, engine


def begin(manager, **kwargs):
    return asyncio.run(manager.handle(RiskMessage(text="这批还能喝吗", request_id="risk-resume", **kwargs), SCOPE))


def resume(manager, first, *, answers=None, revision=None, scope=SCOPE):
    request = ClarificationRequest(context=first.clarification,
        revision=first.clarification.revision if revision is None else revision,
        answers=Answers(**({"name": "牛奶"} if answers is None else answers)))
    return asyncio.run(manager.clarify(request, scope))


def test_risk_resume_round_trip_reads_latest_inventory_and_does_not_call_model():
    manager, reader, engine = setup_manager()
    first = begin(manager, reminder_days=1)
    assert isinstance(first.clarification, RiskSelectionContext)
    assert first.clarification.allowed_fields == ["name"] and reader.reads == []
    stored = AgentResult.model_validate_json(first.model_dump_json())
    assert isinstance(stored.clarification, RiskSelectionContext)
    reader.batches["test-batch"].label_expiry = NOW.date() - timedelta(days=1)
    reader.batches["test-batch"].version += 1
    before = reader.snapshot()
    result = resume(manager, stored)
    assert result.status == "answered" and result.risks[0].level == "red"
    assert result.risks[0].batch_version == 4 and result.clarification is None
    assert result.original_text == first.original_text and result.trace_id == first.trace_id
    assert engine.calls == 1 and reader.snapshot() == before


@pytest.mark.parametrize("change,code", [
    ({"revision": 2}, "CLARIFICATION_CONFLICT"),
    ({"expires_at": NOW}, "CLARIFICATION_EXPIRED"),
    ({"created_at": NOW + timedelta(minutes=1)}, "CLARIFICATION_EXPIRED"),
    ({"expires_at": NOW - timedelta(minutes=1)}, "CLARIFICATION_EXPIRED"),
    ({"allowed_fields": []}, "INVALID_CLARIFICATION"),
])
def test_invalid_risk_context_does_not_read_or_invoke_model(change, code):
    manager, reader, engine = setup_manager()
    first = begin(manager)
    first.clarification = first.clarification.model_copy(update=change)
    result = resume(manager, first, revision=1)
    assert result.error_code == code and reader.reads == [] and engine.calls == 1
    assert result.clarification.revision == first.clarification.revision


@pytest.mark.parametrize("answers", [{}, {"batch_id": "test-batch"}, {"quantity": "1"},
    {"opened_at": "昨天"}, {"name": "牛奶", "location": "厨房"}])
def test_risk_answers_cannot_update_inventory_or_choose_unoffered_batch(answers):
    manager, reader, engine = setup_manager()
    first = begin(manager)
    result = resume(manager, first, answers=answers)
    assert result.error_code == "INVALID_CLARIFICATION" and not reader.reads and engine.calls == 1


def test_risk_scope_denial_does_not_expose_original_or_context():
    manager, reader, engine = setup_manager()
    first = begin(manager)
    denied = resume(manager, first, scope=Scope(user_id="other", household_id=SCOPE.household_id))
    assert denied.error_code == "HOUSEHOLD_FORBIDDEN"
    assert not denied.original_text and denied.clarification is None and not denied.facts
    assert reader.reads == [] and engine.calls == 1


def test_risk_resume_retains_timezone_reminder_and_all_matching_batches():
    manager, reader, engine = setup_manager()
    reader.batches["test-batch"].label_expiry = NOW.date() + timedelta(days=2)
    reader.batches["second"] = reader.batches["test-batch"].model_copy(update={"id": "second"})
    first = begin(manager, reminder_days=1, household_timezone="UTC")
    result = resume(manager, first)
    assert len(result.risks) == 2 and all(r.level == "green" and r.household_timezone == "UTC" for r in result.risks)
    assert engine.calls == 1


def test_timeout_preserves_risk_name_revision_and_original_expiry():
    manager, reader, engine = setup_manager()
    first = begin(manager)
    async def slow(*args):
        await asyncio.sleep(.1)
    reader.search = slow
    manager.timeout_seconds = .01
    result = resume(manager, first)
    assert result.error_code == "AGENT_TIMEOUT" and result.retryable
    assert result.clarification.parsed.name == "牛奶" and result.clarification.revision == 2
    assert result.clarification.expires_at == first.clarification.expires_at and engine.calls == 1


def test_p2_api_accepts_new_risk_context_and_original_p1_context(monkeypatch):
    manager, reader, engine = setup_manager()
    monkeypatch.setenv("AI_SERVICE_TOKEN", "test-service")
    monkeypatch.delenv("P2_ENGINE", raising=False)
    client = TestClient(create_app(engine=engine, reader=reader, now=lambda: NOW))
    health = client.get("/health").json()
    assert health["engine"] == "rules" and validate_health(health, "rules")
    first = client.post("/agent/message", headers=HEADERS,
        json={"text": "这批还能喝吗", "request_id": "r1"}).json()
    body = {"context": first["clarification"], "revision": 1, "answers": {"name": "牛奶"}}
    result = client.post("/agent/clarification", headers=HEADERS, json=body)
    assert result.status_code == 200 and result.json()["intent"] == "QUERY_RISK"
    body["context"]["protocol_version"] = "unknown-version"
    assert client.post("/agent/clarification", headers=HEADERS, json=body).status_code == 422
    first = client.post("/agent/message", headers=HEADERS,
        json={"text": "开封牛奶", "request_id": "r2"}).json()
    assert "protocol_version" not in first["clarification"]
    body = {"context": first["clarification"], "revision": 1, "answers": {"opened_at": "昨天"}}
    result = client.post("/agent/clarification", headers=HEADERS, json=body).json()
    assert result["draft"]["action"] == "OPEN" and reader.batches["test-batch"].opened_at is None


@pytest.mark.parametrize("status,code", [(401, "TOOL_UNAUTHENTICATED"), (403, "HOUSEHOLD_FORBIDDEN"),
    (404, "BATCH_NOT_FOUND"), (409, "TOOL_DATA_CONFLICT"), (500, "TOOL_UNAVAILABLE")])
def test_remote_tool_errors_have_stable_codes_without_echoing_upstream_secrets(monkeypatch, status, code):
    def handler(request):
        assert request.method == "GET" and request.headers["Authorization"] == "Bearer test-tool"
        assert request.headers["X-User-Id"] == SCOPE.user_id
        return httpx.Response(status, json={"error": {"message": "DO_NOT_ECHO_SECRET"}})
    real = httpx.AsyncClient
    monkeypatch.setattr("p2.tools.httpx.AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    reader = RemoteInventoryReader("http://backend", "test-tool")
    with pytest.raises(DomainError) as error:
        asyncio.run(reader.search(SCOPE, "牛奶"))
    assert error.value.code == code and "DO_NOT_ECHO_SECRET" not in error.value.message


def test_public_result_rejects_server_context_and_accepts_only_summary():
    manager, _, _ = setup_manager()
    first = begin(manager)
    value = {"task_id": "task", "status": first.status, "inventory_written": False,
             "result": first.model_dump(mode="json")}
    with pytest.raises(CheckFailure, match="PRIVATE_CONTEXT_EXPOSED"):
        message_result(value)
    context = value["result"]["clarification"]
    value["result"]["clarification"] = {k: context[k] for k in ("revision", "allowed_fields", "expires_at")}
    assert message_result(value).clarification.allowed_fields == ["name"]


@pytest.mark.parametrize("value", ["http://example.com", "https://user:secret@example.com",
    "https://example.com?token=secret", "file:///tmp/backend", "https://example.com/#token"])
def test_probe_rejects_credential_urls_and_unprotected_public_http(value):
    with pytest.raises(ValueError):
        validate_base_url(value)


def test_probe_uses_only_documented_gateway_routes_and_detects_dropped_p2_fields():
    manager, reader, _ = setup_manager()
    before = reader.snapshot()
    tasks, keys, drafts = {}, {}, {}
    dropped = False
    def public(task):
        result = task["result"].model_dump(mode="json")
        if result["clarification"]:
            context = result["clarification"]
            result["clarification"] = {k: context[k] for k in ("revision", "allowed_fields", "expires_at")}
        if dropped and result["intent"] == "QUERY_RISK":
            result.pop("risks")
        return {"task_id": task["id"], "status": result["status"], "revision": task["revision"],
            "draft_id": task["draft_id"], "result": result, "inventory_written": False}
    def save(task, result):
        task["result"] = result
        if result.draft:
            task["draft_id"] = "draft-" + task["id"]
            drafts[task["draft_id"]] = {"inventory_written": False}
    def handler(request):
        # Test-only transport; no socket, backend runtime, or stored real facts.
        assert request.headers["Authorization"] == "Bearer test-user-token"
        path = request.url.path
        assert "confirm" not in path and "/internal/" not in path
        if path == "/api/v1/health":
            body = {"status": "ok", "version": "0.6.0"}
        elif path == "/api/v1/ready":
            body = {"status": "ready", "database": "ok"}
        elif path == "/openapi.json":
            body = {"paths": {p: {m: {}} for p, m in [
                ("/api/v1/agent/messages", "post"), ("/api/v1/agent/clarifications/{task_id}", "post"),
                ("/api/v1/agent/tasks/{task_id}", "get"), ("/api/v1/drafts/{draft_id}", "get")]}}
        elif path == "/api/v1/agent/messages":
            data = json.loads(request.content)
            key = data["request_id"]
            if key in keys:
                task = keys[key]
                if task["body"] != data:
                    return httpx.Response(409, json={})
            else:
                task = {"id": str(len(tasks)+1), "body": data, "revision": 1, "draft_id": None}
                result = asyncio.run(manager.handle(RiskMessage(**{k: v for k, v in data.items() if k != "household_id"}), SCOPE))
                save(task, result)
                tasks[task["id"]] = keys[key] = task
            body = public(task)
        elif path.startswith("/api/v1/agent/clarifications/"):
            task = tasks[path.rsplit("/", 1)[1]]
            data = json.loads(request.content)
            request_body = ClarificationRequest(context=task["result"].clarification, **data)
            save(task, asyncio.run(manager.clarify(request_body, SCOPE)))
            task["revision"] += 1
            body = public(task)
        elif path.startswith("/api/v1/agent/tasks/"):
            body = public(tasks[path.rsplit("/", 1)[1]])
        else:
            body = drafts[path.rsplit("/", 1)[1]]
        return httpx.Response(200, json={"success": True, "data": body})
    with httpx.Client(base_url="http://backend", headers={"Authorization": "Bearer test-user-token"},
                      transport=httpx.MockTransport(handler)) as client:
        probe = BackendProbe(client, household_id=SCOPE.household_id)
        probe.inspect()
        probe.positive(expect_p2=True)
        report = probe.finish()
        assert report["passed"], report
        assert report["inventory_write_requests"] == 0
        assert not report["provider_call_count_verified"] and not report["database_write_audit_verified"]
        dropped = True
        with pytest.raises(CheckFailure, match="P2_FIELDS_DROPPED"):
            probe.risk_round_trip()
    assert before == reader.snapshot()


def test_failed_probe_report_redacts_http_exceptions():
    def handler(request):
        raise httpx.ConnectError("secret URL or user data", request=request)
    with httpx.Client(base_url="http://backend", transport=httpx.MockTransport(handler)) as client:
        probe = BackendProbe(client)
        probe.inspect()
        report = probe.finish()
    assert not report["passed"] and "secret" not in json.dumps(report)


def test_handoff_package_contains_only_allowlisted_runtime_and_contract_files(tmp_path):
    import hashlib
    import tarfile
    from integration.package import package
    result = package(tmp_path / "p2.tar.gz")
    assert not result["remote_deployed"]
    with tarfile.open(result["archive"], "r:gz") as archive:
        names = archive.getnames()
        assert "agent/p2/rules.json" in names and "agent/Dockerfile.p2" in names
        assert "docs/versions/V1-P2/ai-openapi.json" in names
        assert not any(".env" in name or ".cache" in name or "/tests/" in name
                       or "/fixtures" in name or name.startswith("backend/") for name in names)
        assert all(not name.startswith("/") and ".." not in name.split("/") for name in names)
        manifest = json.load(archive.extractfile("p2-integration-manifest.json"))
        for name, digest in manifest["files"].items():
            assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest


def test_exported_contract_matches_current_factory(monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("AI_SERVICE_TOKEN", "test-service")
    monkeypatch.setenv("P2_ENGINE", "rules")
    path = Path(__file__).resolve().parents[2] / "docs/versions/V1-P2/ai-openapi.json"
    assert json.loads(path.read_text(encoding="utf-8")) == create_app(engine=RuleEngine(), reader=object()).openapi()


def test_server_source_manifest_excludes_documents_secrets_and_existing_modules():
    from integration.source_manifest import manifest
    result = manifest()
    assert not result["documents_included"] and not result["credentials_included"]
    assert "p2/rules.json" in result["files"] and "integration/backend_v06.py" in result["files"]
    assert all(not name.startswith(("p0/", "p1/", "tests/", "docs/"))
               and not name.endswith((".md", ".docx", ".tar.gz", ".key", ".pem"))
               and name != "requirements.runtime.txt" for name in result["files"])


def test_server_source_manifest_rejects_missing_runtime_code(tmp_path):
    from integration.source_manifest import manifest
    with pytest.raises(ValueError, match="missing or outside"):
        manifest(tmp_path)
