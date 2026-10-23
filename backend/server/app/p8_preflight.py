"""Read-only P8 compatibility checks. No model calls, migrations or business writes."""
import asyncio
import json
import os

import httpx

from app.p7_preflight import check_http as p7_http


async def check_http(client, env):
    checks = await p7_http(client, env)
    checks.update(p8_routes=False, ai_p8_contract=False)
    placeholder = '00000000-0000-0000-0000-000000000000'
    routes = [
        ('/api/v1/agent/conversation-messages', 405),
        (f'/api/v1/agent/tasks/{placeholder}/chat-control', 405),
        (f'/api/v1/drafts/{placeholder}/execution-preview', 405),
        (f'/api/v1/households/{placeholder}/inventory-items/{placeholder}/planning-facts', 401),
        ('/internal/v1/planning/context', 401),
    ]
    try:
        checks['p8_routes'] = all([(await client.get('http://127.0.0.1:8000'+path)).status_code == status
                                   for path, status in routes])
        if checks['ai_service_url']:
            health = (await client.get('http://agent:8767/health')).json()
            spec = (await client.get('http://agent:8767/openapi.json')).json()
            checks['ai_p8_contract'] = (health.get('chat_policy_version') == 'p8-chat-1'
                and 'post' in spec['paths'].get('/agent/reply-resolution', {}))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        pass
    return checks


def check_database():
    from sqlalchemy import inspect, text
    from app.database import engine
    try:
        with engine.connect() as connection:
            versions = set(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
            tables = set(inspect(connection).get_table_names())
        return {'p8_migration': versions == {'20261023_0010'},
            'p8_tables': {'ai_conversation_bindings', 'ai_conversation_turns', 'inventory_planning_facts',
                'planning_fact_writes', 'draft_operations', 'draft_decisions', 'business_events'} <= tables}
    finally:
        engine.dispose()


async def run():
    async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
        checks = await check_http(client, os.environ)
    try:
        checks.update(check_database())
    except Exception:
        checks.update(p8_migration=False, p8_tables=False)
    print(json.dumps({'checks': checks, 'preflight_passed': all(checks.values()),
        'model_called': False, 'business_data_written': False, 'live_acceptance_verified': False}, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(run()))
