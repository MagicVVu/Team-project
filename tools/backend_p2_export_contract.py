"""Export local executable contracts, without a database or provider connection."""
import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('side', choices=('backend', 'agent'))
parser.add_argument('--stage', choices=('p2', 'p3', 'p4'), default='p2')
args = parser.parse_args()
side, stage = args.side, args.stage
if side == 'backend':
    from sqlalchemy import create_engine
    sys.path.insert(0, str(ROOT / 'backend/server'))
    os.environ.setdefault('DB_PASSWORD', 'isolated-contract-only')
    with patch('sqlalchemy.create_engine', return_value=create_engine('sqlite://')):
        from app.main import app
else:
    sys.path.insert(0, str(ROOT / 'agent'))
    os.environ['AI_SERVICE_TOKEN'] = 'synthetic-contract-only-internal-token'
    os.environ['P3_ENGINE'] = 'rules'
    from conversation.app import create_app
    app = create_app(engine=object(), reader=object())

schema = app.openapi()


def verify(value):
    if isinstance(value, dict):
        if '$ref' in value:
            assert value['$ref'].startswith('#/')
            target = schema
            for component in value['$ref'][2:].split('/'):
                target = target[component.replace('~1', '/').replace('~0', '~')]
        for member in value.values():
            verify(member)
    elif isinstance(value, list):
        for member in value:
            verify(member)


verify(schema)
path = ROOT / f'reports/backend-{stage}-{side}-openapi.json'
path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding='utf-8')
print(side, 'OpenAPI exported; all local references resolve')
