"""Stricter field/state regrading of saved provider outputs; no new model calls."""
import json
import math
from decimal import Decimal
from pathlib import Path
from .generate import samples
from .run import NOW


def correct_fields(row,frame):
    draft=(frame.get("result") or {}).get("draft") or {}
    group=row["group_id"]; variant=int(row["id"].rsplit("-",1)[1])-1
    if draft:
        if draft.get("name")!="牛奶":return False
        if draft.get("action") in {"CONSUME","OPEN","MOVE","DISCARD"}:
            if draft.get("batch_id")!="b1" or draft.get("expected_version")!=4:return False
        quantities={"literal_consume":[1,2,"0.5",1,1,2],"discard_partial":[1,2,"0.5",1,1,1],
                    "add":[2,1,3,2,1,2],"manual_plan":[2,1,3,2,1,2],"correction_quantity":[2]*6}
        if group in quantities and (Decimal(draft.get("quantity","-1"))!=Decimal(str(quantities[group][variant])) or draft.get("unit")!="盒"):return False
        places={"whole_move":["冷藏室","厨房","餐边柜","冰箱上层","储物柜","书房"],
                "correction_location":["厨房","冰箱","餐边柜","储物柜","书房","冷藏室"],
                "add":["冰箱","厨房","储物柜","冰箱上层","厨房","餐边柜"]}
        if group in places and draft.get("location" if group=="add" else "to_location")!=places[group][variant]:return False
        if group=="opening":
            from datetime import timedelta
            expected=(NOW.date()-timedelta(days=variant in {0,2,4})).isoformat()
            if draft.get("opened_at")!=expected:return False
    if row["expected"]=="status":
        expected={"pending":"确认","committed":"执行成功","cancelled":"取消","unknown":"待核实"}[row["profile"]]
        if expected not in frame.get("reply",""):return False
    if row["profile"] in {"reference","multiple"} and row["group_id"] in {"pronoun_query","ordinal_query","quantity_location","dates_query"}:
        facts=(frame.get("result") or {}).get("facts") or []
        if facts and any(r["id"] != ("b2" if row["group_id"]=="ordinal_query" else "b1") for r in facts):return False
    return True


def summarize(path):
    value=json.loads(path.read_text(encoding="utf-8"))
    rows={row["id"]:row for row in samples()}
    results=[]
    for item in value["results"]:
        result={"id":item["id"],"group_id":item["group_id"],"split":item["split"],
            "passed":item["passed"] and correct_fields(rows[item["id"]],item.get("frame") or {}),
            "error_code":item.get("error_code") or (item.get("frame") or {}).get("error_code")}
        results.append(result)
    return dict(source_report=path.name,count=len(results),passed=sum(r["passed"] for r in results),
        success_rate=sum(r["passed"] for r in results)/len(results),
        p95_ms=value["p95_ms"],unnecessary_clarification_rate=value["unnecessary_clarification_rate"],
        max_model_calls=value["max_model_calls"],human_review_status="pending",results=results)


def main():
    root=Path(__file__).resolve().parents[3]/"reports/p84-dialogue"
    reports=[summarize(root/name) for name in ("deepseek-p83-baseline.json","deepseek-dev-final.json","deepseek-holdout.json","deepseek-holdout-regression.json")]
    output={"method":"Conjunctive field/state checks over immutable saved real-model outputs; failures never converted to passes",
        "holdout_policy":"First P8.4 holdout run retained; state routing fixes then regression on consumed holdout, not independent blind acceptance", "reports":reports,
        "human_naturalness_review":"pending","app_joint_acceptance":"not_run","production_database_p95":"not_measured"}
    (root/"evaluation-summary.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps([{k:v for k,v in r.items() if k!="results"} for r in reports],ensure_ascii=False))


if __name__=="__main__":main()
