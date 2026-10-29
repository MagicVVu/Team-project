"""Export step-one backend contracts without changing historical AI snapshots."""
import json
import argparse
import os
import sys
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/server"))
os.environ.setdefault("DB_PASSWORD", "unused-export-placeholder")
with patch("sqlalchemy.create_engine", return_value=create_engine("sqlite://")):
    from app.main import app
    from app.memory_schemas import Response, Message, Page, Recovery
    from app.services.dialogue import P85Request, P85ResolveRequest, P85RespondRequest, P85Resolution
    from app.dialogue_schemas import Understanding, Expression

parser = argparse.ArgumentParser()
parser.add_argument("--output", default="reports/p85-backend-adapter/contracts")
arguments = parser.parse_args()
directory = ROOT / arguments.output
directory.mkdir(parents=True, exist_ok=True)
api = app.openapi()
api.update({"x-deployment-status": "local_source_not_deployed",
            "x-p85-adapter-status": "archive_and_stage_persistence_implemented",
            "x-supported-dialogue-protocols": ["p84-dialogue-1", "p85-dialogue-1"]})
values = {"backend-openapi.json": api}
for name, model in {"public-response": Response, "public-message": Message,
                    "conversation-page": Page, "recovery": Recovery,
                    "understand-request": P85Request, "understand-response": Understanding,
                    "resolve-request": P85ResolveRequest, "resolve-response": P85Resolution,
                    "respond-request": P85RespondRequest, "respond-response": Expression}.items():
    values[name + ".schema.json"] = model.model_json_schema()
for name, value in values.items():
    (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"contracts": len(values), "database_connected": False, "deployed": False}))
