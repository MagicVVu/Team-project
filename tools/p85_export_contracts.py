"""Local schema export only. No DB connection, model calls, or server access."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"agent"))
from conversation.p85.app import create_app
from conversation.p85 import schemas
from conversation.p85.archive import P85StoredTurn
from conversation.engines import RuleEngine


class UnusedReader:
    """OpenAPI generation never instantiates a runtime inventory fixture."""
    pass


def main():
    os.environ.setdefault("AI_SERVICE_TOKEN", "schema-export-only-not-a-runtime-token")
    directory = ROOT/"docs/versions/V1-P8.5/contracts"
    directory.mkdir(parents=True, exist_ok=True)
    api = create_app(engine=RuleEngine(), reader=UnusedReader()).openapi()
    api.update({"x-deployment-status": "local_candidate_not_deployed", "x-conversation-dialogue-protocol": "p85-dialogue-1",
                "x-backend-adapter-status": "contract_only_not_implemented"})
    models = {"understand-request": schemas.P85Request, "understand-response": schemas.P85Understood,
        "resolve-request": schemas.P85ResolveRequest, "resolve-response": schemas.P85Resolved,
        "respond-request": schemas.P85RespondRequest, "respond-response": schemas.P85Responded,
        "archive": schemas.P85Archive, "memory-delta": schemas.P85MemoryDelta,
        "context": schemas.P85Request.model_fields["context"].annotation, "stored-turn": P85StoredTurn}
    values = {"ai-openapi.json": api}
    values.update({name+".schema.json": model.model_json_schema() for name, model in models.items()})
    for name, value in values.items():
        (directory/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"contracts": len(values), "model_called": False, "database_opened": False}))


if __name__ == "__main__": main()
