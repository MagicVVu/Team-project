"""Frozen grouped datasets and reports; expected labels never reach providers."""
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from .providers import canonical
from .schemas import Model, DecisionRequest, DecisionResult, Node, Action, JevError


class Sample(Model):
    id: str
    group: str
    split: str
    category: str
    human_reviewed: bool = False
    request: DecisionRequest
    expected: dict[str, str]


DATASETS = Path(__file__).resolve().parent / "datasets"


def load_dataset(path=None):
    default_dataset = path is None
    path = Path(path) if path is not None else DATASETS / "samples.jsonl"
    try:
        raw = path.read_bytes()
        if default_dataset:
            manifest = json.loads((DATASETS / "manifest.json").read_text(encoding="utf-8"))
            if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
                raise JevError("DATASET_HASH_MISMATCH")
        samples = [Sample.model_validate_json(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    except (ValueError, OSError, KeyError):
        raise JevError("INVALID_DATASET") from None
    ids, groups = set(), {}
    required = {n.value for n in Node} | {"final_action"}
    from .questions import first_questions, second_questions
    options = first_questions() | second_questions()
    for sample in samples:
        if sample.id in ids or sample.split not in {"dev", "calibration", "test"} or set(sample.expected) != required:
            raise JevError("INVALID_DATASET")
        if any(sample.expected[n.value] not in options[n.value]["criteria"] for n in Node) or sample.expected["final_action"] not in {a.value for a in Action}:
            raise JevError("INVALID_EXPECTED_LABEL")
        ids.add(sample.id)
        if sample.group in groups and groups[sample.group] != sample.split:
            raise JevError("DATASET_GROUP_LEAKAGE")
        groups[sample.group] = sample.split
    return samples


async def evaluate(engine, samples, *, split):
    selected = [s for s in samples if s.split == split] if split != "all" else samples
    if not selected:
        raise JevError("EMPTY_SPLIT")
    rows = []
    for sample in selected:
        result = await engine.evaluate(sample.request)
        rows.append({"id": sample.id, "group": sample.group, "split": sample.split,
                     "category": sample.category, "human_reviewed": sample.human_reviewed,
                     "expected": sample.expected, "result": result.model_dump(mode="json")})
        if "BUDGET_EXCEEDED" in result.reasons or "MODEL_NOT_CONFIGURED" in result.reasons:
            break
    return {"protocol_version": "jev-evaluation-1", "split": split,
            "dataset_sha256": hashlib.sha256(canonical([s.model_dump(mode="json") for s in samples]).encode()).hexdigest(),
            "requested": len(selected), "completed": len(rows), "rows": rows}


def percentile(values, q):
    import math
    return sorted(values)[max(0, math.ceil(len(values) * q) - 1)] if values else None


def summarize(run):
    matrix = {n.value: defaultdict(Counter) for n in Node}
    correct = Counter()
    errors, models, categories = Counter(), set(), Counter()
    passed_clarify = missed_clarify = redundant_clarify = true_pass = 0
    dangerous = blocked = final_correct = real_calls = 0
    billed, recorded_tokens, times = Decimal(0), 0, []
    source_counts, total = Counter(), len(run["rows"])
    for row in run["rows"]:
        result = DecisionResult.model_validate(row["result"])
        expected = row["expected"]
        times.append(result.elapsed_ms)
        categories[row["category"]] += 1
        for n in Node:
            node = result.nodes[n]
            prediction = node.answer.choice if node.answer else "__" + node.status.upper()
            target = expected[n.value]
            matrix[n.value][target][prediction] += 1
            correct[n.value] += prediction == target
            if node.model: models.add(node.model)
        clarify = result.nodes[Node.CLARIFICATION]
        predicted_need = clarify.answer is not None and clarify.answer.choice != "PASS"
        need = expected[Node.CLARIFICATION.value] != "PASS"
        passed_clarify += need and predicted_need
        missed_clarify += need and not predicted_need
        redundant_clarify += not need and predicted_need
        true_pass += not need and not predicted_need
        unsafe = result.raw_action in {Action.READ, Action.CONFIRM} and result.raw_action.value != expected["final_action"]
        dangerous += unsafe
        blocked += unsafe and (result.final_action not in {Action.READ, Action.CONFIRM}
                               or result.final_action.value == expected["final_action"])
        final_correct += result.final_action.value == expected["final_action"]
        if result.status == "unavailable": errors.update(result.reasons)
        for call in result.calls:
            source_counts[call.source] += 1
            real_calls += call.source == "live" and call.attempted
            billed += call.charged_usd
            recorded_tokens += call.input_tokens or 0
    metrics = {}
    for node, values in matrix.items():
        labels = {k for k in values} | {p for counts in values.values() for p in counts if not p.startswith("__")}
        f1s = []
        for label in sorted(labels):
            tp = values.get(label, {}).get(label, 0)
            fp = sum(counts.get(label, 0) for target, counts in values.items() if target != label)
            fn = sum(v for pred, v in values.get(label, {}).items() if pred != label)
            f1s.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0)
        metrics[node] = {"accuracy": correct[node] / total if total else None,
                         "macro_f1": sum(f1s) / len(f1s) if f1s else None,
                         "confusion": {k: dict(v) for k, v in values.items()}}
    return {"protocol_version": "jev-report-1", "dataset_sha256": run["dataset_sha256"],
            "split": run["split"], "requested": run["requested"], "completed": total,
            "unattempted": run["requested"] - total,
            "all_completed": total == run["requested"], "human_reviewed": all(r["human_reviewed"] for r in run["rows"]) if total else False,
            "sources": dict(source_counts), "actual_or_recorded_models": sorted(models),
            "is_live_accuracy_measurement": bool(total) and set(source_counts) == {"live"},
            "production_acceptance": False, "calibrated": False,
            "nodes": metrics, "final_action_accuracy": final_correct / total if total else None,
            "clarification_recall": passed_clarify / (passed_clarify + missed_clarify) if passed_clarify + missed_clarify else None,
            "redundant_clarification_rate": redundant_clarify / (redundant_clarify + true_pass) if redundant_clarify + true_pass else None,
            "dangerous_raw_suggestions": dangerous, "blocked_dangerous_suggestions": blocked,
            "live_http_attempts": real_calls, "charged_or_reserved_usd": str(billed),
            "observed_or_replayed_input_tokens": recorded_tokens,
            "total_ms": sum(times), "p50_ms": percentile(times, .5), "p95_ms": percentile(times, .95),
            "unavailable": dict(errors), "categories": dict(categories)}


def write_reports(run, output):
    import csv
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = summarize(run)
    (output / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Jev 独立评测报告", "", f"来源：{report['sources']}；实际/录制模型：{report['actual_or_recorded_models']}。",
             "Mock 为字面规则基线，Replay 为历史结果；均不代表本次真实 Jev 准确率。", "",
             f"数据：{report['completed']}/{report['requested']}，切分 {report['split']}；人工审核：{report['human_reviewed']}。",
             "未校准，不构成正式业务接入验收。", "", "| 节点 | 准确率 | macro-F1 |", "|---|---:|---:|"]
    for node, metric in report["nodes"].items():
        lines.append(f"| {node} | {metric['accuracy']} | {metric['macro_f1']} |")
    lines += ["", f"最终动作准确率：{report['final_action_accuracy']}。",
              f"必要澄清召回：{report['clarification_recall']}；冗余澄清率：{report['redundant_clarification_rate']}。",
              f"潜在危险原始建议：{report['dangerous_raw_suggestions']}；拦截：{report['blocked_dangerous_suggestions']}。",
              f"HTTP 尝试：{report['live_http_attempts']}；本轮已结算或保留费用：${report['charged_or_reserved_usd']}。",
              f"全流程 P50/P95：{report['p50_ms']} / {report['p95_ms']} ms。已尝试但失败的样本计入分母；未尝试 {report['unattempted']} 条，不完整运行不能视为整集结果。",
              f"错误：{report['unavailable']}。", "", "完整混淆矩阵、来源和数据哈希见 summary.json；逐项追踪见 run.json。"]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (output / "cases.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "group", "split", "category", "expected_action", "actual_action", "status", "reasons"])
        for row in run["rows"]:
            result = row["result"]
            writer.writerow([row["id"], row["group"], row["split"], row["category"], row["expected"]["final_action"],
                             result["final_action"], result["status"], "|".join(result["reasons"])])
    return report
