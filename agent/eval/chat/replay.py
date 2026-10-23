"""Replay recorded synthetic model extraction against P8 and fixture inventory.

Never invokes a provider. This is separate evidence from the offline 150 cases.
"""
import argparse
import asyncio
import json
from pathlib import Path

from conversation.manager import Manager
from conversation.schemas import Message
from eval.conversation.run import Reader, SCOPE, NOW
from p2.knowledge import RuleCatalog
from v1.engines import parse_json_output


class RecordedEngine:
    def __init__(self, parsed): self.parsed, self.calls = parsed, 0
    async def extract(self, text):
        self.calls += 1
        return parse_json_output(json.dumps(self.parsed, ensure_ascii=False))


async def replay(value):
    rows = []
    for sample in value["rows"]:
        engine, reader = RecordedEngine(sample["parsed"]), Reader(sample["name"])
        before = reader.data.model_dump_json()
        result = await Manager(engine, reader, RuleCatalog.load(), now=lambda:NOW).handle(
            Message(text=sample["text"], request_id="p8-recorded-"+sample["id"]), SCOPE)
        checks = {"intent":result.intent == sample["intent"], "status":result.status == sample["status"],
            "original_text":result.original_text == sample["text"], "at_most_once":engine.calls <= 1,
            "zero_writes":not result.inventory_writes and not result.shopping_writes and reader.data.model_dump_json() == before}
        if result.draft:
            command = result.draft.model_dump(mode="json")
            checks["draft_identity"] = command["name"] == sample["name"] and command["action"] == sample["intent"]
            if sample["id"] == "add": checks["draft_fields"] = command["quantity"] == "2" and command["unit"] == "盒" and command["location"] == "冰箱上层"
            if sample["id"] == "move": checks["draft_fields"] = command["to_location"] == "储物柜" and command["expected_version"] == 4 and command["batch_id"] == "b1"
            if sample["id"] == "open": checks["draft_fields"] = command["opened_at"] == "2026-10-14" and command["expected_version"] == 4
            if sample["id"] == "discard": checks["draft_fields"] = command["discard_mode"] == "all" and command["quantity"] == "2" and result.quantity_source == "current_batch"
            if sample["id"] == "plan": checks["draft_fields"] = command["quantity"] == "2" and command["unit"] == "包"
        elif sample["id"] == "location":
            checks["fresh_fixture_fact"] = len(result.facts) == 1 and result.facts[0].id == "b1" and result.facts[0].location == reader.data.items[0].batches[0].location
        rows.append({"id":sample["id"], "passed":all(checks.values()), "checks":checks,
            "provider_extraction_seconds":sample["elapsed_seconds"], "result":result.model_dump(mode="json")})
    return {"provider_calls_during_replay":0, "inventory_source":"synthetic fixture only", "rows":rows,
        "passed":sum(row["passed"] for row in rows), "total":len(rows)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    recorded = json.loads(args.input.read_text(encoding="utf-8"))
    result = asyncio.run(replay(recorded))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed":result["passed"], "total":result["total"], "provider_calls_during_replay":0}))
    raise SystemExit(result["passed"] != result["total"])


if __name__ == "__main__": main()
