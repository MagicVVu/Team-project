"""The reserved adapter stays closed until its separate protocol is released."""
from uuid import uuid4
from unittest.mock import AsyncMock
from test_v09_execution import execution_state, headers
from app.routers import agent_gateway


def test_reference_adapter_is_unavailable_without_ai_or_writes(execution_state, monkeypatch):
    client, Session, ids = execution_state
    upstream = AsyncMock()
    monkeypatch.setattr(agent_gateway, "_call_ai", upstream)
    payload = dict(household_id=str(ids["home"]), text=" 它在哪里？ ", request_id="reserved",
                   source_task_id=str(uuid4()), source_revision=1, batch_id=str(ids["batch"]))
    endpoint = "/api/v1/agent/reference-messages"
    assert client.post(endpoint, json=payload).status_code == 401
    result = client.post(endpoint, json=payload, headers=headers())
    assert result.status_code == 503
    assert result.json()["detail"]["code"] == "TRUSTED_REFERENCE_ADAPTER_UNAVAILABLE"
    upstream.assert_not_called()
    from app.models import AITask, AIDraft
    with Session() as db:
        assert db.query(AITask).count() == db.query(AIDraft).count() == 0
