"""P1 compatibility: unreleased actions must never mutate business data."""
import pytest
from sqlalchemy import func, select
from test_v09_execution import execution_state, seed_draft, body, post, headers, url
from app.models import InventoryItem
from app.execution_models import BusinessEvent, DraftOperation


@pytest.mark.parametrize("action", ["OPEN", "DISCARD"])
def test_unreleased_actions_are_closed(execution_state, action):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids, action)
    caps = client.get("/api/v1/agent/execution-capabilities", headers=headers()).json()
    assert caps["actions"][action] is False
    assert client.get(url(draft, "execution"), headers=headers()).json()["status"] == "unavailable"
    result = post(client, draft, body())
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "ACTION_NOT_EXECUTABLE"
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.get(InventoryItem, ids["batch"]).version == 1
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 0
        assert db.scalar(select(func.count()).select_from(DraftOperation)) == 0
