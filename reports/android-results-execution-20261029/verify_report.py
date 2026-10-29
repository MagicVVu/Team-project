"""Summarize the saved local checks; never contacts a device or server."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

report = Path(__file__).resolve().parent
root = report.parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_log(name):
    raw = (report / name).read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")


build = read_log("build.log")
device = read_log("instrumentation.log")
assert "BUILD SUCCESSFUL" in build
assert "OK (42 tests)" in device and "FAILURES!!!" not in device
current_class = current_test = ""
tests = []
for line in device.splitlines():
    if line.startswith("INSTRUMENTATION_STATUS: class="):
        current_class = line.split("=", 1)[1]
    elif line.startswith("INSTRUMENTATION_STATUS: test="):
        current_test = line.split("=", 1)[1]
    elif line == "INSTRUMENTATION_STATUS_CODE: 0":
        tests.append({"class": current_class, "test": current_test, "passed": True})
assert len(tests) == 42
unit_xml = sorted((root / "frontend/app/build/test-results/testDebugUnitTest").glob("TEST-*.xml"))
totals = {key: sum(int(ET.parse(path).getroot().get(key, 0)) for path in unit_xml)
          for key in ("tests", "failures", "errors", "skipped")}
assert totals == {"tests": 67, "failures": 0, "errors": 0, "skipped": 0}
sources = [
    "data/AgentClient.kt", "data/AssistantModels.kt", "data/AssistantStore.kt",
    "data/AssistantResults.kt", "data/DraftConfirmations.kt",
    "ui/AgentResultCards.kt", "ui/AlignmentUi.kt", "ui/CloudAssistant.kt",
]
files = [root / "frontend/app/src/main/java/com/example/teamapp" / name for name in sources]
files += [root / "frontend/app/src/androidTest/java/com/example/teamapp" / name for name in (
    "AssistantResultsExecutionTest.kt", "AssistantResultsUiTest.kt", "FrontendAlignmentTest.kt", "ConversationFlowTest.kt")]
apk = root / "frontend/app/build/outputs/apk/debug/app-debug.apk"
data = {
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "build_success": True,
    "jvm": totals,
    "device": {"android": 36, "tests": 42, "failures": 0,
               "classes": dict(Counter(item["class"] for item in tests)), "cases": tests},
    "apk": {"path": str(apk), "bytes": apk.stat().st_size, "sha256": digest(apk)},
    "production_accounts_used": False,
    "production_writes": False,
    "paid_model_calls": False,
    "production_end_to_end_verified": False,
    "backend_deployment_modified": False,
    "source_sha256": {str(path.relative_to(root)).replace("\\", "/"): digest(path) for path in files},
    "evidence_sha256": {str(path.relative_to(report)).replace("\\", "/"): digest(path)
                        for path in [report / "build.log", report / "instrumentation.log", *sorted((report / "screenshots").glob("*.png"))]},
}
(report / "validation.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"jvm": totals, "device": data["device"]["classes"], "apk": data["apk"]}, ensure_ascii=False))
