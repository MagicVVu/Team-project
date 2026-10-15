"""HTTP acceptance client for the real business gateway, never a backend server.

Inspect requires no identity. Positive checks create tasks/drafts only and need
an existing dedicated test household containing real, active inventory.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
from pydantic import ValidationError

from p2.schemas import AgentResult
from p0.schemas import Model
from pydantic import AwareDatetime, Field


class PublicClarification(Model):
    revision: int = Field(ge=1)
    allowed_fields: list[str]
    expires_at: AwareDatetime


class PublicResult(AgentResult):
    # Raw, server-owned contexts must never be returned to an App client.
    clarification: PublicClarification | None = None


class CheckFailure(Exception):
    pass


def require(condition, code):
    if not condition:
        raise CheckFailure(code)


def unwrap(response, expected_status=200):
    require(response.status_code == expected_status, f"HTTP_{response.status_code}_EXPECTED_{expected_status}")
    try:
        value = response.json()
    except ValueError:
        raise CheckFailure("RESPONSE_NOT_JSON") from None
    require(isinstance(value, dict), "RESPONSE_NOT_OBJECT")
    if "success" in value:
        require(value["success"] is True and isinstance(value.get("data"), dict), "BUSINESS_ENVELOPE_ERROR")
        value = value["data"]
    require("context" not in value and "scope" not in value, "PRIVATE_CONTEXT_EXPOSED")
    return value


def message_result(value):
    require(value.get("inventory_written") is False, "INVENTORY_WRITE_FLAG_INVALID")
    require(isinstance(value.get("task_id"), str) and bool(value["task_id"]), "TASK_ID_MISSING")
    try:
        result = PublicResult.model_validate(value.get("result"))
    except ValidationError:
        raise CheckFailure("PUBLIC_AGENT_RESULT_INVALID_OR_PRIVATE_CONTEXT_EXPOSED") from None
    require(value.get("status") == result.status, "TASK_RESULT_STATUS_MISMATCH")
    return result


def validate_base_url(value):
    url = httpx.URL(value)
    if (url.scheme not in {"http", "https"} or not url.host or url.username or url.password
            or url.query or url.fragment):
        raise ValueError("使用不含凭据或查询参数的后端 URL")
    if url.scheme == "http" and url.host not in {"localhost", "127.0.0.1", "::1", "backend"}:
        raise ValueError("远端使用 HTTPS，或通过 SSH 转发到本机回环地址")
    return value.rstrip("/")


class BackendProbe:
    def __init__(self, client, *, household_id=None, household_timezone="Asia/Shanghai"):
        self.client, self.household_id = client, household_id
        self.timezone = household_timezone
        self.report = {"kind": "real_backend_http_acceptance", "checked_at": datetime.now(timezone.utc).isoformat(),
                       "checks": [], "inventory_write_requests": 0, "task_ids": [], "draft_ids": []}

    def check(self, name, action):
        try:
            metadata = action() or {}
            self.report["checks"].append({"name": name, "passed": True, **metadata})
            return True
        except (CheckFailure, httpx.HTTPError, ValidationError) as error:
            # No raw bodies, household facts, exception URLs or credentials.
            code = str(error) if isinstance(error, CheckFailure) else type(error).__name__
            self.report["checks"].append({"name": name, "passed": False, "code": code})
            return False

    def inspect(self):
        def health():
            body = unwrap(self.client.get("/api/v1/health"))
            require(body.get("status") in {"ok", "healthy"}, "BACKEND_HEALTH_INVALID")
            return {"backend_version": body.get("version")}
        def ready():
            body = unwrap(self.client.get("/api/v1/ready"))
            require(body.get("status") == "ready" and body.get("database") == "ok", "DATABASE_NOT_READY")
        def contract():
            body = unwrap(self.client.get("/openapi.json"))
            required = {"/api/v1/agent/messages": "post", "/api/v1/agent/clarifications/{task_id}": "post",
                "/api/v1/agent/tasks/{task_id}": "get", "/api/v1/drafts/{draft_id}": "get"}
            require(all(method in body.get("paths", {}).get(path, {}) for path, method in required.items()),
                    "BACKEND_ROUTES_INCOMPLETE")
            return {"openapi_version": body.get("info", {}).get("version")}
        for name, action in (("backend_health", health), ("database_ready", ready), ("gateway_openapi", contract)):
            self.check(name, action)

    def post_message(self, text):
        body = {"household_id": self.household_id, "text": text,
                "request_id": "p2-integration-" + uuid4().hex, "household_timezone": self.timezone}
        value = unwrap(self.client.post("/api/v1/agent/messages", json=body))
        result = message_result(value)
        require(all(b.household_id == self.household_id for b in result.facts + result.candidates),
                "CROSS_HOUSEHOLD_FACTS_RETURNED")
        if result.preview and result.preview.before:
            require(result.preview.before.household_id == self.household_id, "CROSS_HOUSEHOLD_PREVIEW_RETURNED")
        self.report["task_ids"].append(value["task_id"])
        return body, value, result

    def positive(self, *, expect_p2=False):
        first = {}
        def inventory():
            body, value, result = self.post_message("库存有什么")
            require(result.status == "answered" and bool(result.facts), "NO_TEST_INVENTORY_OR_QUERY_FAILED")
            require(any(b.status == "ACTIVE" and b.quantity > 0 for b in result.facts), "NO_ACTIVE_TEST_INVENTORY")
            first.update(body=body, value=value, facts={b.id: b for b in result.facts})
            return {"batch_count": len(result.facts), "trace_id": result.trace_id}
        if not self.check("real_inventory_query", inventory):
            return
        def replay():
            value = unwrap(self.client.post("/api/v1/agent/messages", json=first["body"]))
            result = message_result(value)
            require(value["task_id"] == first["value"]["task_id"], "IDEMPOTENT_TASK_ID_CHANGED")
            require(value["result"] == first["value"]["result"], "IDEMPOTENT_RESULT_CHANGED")
            require(result.status == "answered", "REPLAY_FAILED")
            # Same result proves HTTP dedup behavior, not provider call counts.
        self.check("same_key_same_result", replay)
        def conflict():
            body = {**first["body"], "text": "牛奶在哪"}
            require(self.client.post("/api/v1/agent/messages", json=body).status_code == 409, "IDEMPOTENCY_CONFLICT_NOT_REJECTED")
        self.check("same_key_different_body_rejected", conflict)
        def restored():
            task_id = quote(first["value"]["task_id"], safe="")
            value = unwrap(self.client.get("/api/v1/agent/tasks/" + task_id))
            result = message_result(value)
            require(value["task_id"] == first["value"]["task_id"] and result.status == "answered", "TASK_RECOVERY_FAILED")
        self.check("task_get_recovery", restored)
        active = next(b for b in first["facts"].values() if b.status == "ACTIVE" and b.quantity > 0)
        def draft():
            _, value, result = self.post_message("丢弃全部" + active.name)
            if result.status == "needs_clarification":
                require(result.clarification is not None and "batch_id" in result.clarification.allowed_fields,
                        "DRAFT_SELECTION_NOT_AVAILABLE")
                candidate = next((b for b in result.candidates if b.id == active.id), None)
                require(candidate is not None, "EXPECTED_BATCH_NOT_CANDIDATE")
                task_id = quote(value["task_id"], safe="")
                value = unwrap(self.client.post("/api/v1/agent/clarifications/" + task_id,
                    json={"revision": result.clarification.revision, "answers": {"batch_id": candidate.id}}))
                result = message_result(value)
            require(result.status == "needs_confirmation" and result.draft is not None, "DRAFT_NOT_GENERATED")
            require(result.draft.action == "DISCARD" and result.draft.batch_id == active.id
                    and result.draft.expected_version == active.version, "DRAFT_FACTS_MISMATCH")
            require(result.draft.discard_mode == "all" and result.draft.quantity == active.quantity
                    and result.draft.unit == active.unit, "DISCARD_ALL_QUANTITY_MISMATCH")
            require(result.preview is not None and result.preview.prospective is True, "PROSPECTIVE_PREVIEW_MISSING")
            require(result.preview.before is not None and result.preview.before.version == active.version
                    and result.preview.quantity_delta == -active.quantity and result.preview.after is not None
                    and result.preview.after.quantity == 0 and result.preview.after.status == "DISCARDED",
                    "DISCARD_PREVIEW_MISMATCH")
            draft_id = value.get("draft_id")
            require(isinstance(draft_id, str) and bool(draft_id), "PERSISTED_DRAFT_ID_MISSING")
            self.report["draft_ids"].append(draft_id)
            saved = unwrap(self.client.get("/api/v1/drafts/" + quote(draft_id, safe="")))
            require(saved.get("inventory_written") is False, "DRAFT_READ_WRITE_FLAG_INVALID")
            return {"trace_id": result.trace_id}
        self.check("discard_draft_and_optional_batch_clarification", draft)
        if expect_p2:
            self.check("risk_result_round_trip", self.risk_round_trip)
            self.check("risk_name_clarification", lambda: self.risk_clarification(active.name))
        def unchanged():
            _, _, result = self.post_message("库存有什么")
            require(result.status == "answered" and {b.id: b for b in result.facts} == first["facts"],
                    "INVENTORY_CHANGED_DURING_PROBE")
        self.check("inventory_before_after_unchanged", unchanged)

    def risk_round_trip(self):
        _, value, result = self.post_message("哪些需要关注")
        require(result.status == "answered" and result.intent == "QUERY_RISK", "P2_RISK_ROUTE_UNAVAILABLE")
        require("risks" in value["result"] and "evaluated_count" in value["result"], "P2_FIELDS_DROPPED")
        require(result.evaluated_count == len(result.facts), "RISK_FACT_COUNT_MISMATCH")
        self.validate_risks(result)
        restored = unwrap(self.client.get("/api/v1/agent/tasks/" + quote(value["task_id"], safe="")))
        require(restored.get("result") == value["result"], "RISK_FIELDS_LOST_IN_STORAGE")
        return {"evaluated_count": result.evaluated_count, "returned_count": len(result.risks)}

    @staticmethod
    def validate_risks(result):
        facts = {b.id: b for b in result.facts}
        for risk in result.risks:
            require(risk.batch_id in facts and risk.batch_version == facts[risk.batch_id].version,
                    "RISK_BATCH_VERSION_MISMATCH")
            require(risk.safety_guaranteed is False, "RISK_SAFETY_GUARANTEE_INVALID")

    def risk_clarification(self, name):
        _, value, result = self.post_message("这批还能用吗")
        require(result.status == "needs_clarification" and result.clarification is not None
                and result.clarification.allowed_fields == ["name"], "RISK_CONTEXT_NOT_AVAILABLE")
        response = unwrap(self.client.post("/api/v1/agent/clarifications/" + quote(value["task_id"], safe=""),
            json={"revision": result.clarification.revision, "answers": {"name": name}}))
        completed = message_result(response)
        require(completed.status == "answered" and completed.intent == "QUERY_RISK" and bool(completed.facts),
                "RISK_CLARIFICATION_FAILED")
        self.validate_risks(completed)

    def finish(self):
        self.report["passed"] = bool(self.report["checks"]) and all(c["passed"] for c in self.report["checks"])
        self.report["provider_call_count_verified"] = False
        self.report["database_write_audit_verified"] = False
        return self.report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--positive", action="store_true", help="Create test tasks/drafts; never confirm writes")
    parser.add_argument("--expect-p2", action="store_true")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        base = validate_base_url(args.base_url)
    except ValueError as error:
        parser.error(str(error))
    if args.expect_p2 and not args.positive:
        parser.error("--expect-p2 requires --positive")
    token, household = os.getenv("MAGICVVU_USER_ACCESS_TOKEN"), os.getenv("MAGICVVU_TEST_HOUSEHOLD_ID")
    if args.positive and (not token or not household):
        parser.error("正向检查需要环境中的 MAGICVVU_USER_ACCESS_TOKEN 和 MAGICVVU_TEST_HOUSEHOLD_ID")
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"} if args.positive else {},
                      timeout=15, trust_env=False, follow_redirects=False) as client:
        probe = BackendProbe(client, household_id=household, household_timezone=args.timezone)
        probe.inspect()
        if args.positive and all(c["passed"] for c in probe.report["checks"]):
            probe.positive(expect_p2=args.expect_p2)
        report = probe.finish()
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
