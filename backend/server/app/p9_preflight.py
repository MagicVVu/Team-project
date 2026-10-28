"""P9 read-only production checks; no business writes or provider calls."""
import asyncio
import json
import os
import httpx
from sqlalchemy import inspect, text
from app.database import engine
from app.p8_preflight import check_http
from app.routers.draft_execution import capabilities


async def run():
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        checks = await check_http(client, os.environ)
    with engine.connect() as db:
        checks['p9_migration'] = set(db.execute(text('SELECT version_num FROM alembic_version')).scalars()) == {'20261026_0011'}
        tables = set(inspect(db).get_table_names())
        checks['p9_tables'] = {'products','product_batches','mutation_receipts','business_events'} <= tables
        columns = {c['name'] for c in inspect(db).get_columns('business_events')}
        checks['p9_event_columns'] = {'request_id','related_event_id','product_id','created_at'} <= columns
    caps = capabilities(None)
    checks['automatic_commit_closed'] = caps['automatic_planning_commit'] is False and caps['manual_plan_only'] is True
    checks['p9_metadata'] = caps['maintenance_release'] == 'V1-P9'
    print(json.dumps({'checks':checks,'preflight_passed':all(checks.values()),
        'model_called':False,'business_data_written':False,'live_acceptance_verified':False},sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(run()))
