"""Export existing backend source contract; no P8.5 backend support is implied."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"backend/server"))
os.environ.setdefault("DB_PASSWORD", "unused-export-placeholder")
with patch("sqlalchemy.create_engine", return_value=create_engine("sqlite://")):
    from app.main import app
    from app.memory_schemas import Response, Message, Page, Recovery
directory = ROOT/"docs/versions/V1-P8.5/contracts"
directory.mkdir(parents=True, exist_ok=True)
api = app.openapi()
api.update({"x-deployment-status": "local_existing_backend_source_not_reverified_on_server",
            "x-p85-adapter-status": "not_implemented", "x-conversation-dialogue-protocol": "p84-dialogue-1"})
values = {"backend-openapi.json": api}
for name, model in {"public-response": Response, "public-message": Message, "conversation-page": Page, "recovery": Recovery}.items():
    values[name+".schema.json"] = model.model_json_schema()
for name, value in values.items():
    (directory/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"contracts": len(values), "backend_changed": False, "database_connected": False}))
