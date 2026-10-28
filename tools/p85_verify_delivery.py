"""Local artifact audit; no SSH, database, provider call, or Git mutation."""
import ast
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"agent"))
from integration.source_manifest import manifest
from conversation.p85.schemas import (P85Request, P85ResolveRequest, P85RespondRequest,
                                      P85Archive, P85Episode, P85Plan)
from eval.dialogue.run import fixture, NOW, SCOPE
from datetime import timedelta

DOCS = ROOT/"docs/versions/V1-P8.5"
REPORTS = ROOT/"reports/p85-memory"


def read(path): return json.loads(path.read_text(encoding="utf-8"))
def write(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def main():
    for path in DOCS.glob("*.md"):
        for _, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if not target.startswith(("http:", "https:", "#")):
                assert (path.parent/target.split("#")[0]).exists(), (path.name, target)
    schemas = {}
    for path in (DOCS/"contracts").glob("*.json"):
        value = read(path)
        if path.name.endswith(".schema.json"):
            Draft202012Validator.check_schema(value)
            schemas[path.stem] = value
    api = read(DOCS/"contracts/ai-openapi.json")
    for stage in ("understand", "resolve", "respond"):
        assert "/agent/dialogue/p85/"+stage in api["paths"]
    def refs(value, root):
        if isinstance(value, dict):
            if "$ref" in value:
                assert value["$ref"].startswith("#/"), "External schema reference"
                target = root
                for bit in value["$ref"][2:].split("/"):
                    target = target[bit.replace("~1", "/").replace("~0", "~")]
            for child in value.values(): refs(child, root)
        elif isinstance(value, list):
            for child in value: refs(child, root)
    refs(api, api)
    base = manifest()
    for path in sorted((ROOT/"agent/conversation/p85").glob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"))
        base["files"][path.relative_to(ROOT/"agent").as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    base.update(kind="P8.5 local candidate code allowlist; NOT synchronized", stage="V1-P8.5")
    write(REPORTS/"candidate-source-manifest.json", base)

    statistics = {}
    for name in ("p84-baseline-dev", "deepseek-dev-initial", "deepseek-holdout-first", "deepseek-postfix-regression", "final-saved-plans-replay"):
        data = read(REPORTS/(name+".json"))
        turns = [t for s in data["results"] for t in s["turns"]]
        statistics[name] = {k: data[k] for k in ("mode", "scenario_count", "turn_count", "scenario_success_rate", "turn_success_rate", "p95_ms", "max_model_calls")}
        statistics[name].update(passed_turns=sum(t["passed"] for t in turns),
            structured_clarification_turns=sum(t.get("resolved", {}).get("kind") == "needs_input" or
                (t.get("resolved", {}).get("result") or {}).get("status") == "needs_clarification" for t in turns),
            provider_error_turns=sum("error_code" in t for t in turns))
    statistics["interpretation"] = "First holdout failed; post-fix evaluation reuses consumed samples; human review pending; latency excludes business DB and App"
    write(REPORTS/"evaluation-summary.json", statistics)

    measured = read(REPORTS/"deepseek-postfix-regression.json")["results"][0]["turns"][0]["resolved"]
    _, context, _ = fixture("reference", None)
    episode = P85Episode.model_validate(measured["memory_delta"]["episode"])
    episode.reference = context.reference
    context = context.model_copy(update={"trusted_now": NOW+timedelta(seconds=30), "revision": 2, "reference": None})
    request = P85Request(text="回到最开始查过的那个，现在还有多少", request_id="synthetic-example",
        context=context, archive=P85Archive(scope=SCOPE, conversation_id=context.conversation_id, revision=2, episodes=[episode]))
    resolution = P85ResolveRequest(**request.model_dump(), plan_context_revision=2,
        plan=P85Plan(speech_act="question", memory_id=episode.memory_id, reads=[{"kind": "quantity"}]))
    examples = {"notice": "Synthetic clock 2026-10-15; not a live server request; caller must refresh permissions, time, revisions and original references",
        "understand_request": request.model_dump(mode="json"), "resolve_request": resolution.model_dump(mode="json"),
        "respond_request": P85RespondRequest(text=measured["original_text"], resolved=measured).model_dump(mode="json")}
    for example, schema in (("understand_request", "understand-request.schema"), ("resolve_request", "resolve-request.schema"), ("respond_request", "respond-request.schema")):
        Draft202012Validator(schemas[schema], format_checker=FormatChecker()).validate(examples[example])
    write(DOCS/"contracts/examples.json", examples)
    tests = {}
    for name in ("ai-tests", "backend-compat-tests"):
        tree = ET.parse(REPORTS/(name+".xml")).getroot()
        suites = [tree] if tree.tag == "testsuite" else list(tree)
        tests[name] = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
        assert tests[name]["failures"] == tests[name]["errors"] == 0
    summary = {"stage": "V1-P8.5", "local_only": True, "server_synchronized": False, "server_version_replaced": False,
        "frontend_source_changed": False, "backend_source_changed": False, "new_tables": False, "new_dependencies": False,
        "git_committed": False, "git_pushed": False, "tests": tests, "runtime_allowlist_files": len(base["files"]),
        "json_contracts": len(list((DOCS/"contracts").glob("*.json"))), "schema_refs_and_examples_checked": True,
        "model_initial_holdout_acceptance": "below_target_not_erased", "postfix_samples": "regression_not_blind",
        "human_naturalness_review": "pending", "backend_p85_adapter": "not_implemented", "app_acceptance": "not_run"}
    write(REPORTS/"delivery-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__": main()
