"""Local repair contracts; old stage snapshots and release labels stay intact."""
import json
import os
from pathlib import Path
from unittest.mock import patch
from .app import create_app
from .schemas import AgentResult, ProcurementSource, Recommendation
from review.rules import candidates, Approval
from p2.knowledge import RuleCatalog


def export():
    target = Path(__file__).resolve().parents[2]/"docs/versions/V1-P8.1/contracts"
    target.mkdir(parents=True, exist_ok=True)
    with patch.dict(os.environ, {"AI_SERVICE_TOKEN": "local-contract-not-a-credential", "P3_ENGINE": "rules"}):
        api = create_app(reader=object()).openapi()
    api["x-deployment-status"] = "local_source_contract"
    documents = {"ai-openapi.json": api, "agent-result.schema.json": AgentResult.model_json_schema(),
        "recommendation.schema.json": Recommendation.model_json_schema(),
        "procurement-source.schema.json": ProcurementSource.model_json_schema(),
        "rule-approval.schema.json": Approval.model_json_schema(),
        "rule-review-candidates.json": candidates(RuleCatalog.load())}
    for name, value in documents.items():
        (target/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__": export()
