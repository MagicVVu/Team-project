"""Validate local evidence/contracts and record exact scope; no network access."""
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DOCS = ROOT/"docs/versions/V1-P8.1"


def test_summary(filename):
    suites = ET.parse(HERE/filename).getroot().iter("testsuite")
    totals = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for key in totals: totals[key] += int(suite.get(key, 0))
    totals["passed"] = totals["tests"]-totals["failures"]-totals["errors"]-totals["skipped"]
    assert totals["failures"] == totals["errors"] == 0
    return totals


def references(value, document):
    if isinstance(value, dict):
        if "$ref" in value and value["$ref"].startswith("#/"):
            found = document
            for part in value["$ref"][2:].split("/"):
                found = found[part.replace("~1", "/").replace("~0", "~")]
        for child in value.values(): references(child, document)
    elif isinstance(value, list):
        for child in value: references(child, document)


def main():
    previous = json.loads((HERE/"verification-summary.json").read_text(encoding="utf-8")) if (HERE/"verification-summary.json").exists() else {}
    # Git quotes non-ASCII paths by default. They are documentation only; use -z for hashes.
    modified = subprocess.check_output(["git", "diff", "--name-only", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    added = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    paths = sorted(set(p for p in modified+added if p))
    forbidden = ("frontend/", "backend/server/alembic/", "backend/server/app/models.py",
                 "backend/server/app/execution_models.py", "backend/server/app/routers/agent_gateway.py", "agent/jev/")
    assert not any(p.startswith(forbidden) for p in paths)
    contracts = []
    for path in sorted((DOCS/"contracts").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        references(document, document)
        contracts.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    candidates = json.loads((DOCS/"contracts/rule-review-candidates.json").read_text(encoding="utf-8"))
    assert all(not r["rule"]["enabled"] and not r["rule"]["reviewed"] for r in candidates["rules"])
    regression = json.loads((HERE/"offline-regression.json").read_text(encoding="utf-8"))
    assert regression["count"] == regression["passed"] == 40 and regression["model_calls"] == 0
    known_source_paths = set(paths) | set(previous.get("source_sha256", {}))
    release_path = DOCS/"production-prepare.json"
    if release_path.exists():
        released = json.loads(release_path.read_text(encoding="utf-8"))
        for service, prefix in (("agent", "agent/"), ("backend", "backend/server/")):
            known_source_paths.update(prefix+p for p in released["overlay_files"][service])
    source_hashes = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(known_source_paths)
                     if (ROOT/p).is_file()
                     if p.startswith(("agent/", "backend/server/")) and p.endswith(".py")}
    summary = {"date": "2026-10-24", "scope": "V1-P8.1_local_validation",
        "ai_tests": test_summary("ai-tests.xml"), "backend_full_tests": test_summary("backend-tests.xml"),
        "backend_final_repair_tests": test_summary("backend-repair-tests.xml"),
        "test_counts_overlap": True,
        "backend_validation_note": "Full regression followed by final repair tests covering post-commit malformed-response protection and real referenced PLAN_ADD round-trip; counts overlap.",
        "offline_regression": {k: v for k,v in regression.items() if k != "cases"},
        "contracts": contracts, "source_sha256": source_hashes,
        "boundary_checks": {"frontend_unchanged": True, "database_models_and_migrations_unchanged": True,
            "database_task_gateway_unchanged": True, "jev_unchanged": True, "human_rules_not_enabled": True},
        "server_sync_in_local_validation": "not_performed", "production_release_in_local_validation": "not_performed", "git_operations_by_this_agent": "none",
        "real_model_evaluation": "not_performed", "android_joint_acceptance": "not_performed",
        "postgresql_concurrency_acceptance": "not_performed", "human_rule_approval": "pending"}
    if (HERE/"p81-backend-release-tests.xml").exists():
        summary["p81_backend_release_tests"] = test_summary("p81-backend-release-tests.xml")
    if (DOCS/"production-deployment.json").exists():
        deployment = json.loads((DOCS/"production-deployment.json").read_text(encoding="utf-8"))
        summary["subsequent_production_release"] = {"maintenance_release": "V1-P8.1", "status": deployment["stage"],
            "record": "docs/versions/V1-P8.1/正式发布记录.md", "tags": deployment["tags"]}
    (HERE/"verification-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for path in DOCS.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if not target.startswith(("http:", "https:", "#")):
                assert (path.parent/target.split("#")[0]).resolve().exists(), (path, target)
    print(json.dumps({k:summary[k] for k in ("ai_tests", "backend_full_tests", "backend_final_repair_tests")}, ensure_ascii=False))


if __name__ == "__main__": main()
