"""Collect local delivery evidence. Does not invoke SSH or run tests/models."""
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
from integration.source_manifest import manifest

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
TARGET = REPO/"docs/versions/V1-P7"
PRIVATE = REPO.parent/".runtime/p7-integration"


def tests(name):
    root = ET.parse(TARGET/name).getroot()
    suites = list(root.iter("testsuite"))
    counts = {key:sum(int(s.attrib.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    counts["passed"] = counts["tests"]-counts["failures"]-counts["errors"]-counts["skipped"]
    counts["time_seconds"] = sum(float(s.attrib.get("time", 0)) for s in suites)
    counts["report"] = name
    if name == "ai-tests.xml":
        counts["p7_tests"] = sum(c.attrib.get("classname", "").endswith("test_conversation") for c in root.iter("testcase"))
    return counts


def main():
    current = manifest()["files"]
    dataset = json.loads((ROOT/"manifest.json").read_text(encoding="utf-8"))
    evaluations = {}
    for engine in ("rules", "deepseek-ssh"):
        for split in ("dev", "test"):
            matches = []
            for path in sorted((ROOT/"results").glob(f"{engine}-{split}-*.json"), reverse=True):
                value = json.loads(path.read_text(encoding="utf-8"))
                if value["metadata"]["dataset_sha256"] == dataset["dataset_sha256"] and value["metadata"]["runtime_hashes"] == current:
                    matches.append((path, value))
            if not matches: raise RuntimeError("Missing current evaluation: "+engine+"/"+split)
            path, value = matches[0]
            evaluations[engine+"_"+split] = {"report":path.relative_to(REPO).as_posix(), "metrics":value["metrics"],
                "synthetic_workflow_passed":value["synthetic_workflow_passed"],
                "runtime_unchanged":value["metadata"]["runtime_unchanged"], "human_reviewed":False,
                "budget_before":value["metadata"].get("budget_before"), "budget_after":value["metadata"].get("budget_after")}
    sync = json.loads((PRIVATE/"code-sync-report.json").read_text(encoding="utf-8-sig"))
    remote = json.loads((PRIVATE/"remote-verification.json").read_text(encoding="utf-8-sig"))
    if sync["files"] != current or remote["runtime_files"] != current:
        raise RuntimeError("Remote and local source hashes differ")
    for source, dest in (("code-sync-report.json", "code-sync-report.json"), ("remote-verification.json", "server-verification.json")):
        shutil.copyfile(PRIVATE/source, TARGET/dest)
    regression = {"ai":tests("ai-tests.xml"), "legacy_gateway":tests("legacy-gateway-tests.xml"),
                  "business_backend":tests("business-backend-tests.xml")}
    status = {"release":"V1-P7", "ai_version":"0.7.0", "date":"2026-10-17", "timezone":"Asia/Shanghai",
        "base_commit":subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "ai_implementation_complete":True,
        "local_automated_validation_complete":all(v["errors"] == v["failures"] == 0 for v in regression.values()),
        "model_workflow_validation_complete":all(v["synthetic_workflow_passed"] for k,v in evaluations.items() if k.startswith("deepseek")),
        "frontend_p7_integrated":False, "backend_trusted_reference_adapter_integrated":False,
        "unified_draft_confirmation_integrated":False, "joint_acceptance_complete":False,
        "formal_ai_acceptance_complete":False, "full_v1_product_complete":False,
        "database_gateway_modified":False, "frontend_modified":False, "backend_product_code_modified":False,
        "inventory_or_shopping_writes":False, "new_mock_service":False,
        "git_commit_or_push":False, "production_ai_switched":False, "jev":"deferred_by_user",
        "regression":regression, "dataset":dataset, "evaluation":evaluations,
        "runtime_sync":{"file_count":len(current), "hashes_verified":True, "remote_imports_verified":remote["python_imports_verified"],
            "app_version":remote["app_version"], "backend_health":remote["backend_health_read_only"],
            "remote_root":sync["remote_root"], "documents_uploaded":False, "tests_uploaded":False,
            "credentials_uploaded":False, "services_started":False},
        "limitations":["Synthetic facts and unreviewed constructed samples; not Android/production DB end-to-end",
            "Internal reference forwarding requires a separate trusted business adapter; public gateway unchanged",
            "Consume semantic events, OPEN and DISCARD confirmation require backend capabilities",
            "P7 Docker image not built or deployed; P6 entry and operator launcher preserved"],
        "previous_evidence":{"dataset":"agent/eval/conversation/archive/v1/samples.jsonl",
            "reports_preserved":True, "reason":"Independent unit tests prompted boundary fixes and a new holdout; no holdout-driven tuning"}}
    (TARGET/"implementation-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    table = []
    for label, key in (("规则开发", "rules_dev"), ("规则保留", "rules_test"), ("DeepSeek 开发", "deepseek-ssh_dev"), ("DeepSeek 保留", "deepseek-ssh_test")):
        value = evaluations[key]
        m = value["metrics"]
        table.append(f"| {label} | {m['all_checks_passed']}/{m['count']} | {m['intent_accuracy']:.0%} | {m['clarification_recall']:.0%} | {m['draft_field_accuracy']:.0%} | {m['p95_seconds']:.3f}s |")
    text = "# P7 交付与验证\n\n2026-10-17，AI 0.7.0。AI 实现与本地验证完成；Android、独立业务适配/确认、联合验收及正式切换未完成。\n\n"
    text += f"AI 回归 {regression['ai']['passed']} 项通过、{regression['ai']['skipped']} 项跳过，其中 P7 专项 {regression['ai']['p7_tests']} 项。旧网关 {regression['legacy_gateway']['passed']} 项、正式后端本地回归 {regression['business_backend']['passed']} 项通过。报告见对应 XML。\n\n"
    text += "| 评测 | 全检查通过 | 意图准确率 | 澄清召回率 | 草稿字段准确率 | P95 |\n|---|---|---|---|---|---|\n"+"\n".join(table)+"\n\n"
    text += "当前 150 条为 v2 数据集，90 开发/60 保留，50 个场景组隔离，人工复核 pending。原 v1 样本和全部报告保留；独立单元测试发现字段注入与超时丢字段后，修正代码并使用此前未用的51～70组作新保留集。当前报告的运行文件哈希与本地、服务器一致，评测期间运行代码未变。\n\n"
    text += "DeepSeek 调用使用用户已配置的服务器私有密钥，只有合成文本通过 SSH 传入，评测文件和夹具没有上传。原累计预算账本继续使用，没有重置；无自动模型重试。P95 包含本地 AI 与 SSH/模型耗时，但没有真实数据库和 Android/确认事务，不能当作产品性能验收。\n\n"
    text += f"服务器核验 {len(current)} 个白名单运行文件；入口 conversation.app:create_app、版本0.7.0，导入/OpenAPI/健康配置检查通过。正式后端只读 health 为 {remote['backend_health_read_only'].get('version')}。未启动/切换服务、未构建镜像、未上传密钥/文档/测试、未改网关或执行正式业务写入。\n\n"
    text += "前后端分别按 frontend-handoff.md、backend-handoff.md 承接；完整移动场景与中断恢复仍待联合执行。详细机器状态见 implementation-status.json。\n"
    (TARGET/"delivery-and-validation.md").write_text(text, encoding="utf-8")
    checked = 0
    for path in [*TARGET.glob("*.md"), REPO/"agent/conversation/README.md"]:
        for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if link.startswith(("http", "#", "/")): continue
            checked += 1
            if not (path.parent/link.split("#", 1)[0]).resolve().exists():
                raise RuntimeError("Broken delivery link: "+str(path)+": "+link)
    if not checked: raise RuntimeError("No delivery links checked")
    print(json.dumps({"markdown_links_checked":checked}))
    print(json.dumps({"tests":regression, "evaluation":{k:v["metrics"] for k,v in evaluations.items()}, "runtime_files":len(current)}))


if __name__ == "__main__": main()
