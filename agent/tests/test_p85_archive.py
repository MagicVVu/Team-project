from datetime import timedelta
import pytest
from p0.domain import DomainError
from conversation.p85.archive import build_archive, P85StoredTurn
from conversation.p85.render import render
from conversation.p85.schemas import P85Resolved
from test_session_memory import context, NOW


def stored(i=0, **changes):
    ctx = context()
    value = dict(scope=ctx.scope, conversation_id=ctx.conversation_id, revision=0, request_id=str(i),
                 text="查一下牛奶", reply="历史回复", completed_at=NOW-timedelta(seconds=i+1),
                 subjects=[{"name": "牛奶", "quote": "牛奶"}])
    value.update(changes)
    return P85StoredTurn(**value)


def test_history_mapping_filters_old_and_incomplete_and_discloses_unread_pages():
    ctx = context()
    archive = build_archive(ctx, [stored(), stored(1, completed=False), stored(2, completed_at=NOW-timedelta(days=30))], source_has_more=True)
    assert len(archive.episodes) == 1 and archive.has_more
    assert archive.episodes[0].text == "查一下牛奶"
    assert build_archive(ctx, [stored()]).episodes[0].memory_id == archive.episodes[0].memory_id


@pytest.mark.parametrize("kind", ["scope", "session", "future", "revision", "request"])
def test_mapping_refuses_mixed_scope_or_conflicting_snapshots(kind):
    turn = stored().model_dump(mode="json")
    if kind == "scope": turn["scope"]["household_id"] = "other"
    if kind == "session": turn["conversation_id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    if kind == "future": turn["completed_at"] = (NOW+timedelta(seconds=1)).isoformat()
    if kind == "revision": turn["revision"] = 1
    if kind == "request": turn["reply"] = "不同内容"
    with pytest.raises(DomainError): build_archive(context(), [stored(), turn])


def test_mapping_deduplicates_identical_requests_and_bounds_archive():
    assert len(build_archive(context(), [stored(), stored()]).episodes) == 1
    archive = build_archive(context(), [stored(i) for i in range(110)])
    assert len(archive.episodes) == 100 and archive.has_more


@pytest.mark.parametrize("expression", [
    {"fact_order": ["f0"], "closing": "review_draft"},
    {"fact_order": ["f0"], "opening": "check"},
    {"fact_order": ["f0"], "closing": "choose_batch"},
    {"fact_order": ["f0", "f0"]},
    {"fact_order": ["f0"], "opening": "已经执行成功"},
])
def test_expression_cannot_change_status_add_claims_or_lose_evidence(expression):
    frame = P85Resolved(original_text="它在哪", kind="needs_input", reply="请选物品", facts={"f0": "请选物品"})
    with pytest.raises(ValueError): render(expression, frame)


def test_new_evaluation_uses_group_isolation_and_six_turn_scenarios():
    from eval.p85.generate import scenarios
    rows = scenarios()
    assert len(rows) == 40 and sum(len(r["turns"]) for r in rows) == 240
    assert sum(len(r["turns"]) for r in rows if r["split"] == "dev") == 144
    assert {r["group_id"] for r in rows if r["split"] == "dev"}.isdisjoint({r["group_id"] for r in rows if r["split"] == "holdout"})
    assert all(r["synthetic"] and r["source"] and r["human_review_status"] == "pending" for r in rows)
