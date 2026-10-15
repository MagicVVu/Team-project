"""Offline P4 verification; preserves every legacy expectation and review gate.

Run from the repository: python agent/eval/p4/verify.py --out PATH.
Exit 0 means the reported program defects are resolved with no new regression.
It does not mean that the legacy suite or formal device acceptance passed.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
SUITE = REPO / "tests/garin/test_package/Agent_Regression_v1"
TARGETS = {"p0-regression": "local_p0", "p1-regression": "local_p1",
           "android-regression": "android_gateway"}
CASE_FILES = ("baseline_150", "extended", "flows")


def load_cases():
    return [json.loads(line) for name in CASE_FILES
            for line in (SUITE / "cases" / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]


def prior_issues():
    rows = json.loads((REPO / "tests/garin/失败清单.json").read_text(encoding="utf-8"))
    return {(r["target"], r["id"]): r for r in rows}


def resolution(target, case_id, observation, errors):
    """Explicit P1/device contract checks; never rewrite legacy assertions."""
    if not errors:
        return "legacy_assertions_pass"
    result = observation.get("result", {})
    safe = (result.get("draft") is None and
            observation.get("before") is not None and
            observation["before"] == observation.get("after"))
    if (target == "p1-regression" and case_id == "p0-41-2" and safe and
            result.get("intent") == "CONSUME" and result.get("status") == "answered" and
            result.get("error_code") == "BATCH_TERMINAL" and
            len(result.get("facts", [])) == 1 and
            result["facts"][0]["id"] == "tissue-0" and
            result["facts"][0]["status"] == "FINISHED"):
        return "parser_fixed_p1_terminal_contract"
    if (target == "android-regression" and case_id in {"ext-013", "ext-015"} and safe and
            result.get("intent") == "PLAN_ADD" and
            result.get("status") == "needs_clarification" and
            result.get("error_code") == "PLAN_ITEM_REQUIRED" and result.get("manual_entry")):
        return "parser_fixed_device_registration_limit"
    return "unresolved"


def offline():
    # This process owns its environment. Do not read .env or load real models.
    for key in list(os.environ):
        if any(part in key for part in ("API_KEY", "TOKEN", "BASE_URL", "P0_", "P1_", "P2_", "P3_", "LLM_", "APP_AI_ENGINE")):
            os.environ.pop(key, None)
    os.environ.update(P0_ENGINE="rules", P0_MODE="mock", P1_ENGINE="rules",
                      APP_AI_ENGINE="rules", APP_API_TOKEN="local-development", DEMO_TOKEN="demo-local")
    connect = socket.socket.connect

    def denied(*args, **kwargs):
        raise RuntimeError("P4 verification blocks external socket connections")

    def guarded(sock, address):
        frame = sys._getframe(1)
        fallback = getattr(socket, "_fallback_socketpair", None)
        if (fallback is not None and frame.f_code is fallback.__code__ and
                frame.f_locals.get("csock") is sock and
                address == frame.f_locals["lsock"].getsockname()[:2]):
            return connect(sock, address)
        return denied(sock, address)

    socket.socket.connect = guarded
    socket.socket.connect_ex = denied
    socket.create_connection = denied


def verify(out):
    sys.path[:0] = [str(REPO), str(REPO / "agent"), str(SUITE)]
    from run import score
    out.mkdir(parents=True, exist_ok=False)
    cases, old = load_cases(), prior_issues()
    summary, resolved, new_failures, unresolved = {}, [], [], []
    for target, module in TARGETS.items():
        adapter = importlib.import_module("adapters." + module)
        rows = []
        for case in cases:
            row = {"id": case["id"], "gate": case["gate"]}
            if case["gate"] == "review":
                row.update(status="REVIEW", failures=["gold label awaiting human approval"])
            else:
                try:
                    observation = adapter.evaluate(case, {"engine": "rules"})
                    errors = score(case, observation)
                    row.update(status="FAIL" if errors else "PASS", failures=errors, evidence=observation)
                    previous = old.get((target, case["id"]), {})
                    if previous.get("classification") == "程序问题":
                        state = resolution(target, case["id"], observation, errors)
                        item = {"target": target, "id": case["id"], "text": case["text"],
                                "resolution": state, "legacy_status": row["status"],
                                "legacy_failures": errors, "evidence_path": f"{target}/results.jsonl",
                                "evidence_line": len(rows) + 1}
                        (unresolved if state == "unresolved" else resolved).append(item)
                    elif errors and (not previous or previous.get("status") != "FAIL"):
                        new_failures.append({"target": target, "id": case["id"], "failures": errors})
                except NotImplementedError as error:
                    row.update(status="BLOCKED", failures=[str(error)])
                except Exception as error:
                    row.update(status="ERROR", failures=[f"{type(error).__name__}: {error}"])
                    unresolved.append({"target": target, "id": case["id"], "resolution": "execution_error"})
            rows.append(row)
        directory = out / target
        directory.mkdir()
        (directory / "results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        counts = dict(Counter(r["status"] for r in rows))
        summary[target] = {"counts": counts, "legacy_required_pass": all(r["status"] == "PASS" for r in rows if r["gate"] == "required")}
        (directory / "summary.json").write_text(json.dumps(summary[target], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    expected = sum(r.get("classification") == "程序问题" for r in old.values())
    future = SUITE / "cases/future_scenarios.jsonl"
    future_count = len(future.read_text(encoding="utf-8").splitlines())
    sources = [*sorted((REPO / "agent/p0").glob("*.py")),
               *sorted((REPO / "agent/p1").glob("*.py")), REPO / "backend/app.py"]
    frozen = [SUITE / "cases" / f"{name}.jsonl" for name in CASE_FILES]
    report = {"release_version": "V1-P4", "run_at_utc": datetime.now(timezone.utc).isoformat(),
              "base_commit": subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
              "tested_checkout_includes_uncommitted_p4_changes": True,
              "python": sys.version, "engine": "rules", "external_network_blocked": True,
              "counts": summary, "reported_program_failure_occurrences": expected,
              "resolved_occurrences": len(resolved), "resolution_counts": dict(Counter(r["resolution"] for r in resolved)),
              "resolved": resolved, "unresolved": unresolved, "new_failures": new_failures,
              "future_scenarios": {"BLOCKED": future_count, "reason": "No device/production scenario driver; not executed"},
              "source_sha256": {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              "frozen_case_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen},
              "case_expectations_modified": False, "human_signoff": False,
              "real_model_retested": False, "formal_acceptance": False,
              "program_defects_resolved": not unresolved and not new_failures and len(resolved) == expected}
    (out / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("counts", "reported_program_failure_occurrences", "resolved_occurrences", "resolution_counts", "unresolved", "new_failures", "program_defects_resolved")}, ensure_ascii=False, indent=2))
    return report["program_defects_resolved"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    offline()
    raise SystemExit(0 if verify(args.out) else 1)
