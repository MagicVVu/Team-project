"""Reproduce P4 unit, frozen regression and P1/P2/P3 rules evaluations offline."""
import argparse
import asyncio
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from eval.p4.verify import REPO, offline, verify


def validate(out):
    out.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [str(REPO), str(REPO / "agent")]
    offline()
    import pytest
    with (out / "pytest-output.txt").open("w", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
        unit_exit = pytest.main([str(REPO / "agent/tests"), str(REPO / "backend/tests"),
            "-q", "--tb=short", "-p", "no:cacheprovider", "--junitxml=" + str(out / "pytest.xml")])
    suites = ET.parse(out / "pytest.xml").getroot().findall("testsuite")
    unit = {key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")}
    unit["exit_code"] = int(unit_exit)
    print("P4 unit tests:", unit, flush=True)
    with (out / "legacy-output.txt").open("w", encoding="utf-8") as log, redirect_stdout(log):
        legacy_ok = verify(out / "legacy")
    print("P4 reported program defects resolved:", legacy_ok, flush=True)
    native = {}
    directory = out / "native"
    directory.mkdir()
    for version in ("p1", "p2", "p3"):
        module = importlib.import_module(f"eval.{version}.run")
        for split, count in (("dev", 90), ("test", 60)):
            results = module.ROOT / "results"
            before = set(results.glob("*.json"))
            name = f"{version}-rules-{split}"
            with (directory / f"{name}.txt").open("w", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
                asyncio.run(module.run(SimpleNamespace(engine="rules", split=split, limit=None)))
            created = set(results.glob("*.json")) - before
            if len(created) != 1:
                raise RuntimeError("Native evaluation did not generate exactly one new report")
            source = created.pop()
            target = directory / f"{name}.json"
            if not source.resolve().is_relative_to(REPO) or not target.resolve().is_relative_to(out.resolve()):
                raise RuntimeError("Native report relocation is outside the repository/evidence directory")
            shutil.move(str(source), str(target))
            data = json.loads(target.read_text(encoding="utf-8"))
            metrics = data["metrics"]
            rows = data["rows"]
            passed = (len(rows) == count and metrics["all_checks_accuracy"] == 1 and
                      all(row["checks"]["no_writes"] for row in rows) and
                      all(row.get("attempted", True) for row in rows))
            native[name] = {"count": len(rows), "passed": passed, "metrics": metrics,
                            "dataset_sha256": data["metadata"]["dataset_sha256"],
                            "report": f"native/{name}.json"}
            print(name, "passed=", passed, flush=True)
    paths = [path for module in ("p0", "p1", "p2", "p3", "integration")
             for path in sorted((REPO / "agent" / module).glob("*.py"))]
    paths += [REPO / "backend/app.py", *sorted((REPO / "agent/eval/p4").glob("*.py"))]
    result = {"release_version": "V1-P4", "run_at_utc": datetime.now(timezone.utc).isoformat(),
              "unit_tests": unit, "program_defects_resolved": legacy_ok,
              "native_evaluations": native, "all_local_checks_passed": unit_exit == 0 and legacy_ok and all(r["passed"] for r in native.values()),
              "source_sha256": {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              "real_model_retested": False, "formal_backend_verified": False,
              "device_storage_verified": False, "remote_updated": False, "human_signoff": False}
    (out / "validation-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result["all_local_checks_passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="A new output directory; existing evidence is never overwritten")
    args = parser.parse_args()
    raise SystemExit(0 if validate(args.out.resolve()) else 1)
