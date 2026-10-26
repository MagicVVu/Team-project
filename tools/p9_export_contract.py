"""Export the candidate contract without a database connection."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend/server'))
os.environ.setdefault('DB_PASSWORD', 'unused-export-placeholder')
with patch('sqlalchemy.create_engine', return_value=create_engine('sqlite://')):
    from app.main import app
value = app.openapi()
value['x-deployment-status'] = 'local_source_contract_not_deployed'
value['x-conversation-memory-protocol'] = 'conversation-memory-1'
path = ROOT/'docs/versions/V1-P9/backend-openapi.json'
path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('Candidate backend OpenAPI exported')
