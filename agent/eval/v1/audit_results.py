"""Independently audit saved outputs; no model reruns and no report overwrites."""
from decimal import Decimal
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def expected_command(sample, resumed=False):
    spec=sample["expected"].get("draft",{})
    intent=sample["expected"]["intent"]
    action=spec.get("action", "PLAN_ADD" if intent=="SUGGEST_PURCHASE" else intent)
    common={"action":action,"name":sample["fixture"]["name"]}
    if action in {"ADD","CONSUME","PLAN_ADD","DISCARD"}:
        quantity="1" if resumed else spec.get("quantity")
        # A resumed single recommendation keeps the labelled target shortfall.
        if resumed and intent=="SUGGEST_PURCHASE": quantity="1"
        # These frozen labelled scenarios explicitly report a whole batch finished.
        if resumed and sample["group"] in {"v1-scene-27","v1-scene-28"}: quantity="2"
        if quantity is None: return None
        common.update(quantity=quantity,unit=sample["fixture"]["unit"])
    if action=="ADD":
        common.update(location=None,purchased_at=None,label_expiry=None)
    if action in {"CONSUME","OPEN","MOVE","DISCARD"}:
        common.update(batch_id="b1",expected_version=4)
    if action=="OPEN": common["opened_at"]="2026-10-15" if resumed else spec["opened_at"]
    if action=="MOVE": common["to_location"]=spec["to_location"]
    if action=="DISCARD": common["discard_mode"]=spec.get("discard_mode","partial")
    return common

def audit_report(path):
    from .fixtures import fixture
    report=json.loads(path.read_text(encoding="utf-8"))
    samples={r["id"]:r for r in (json.loads(line) for line in (ROOT/"samples.jsonl").read_text(encoding="utf-8").splitlines())}
    rows=[]
    for row in report["rows"]:
        sample=samples[row["id"]]
        source=fixture(**sample["fixture"])
        facts={b.id:b.model_dump(mode="json") for i in source.items for b in i.batches}
        checks={}
        for label,result in (("initial",row["result"]),("continuation",row.get("continuation"))):
            if result is None: continue
            command=result["draft"]
            if command is not None:
                expected=expected_command(sample,resumed=label=="continuation")
                checks[label+"_all_command_fields"]=expected is not None and command==expected
            checks[label+"_facts"]=all(
                b["id"] in facts and all(facts[b["id"]].get(k)==v for k,v in b.items())
                for b in result["facts"])
            checks[label+"_candidate_facts"]=all(
                b["id"] in facts and all(facts[b["id"]].get(k)==v for k,v in b.items())
                for b in result["candidates"])
        rows.append({"id":row["id"],"checks":checks})
    return {"source_report":path.relative_to(ROOT).as_posix(),"all_rows_passed":all(all(r["checks"].values()) for r in rows),
        "initial_drafts":sum("initial_all_command_fields" in r["checks"] for r in rows),
        "continuation_drafts":sum("continuation_all_command_fields" in r["checks"] for r in rows),"rows":rows}

def main():
    paths=[]
    for engine in ("rules","deepseek"):
        for split in ("dev","test"):
            paths.append(max((ROOT/"results").glob(f"{engine}-{split}-*.json")))
    audits=[audit_report(p) for p in paths]
    out=ROOT/"results"/"full-field-audit-v2.json"
    if out.exists(): raise SystemExit("Audit already exists; do not overwrite")
    out.write_text(json.dumps({"audits":audits,"all_passed":all(r["all_rows_passed"] for r in audits)},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"all_passed":all(r["all_rows_passed"] for r in audits),"summaries":[{k:v for k,v in r.items() if k!="rows"} for r in audits]}))
if __name__=="__main__": main()
