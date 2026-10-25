"""Export this local increment separately; never overwrite released contracts."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "docs/versions/V1-P8.2/contracts"


def export(kind="all"):
    from .app import create_app
    from .memory_schemas import MemoryContext, TurnRequest, TurnResult
    TARGET.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    if kind in {"all", "ai"}:
        with patch.dict(os.environ, {"AI_SERVICE_TOKEN":"export-placeholder-not-a-secret", "P3_ENGINE":"rules"}):
            ai = create_app(reader=object()).openapi()
        artifacts.update({"ai-openapi.json":ai,
                 "memory-context.schema.json":MemoryContext.model_json_schema(),
                 "ai-turn-request.schema.json":TurnRequest.model_json_schema(),
                 "ai-turn-response.schema.json":TurnResult.model_json_schema()})
    if kind in {"all", "backend"}:
        sys.path.insert(0, str(ROOT/"backend/server"))
        from sqlalchemy import create_engine
        with patch.dict(os.environ, {"DB_PASSWORD":"export-placeholder-not-a-secret"}), \
                patch("sqlalchemy.create_engine", return_value=create_engine("sqlite://")):
            from app.main import app
        from app.memory_schemas import Message, Reset, Response, Page, Recovery
        artifacts["backend-openapi.json"] = app.openapi()
        for name, model in {"public-message":Message, "public-reset":Reset,
                        "public-response":Response, "public-history":Page, "public-recovery":Recovery}.items():
            artifacts[name+".schema.json"] = model.model_json_schema()
    for name, value in artifacts.items():
        if name.endswith("openapi.json"):
            value["x-deployment-status"] = "local_source_contract_not_deployed"
            value["x-conversation-memory-protocol"] = "conversation-memory-1"
        (TARGET/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("Exported local memory contracts; no database or network connection.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["ai", "backend", "all"], default="all")
    export(parser.parse_args().kind)
