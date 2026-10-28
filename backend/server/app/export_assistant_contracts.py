"""Export local OpenAPI without connecting to a configured database."""
import json
import os
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine


def export():
    with patch.dict(os.environ, {"DB_PASSWORD": "export-placeholder-not-a-credential"}), \
            patch("sqlalchemy.create_engine", return_value=create_engine("sqlite://")):
        from app.main import app
    target = Path(__file__).resolve().parents[3]/"docs/versions/V1-P8.1/contracts"
    target.mkdir(parents=True, exist_ok=True)
    api = app.openapi()
    api["x-deployment-status"] = "local_source_contract"
    (target/"backend-openapi.json").write_text(json.dumps(api, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__": export()
