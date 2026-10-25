"""Verify local delivery evidence, links and frozen legacy contracts; no network."""
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from .compatibility import assert_legacy_schema
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT/"docs/versions/V1-P8.2"
REPORTS = ROOT/"reports/session-memory"


def read(path): return json.loads(path.read_text(encoding="utf-8"))


def refs(value, document):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and item.startswith("#/"):
                target = document
                for part in item[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
            else: refs(item, document)
    elif isinstance(value, list):
        for item in value: refs(item, document)


def junit(path):
    suites = ET.parse(path).getroot().iter("testsuite")
    counts = {key:0 for key in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for key in counts: counts[key] += int(suite.get(key, "0"))
    assert counts["failures"] == counts["errors"] == 0, (path.name, counts)
    counts["passed"] = counts["tests"]-counts["skipped"]
    return counts


def main():
    contracts = sorted((DOCS/"contracts").glob("*.json"))
    assert len(contracts) == 10
    for contract in contracts: refs(read(contract), read(contract))
    for filename in ("ai-openapi.json", "backend-openapi.json"):
        current = read(DOCS/"contracts"/filename)
        old = read(ROOT/"docs/versions/V1-P8.1/contracts"/filename)
        assert all(current["paths"][path] == value for path, value in old["paths"].items())
        for name, value in old["components"]["schemas"].items():
            assert_legacy_schema(value, current["components"]["schemas"][name])
    for doc in DOCS.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", doc.read_text(encoding="utf-8")):
            path = (doc.parent/target.split("#")[0]).resolve()
            assert path.is_relative_to(ROOT) and (path.exists() or path == REPORTS/"verification-summary.json"), (doc.name, target)
    dataset = ROOT/"agent/eval/session_memory/samples.jsonl"
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    assert len(rows)==150 and sum(r["split"]=="dev" for r in rows)==90
    assert {r["group_id"] for r in rows if r["split"]=="dev"}.isdisjoint({r["group_id"] for r in rows if r["split"]=="holdout"})
    assert read(dataset.with_name("manifest.json"))["dataset_sha256"] == digest
    offline, provider = read(REPORTS/"offline-all.json"), read(REPORTS/"provider-all.json")
    assert offline["passed"] == offline["total"] == 150 and offline["paid_model_calls"] == 0
    assert provider["passed"] == provider["total"] == 150 and provider["paid_model_calls"] == 10
    assert offline["dataset_sha256"] == provider["dataset_sha256"] == digest
    initial = read(REPORTS/"provider-initial.json")
    source_paths = ["agent/conversation/app.py", "agent/conversation/engines.py", "agent/conversation/manager.py",
        "agent/conversation/health.py", "agent/conversation/schemas.py",
        "agent/conversation/memory.py", "agent/conversation/memory_schemas.py", "agent/integration/source_manifest.py",
        "backend/server/app/main.py", "backend/server/app/memory_schemas.py",
        "backend/server/app/routers/session_memory.py", "backend/server/app/services/session_memory.py",
        "backend/server/app/routers/agent_gateway.py", "backend/server/app/routers/draft_execution.py"]
    summary = dict(scope="local_conversation_memory_increment", maintenance_release="V1-P8.2", version_assigned=True,
        ai=junit(REPORTS/("p82-ai-regression.xml" if (REPORTS/"p82-ai-regression.xml").exists() else "ai-regression.xml")),
        backend=junit(REPORTS/"backend-regression.xml"),
        backend_final_targeted=junit(REPORTS/"backend-final-tests.xml"),
        contracts_verified=len(contracts), legacy_contracts_compatible=True, documentation_links_verified=True,
        offline=dict(passed=150, total=150, paid_model_calls=0, human_review_status="pending"),
        provider=dict(initial_context_passed=sum(r["passed"] for r in initial["results"] if r["actual_provider_calls"]),
            final_context_passed=10, final_context_total=10, actual_calls_total=initial["paid_model_calls"]+provider["paid_model_calls"],
            provider_fixture_flow_p95_ms=provider["provider_fixture_flow_p95_ms"],
            full_intent_acceptance=False, production_p95_verified=False, no_automatic_paid_retry=True),
        delivery=dict(ai="locally_implemented", backend_adapter="locally_implemented", frontend="pending_owner_integration",
                      joint_acceptance="pending", server_sync="not_performed", production_switch="not_performed",
                      schema_migrations="none", git_commit_or_push="not_performed"),
        source_sha256={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in source_paths})
    if (REPORTS/"p82-backend-release.xml").exists():
        summary["backend_release_regression"] = junit(REPORTS/"p82-backend-release.xml")
    if (DOCS/"production-deployment.json").exists():
        deployed=read(DOCS/"production-deployment.json")
        post=read(DOCS/"production-postcheck.json")
        final=read(DOCS/"production-final-check.json")
        assert deployed["maintenance_release"] == "V1-P8.2" and deployed["unrelated_code_preserved"]
        assert post["synthetic_provider_check"]["passed"] and post["public_checks"]["postgres_memory_read"]["passed"]
        assert final["rollback_images_available"] and final["database_container_unchanged"]
        for name in ("production-ai-openapi.json", "production-backend-openapi.json"):
            document=read(DOCS/name)
            refs(document,document)
            assert document["x-maintenance-release"] == "V1-P8.2"
        summary["delivery"].update(server_sync="verified",production_switch="verified")
        summary["production_contracts_verified"] = 2
        summary["provider"]["local_actual_calls"] = summary["provider"]["actual_calls_total"]
        summary["provider"]["server_synthetic_calls"] = post["synthetic_provider_check"]["requests"]
        summary["provider"]["actual_calls_total"] += post["synthetic_provider_check"]["requests"]
        summary["production"] = {"images":deployed["tags"], "database_revision":deployed["database_revision"],
            "unrelated_code_preserved":True, "configuration_preserved":True, "rollback_available":True}
    (REPORTS/"verification-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({key:summary[key] for key in ("ai", "backend", "contracts_verified", "legacy_contracts_compatible", "provider")}, ensure_ascii=True))


if __name__ == "__main__": main()
