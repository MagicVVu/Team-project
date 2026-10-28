"""Export the candidate backend contract without connecting to any database."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/server'))
os.environ.setdefault('DB_PASSWORD', 'schema-export-unused-no-connection')
from app.main import app

destination = ROOT / 'reports/backend-ai-alignment/backend-openapi.json'
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(destination)
