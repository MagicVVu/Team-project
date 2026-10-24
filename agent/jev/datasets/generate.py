"""Reproducible 100 expression families x 3 variants. Not human-reviewed."""
import hashlib
import json
from pathlib import Path

from jev.schemas import Intent, DecisionRequest

ROOT = Path(__file__).resolve().parent

# Five different expressions per scenario; all variants of one expression stay together.
SCENARIOS = [
    ("add", "ADD", "ADDED", ["刚买了两盒牛奶，放冰箱", "牛奶新购入两盒，放冰箱", "新增两盒牛奶到冰箱", "登记入库牛奶两盒，位置冰箱", "牛奶添加两盒，存在冰箱"]),
    ("consume", "CONSUME", "CONSUMED", ["牛奶喝掉一盒了", "牛奶用掉一盒", "牛奶消耗一盒", "牛奶减去一盒", "牛奶喝掉了1盒"]),
    ("finish", "CONSUME", "FINISHED", ["这批牛奶全部喝完了", "牛奶已经用完了", "牛奶都吃完了", "这一批牛奶喝完了", "牛奶全部用完了"]),
    ("move", "MOVE", "MOVED", ["把牛奶移到厨房", "牛奶移动到厨房", "牛奶挪到厨房", "整批牛奶移动去厨房", "请将牛奶移动到厨房"]),
    ("open", "OPEN", "OPENED", ["牛奶昨天开封了", "牛奶登记开封日期为昨天", "这批牛奶打开了", "牛奶已开封，日期昨天", "整批牛奶昨天打开了"]),
    ("discard", "DISCARD", "DISCARDED", ["牛奶倒掉一盒了", "丢弃一盒牛奶", "牛奶扔掉一盒", "牛奶报废一盒", "把一盒牛奶丢弃"]),
    ("plan", "PLAN_ADD", "NONE", ["采购清单加入一盒牛奶", "将一盒牛奶加到待购", "牛奶一盒放进采购清单", "清单添加牛奶一盒", "待购里登记一盒牛奶"]),
    ("inventory", "QUERY_INVENTORY", "NONE", ["牛奶还有多少", "牛奶库存多少", "牛奶剩多少", "牛奶是不是喝完了", "牛奶还有吗"]),
    ("location", "QUERY_LOCATION", "NONE", ["牛奶在哪", "牛奶放哪里", "牛奶在什么地方", "牛奶放在哪儿", "牛奶在哪个位置"]),
    ("risk", "QUERY_RISK", "NONE", ["牛奶过期了吗", "牛奶安全吗", "查牛奶保存条件", "牛奶临期了吗", "牛奶是否过期"]),
    ("consumption", "QUERY_CONSUMPTION", "NONE", ["牛奶消耗统计", "最近牛奶用了多少", "上周牛奶消耗多少", "查询牛奶消耗统计", "最近一周牛奶用了多少"]),
    ("forecast", "QUERY_FORECAST", "NONE", ["牛奶什么时候用完", "牛奶还能用几天", "牛奶多久用完", "预计牛奶什么时候喝完", "想知道牛奶还能用几天"]),
    ("purchase", "SUGGEST_PURCHASE", "NONE", ["牛奶要不要买", "牛奶需要补货吗", "牛奶该买吗", "这周牛奶还要买吗", "家里牛奶是否需要补货"]),
    ("location_items", "QUERY_LOCATION_ITEMS", "NONE", ["冰箱里有什么", "冰箱有哪些物品", "看看冰箱里有什么", "冰箱里面有哪些东西", "查冰箱有什么"]),
    ("overview", "QUERY_OVERVIEW", "NONE", ["今天有什么需要关注", "查看库存摘要", "家庭库存概览", "列出库存关注事项", "我想看库存摘要"]),
    ("negation", "QUERY_INVENTORY", "NONE", ["牛奶没喝完，查剩多少", "不要扣牛奶，先查询库存", "别把牛奶记成用完，查剩多少", "牛奶没有喝完，看看库存", "不要把牛奶用完，查询数量"]),
    ("future", "SUGGEST_PURCHASE", "NONE", ["明天准备买牛奶", "我打算买牛奶", "明天买牛奶", "计划买两盒牛奶", "准备买牛奶，还没买到"]),
    ("multiple", "UNKNOWN", "UNKNOWN", ["牛奶和面包各加一份", "牛奶移到厨房，然后丢弃面包", "牛奶喝掉一盒，再把面包移到厨房", "牛奶和洗衣液都用掉一份", "添加牛奶，顺便登记面包"]),
    ("ambiguous", "CONSUME", "CONSUMED", ["牛奶喝掉一盒了", "牛奶消耗一盒", "牛奶用掉一盒", "牛奶减去一盒", "牛奶吃掉一盒"]),
    ("missing", "CONSUME", "CONSUMED", ["牛奶喝掉一些", "牛奶消耗了一些", "牛奶用掉一些", "牛奶吃掉了一些", "牛奶减去一些"]),
]


def build_samples():
    samples = []
    for category_index, (category, intent, event, expressions) in enumerate(SCENARIOS):
        for family, expression in enumerate(expressions):
            group = f"g{category_index + 1:02}-{family + 1}"
            split = "dev" if family < 3 else "calibration" if family == 3 else "test"
            for variant, text in enumerate([expression, "麻烦一下，" + expression, "嗯，" + expression + "。"], 1):
                facts = {"known": True, "scope_valid": True, "task_status": "ready",
                    "version_current": True, "unit_compatible": True,
                    "capabilities": [i.value for i in Intent if i not in {Intent.UNKNOWN, Intent.UNSUPPORTED}],
                    "fields": {"name": "牛奶", "quantity": "2" if category == "add" else "1", "unit": "盒",
                               "location": "冰箱", "to_location": "厨房", "opened_at": "2026-10-22"},
                    "candidates": [{"id": "synthetic-c1", "name": "牛奶", "quantity": "3", "unit": "盒", "location": "冰箱", "version": 1}],
                    "selected_id": "synthetic-c1"}
                clarify, action = "PASS", "CONFIRM" if intent in {"ADD", "CONSUME", "OPEN", "MOVE", "DISCARD", "PLAN_ADD"} else "READ"
                if category == "ambiguous":
                    facts["candidates"].append({**facts["candidates"][0], "id": "synthetic-c2"})
                    facts["selected_id"] = None
                    clarify, action = "CLARIFY", "CLARIFY"
                if category == "missing":
                    facts["fields"]["quantity"] = None
                    clarify, action = "CLARIFY", "CLARIFY"
                if category == "multiple":
                    clarify, action = "CLARIFY", "CLARIFY"
                sample_id = group + f"-v{variant}"
                request = DecisionRequest.model_validate({"synthetic": True, "request_id": sample_id, "text": text,
                    "now": "2026-10-23T12:00:00+08:00", "facts": facts})
                samples.append({"id": sample_id, "group": group, "split": split, "category": category,
                    "human_reviewed": False, "request": request.model_dump(mode="json"),
                    "expected": {"intent_router": intent, "event_classifier": event,
                                 "clarification_gate": clarify, "action_gate": action, "final_action": action}})
    return samples


def main():
    from jev.evaluation import Sample
    samples = [Sample.model_validate(s).model_dump(mode="json") for s in build_samples()]
    content = "".join(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n" for s in samples)
    (ROOT / "samples.jsonl").write_text(content, encoding="utf-8", newline="\n")
    manifest = {"version": "jev-synthetic-1", "count": 300, "groups": 100,
                "dev": 180, "calibration": 60, "test": 60, "categories": 20,
                "source": "AI-authored synthetic expressions and fixture facts", "human_reviewed": False,
                "real_audio": False, "split_rule": "expression families 1-3 dev, 4 calibration, 5 test; variants never cross splits",
                "limitations": "Same product and shared vocabulary; template generalization is limited. Not representative production accuracy.",
                "sha256": hashlib.sha256(content.encode()).hexdigest()}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "example.json").write_text(json.dumps(samples[0]["request"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"samples": len(samples), "groups": manifest["groups"]}))


if __name__ == "__main__":
    main()
