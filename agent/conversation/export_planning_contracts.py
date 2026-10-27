"""P8.3 exports are local artifacts; released snapshots remain immutable."""
import json
import os
from pathlib import Path
from unittest.mock import patch
from .app import create_app
from .schemas import AgentResult
from .memory_schemas import TurnResult
from .planning_schemas import BackendSnapshot, Provenance, Basis, ProductPlanning, RevalidationRequest


def export():
    root = Path(__file__).resolve().parents[2]/"docs/versions/V1-P8.3/contracts"
    root.mkdir(parents=True, exist_ok=True)
    with patch.dict(os.environ, {"AI_SERVICE_TOKEN":"export-placeholder", "P3_ENGINE":"rules"}):
        api = create_app(reader=object()).openapi()
    api["x-deployment-status"] = "local_source_contract_not_deployed"
    api["x-conversation-memory-protocol"] = "conversation-memory-1"
    artifacts = {"ai-openapi.json":api}
    for name, model in {"agent-result":AgentResult, "ai-turn-response":TurnResult, "backend-snapshot":BackendSnapshot,
                        "planning-provenance":Provenance, "planning-basis":Basis, "product-planning":ProductPlanning,
                        "revalidation-request":RevalidationRequest}.items():
        artifacts[name+".schema.json"] = model.model_json_schema()
    for name, value in artifacts.items():
        (root/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("P8.3 AI contracts exported without network, database or model calls.")


if __name__ == "__main__": export()
