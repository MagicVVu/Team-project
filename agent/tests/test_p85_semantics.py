"""Regression cases discovered in the FIRST holdout; that set is now consumed."""
from decimal import Decimal
import pytest
from conversation.p85 import flow
from conversation.p85.schemas import P85Request, P85ResolveRequest
from test_conversation import service, reference, run, SCOPE
from test_session_memory import context
from test_p85_memory import request, resolve_request, episode
from eval.dialogue.run import fixture, SCOPE as EVAL_SCOPE


def test_provider_history_name_is_bound_only_after_fresh_identity_check():
    owner, _, reader = service()
    req = request("现在帮我登记消耗两盒吧", ctx=context(reference=reference()), episodes=[])
    plan = {"speech_act": "request", "action": "CONSUME", "selector": {"name": "牛奶"},
            "fields": {"quantity": {"value": "2", "quote": "两盒"}, "unit": {"value": "盒", "quote": "两盒"}}}
    frame = run(flow.resolve(owner, resolve_request(req, plan), SCOPE))
    assert frame.result["draft"]["batch_id"] == "b1" and frame.original_text == req.text
    assert frame.result["object_source"] == "trusted_reference" and reader.batch_reads == 1
    reader.data.items[0].batches[0].name = "鸡蛋"
    frame = run(flow.resolve(owner, resolve_request(req, plan), SCOPE))
    assert frame.error_code == "REFERENCE_IDENTITY_CHANGED" and frame.result is None


def test_current_pronoun_is_not_retargeted_to_a_social_episode():
    owner, _, _ = service()
    old = episode("social", text="先说点厨房整理心得", subjects=[], reference=None)
    req = request("把它移到厨房", ctx=context(reference=reference()), episodes=[old])
    plan = {"speech_act": "request", "action": "MOVE", "selector": {"use_reference": True}, "memory_id": "social",
            "fields": {"to_location": {"value": "厨房", "quote": "厨房"}}}
    frame = run(flow.resolve(owner, resolve_request(req, plan), SCOPE))
    assert frame.result["draft"]["batch_id"] == "b1"
    req = req.model_copy(update={"text": "把之前的那个移到厨房"})
    frame = run(flow.resolve(owner, resolve_request(req, plan), SCOPE))
    assert frame.error_code == "MEMORY_OBJECT_RESELECT_REQUIRED"


def test_real_time_query_is_not_replaced_by_historical_recall():
    owner, _, reader = service()
    reader.data.items[0].batches[0].quantity = Decimal("9")
    req = request("前面提到的牛奶，现在的数量和位置呢")
    frame = run(flow.resolve(owner, resolve_request(req, {"speech_act": "recall", "memory_id": "old-milk",
        "reads": [{"kind": "quantity"}, {"kind": "location"}]}), SCOPE))
    assert frame.result["facts"][0]["quantity"] == "9" and reader.batch_reads == 1


@pytest.mark.parametrize("text", ["它昨天开封，帮我记一下", "这批今天开封", "这一批2026-10-14开封，记录一下"])
def test_explicit_opening_is_not_new_inventory_and_needs_no_model(text):
    owner, engine, _ = service()
    req = request(text, ctx=context(reference=reference()), episodes=[])
    understood = run(flow.understand(owner, req, SCOPE))
    frame = run(flow.resolve(owner, resolve_request(req, understood.plan), SCOPE))
    assert understood.understanding_calls == engine.calls == 0
    assert frame.result["draft"]["action"] == "OPEN" and "quantity" not in frame.result["draft"]


@pytest.mark.parametrize("action,text,value", [("OPEN", "说错了，应该是今天开封", "2026-10-15"),
                                               ("MOVE", "还是挪到储物柜吧", "储物柜")])
def test_clear_date_and_location_corrections_zero_model(action, text, value):
    owner, ctx, _ = fixture("move_pending" if action == "MOVE" else "pending", None)
    if action == "OPEN":
        from p1.domain import make_draft, parse_date
        from p1.schemas import Parsed
        command, preview = make_draft(Parsed(intent="OPEN", name="牛奶", opened_at="昨天"), owner.reader.data.items[0].batches[0],
                                      {"opened_at": parse_date("昨天", owner.now(), "Asia/Shanghai")})
        ctx.active.task.result.draft = command
        ctx.active.task.result.preview = preview
        ctx.tasks[0].action = "OPEN"
    req = request(text, ctx=ctx, episodes=[])
    understood = run(flow.understand(owner, req, EVAL_SCOPE))
    frame = run(flow.resolve(owner, resolve_request(req, understood.plan), EVAL_SCOPE))
    assert understood.understanding_calls == 0 and frame.kind == "edit"
    assert frame.result["draft"]["to_location" if action == "MOVE" else "opened_at"] == value


def test_half_hypothesis_uses_current_stock_but_never_creates_consumption():
    owner, engine, reader = service()
    reader.data.items[0].batches[0].quantity = Decimal("6")
    req = request("如果我喝掉一半会怎么样，我只是问问", ctx=context(reference=reference()), episodes=[])
    plan = {"speech_act": "hypothesis", "amount_mode": "half", "reads": [{"kind": "consumption"}], "selector": {"use_reference": True}}
    frame = run(flow.resolve(owner, resolve_request(req, plan), SCOPE))
    assert not frame.result.get("draft") and frame.result["status"] == "answered"
    assert "3 盒" in frame.reply and "仅作假设" in frame.reply and "没有生成或执行变更" in frame.reply
    assert reader.data.items[0].batches[0].quantity == 6 and engine.calls == 0


def test_no_real_candidates_never_means_pick_first_of_inventory():
    owner, ctx, _ = fixture("pending", None)
    req = request("还是两盒吧", ctx=ctx, episodes=[])
    plan = {"speech_act": "correction", "selector": {"choice_index": 0, "use_reference": True},
            "fields": {"quantity": {"value": "2", "quote": "两盒"}, "unit": {"value": "盒", "quote": "两盒"}}}
    frame = run(flow.resolve(owner, resolve_request(req, plan), EVAL_SCOPE))
    assert frame.kind == "edit" and frame.result["draft"]["batch_id"] == "b1"
    req = req.model_copy(update={"text": "第二个，还是两盒吧"})
    frame = run(flow.resolve(owner, resolve_request(req, plan), EVAL_SCOPE))
    assert frame.error_code == "INVALID_CANDIDATE" and frame.result is None


def test_household_discussion_can_be_free_prose_and_suggest_short_breaks():
    owner, engine, reader = service()
    req = request("整理得好累，怎么轻松点", episodes=[])
    prose = "听起来挺累的。可以先休息5分钟，再从常用的台面开始；不用急着整理完。"
    frame = run(flow.resolve(owner, resolve_request(req, {"speech_act": "discuss", "social_reply": prose}), SCOPE))
    assert frame.reply == prose and not frame.expression_required and frame.result is None
    assert reader.batch_reads == reader.searches == engine.calls == 0


@pytest.mark.parametrize("prose", ["牛奶还剩5盒", "我已经帮你移动到厨房", "记得你上次说喜欢喝牛奶", "牛奶在冰箱里", "这盒牛奶还能吃", "帮你写入了", "操作成功"])
def test_free_prose_never_becomes_business_or_personal_memory_claims(prose):
    from conversation.p85.prose import household_prose
    assert household_prose(prose) is None
    owner, _, _ = service()
    req = request("先聊聊整理", episodes=[])
    frame = run(flow.resolve(owner, resolve_request(req, {"speech_act": "discuss", "social_reply": prose}), SCOPE))
    assert frame.reply != prose and frame.result is None


def test_missing_history_does_not_fabricate_remembering():
    owner, _, _ = service()
    req = request("还记得我之前说过什么吗", episodes=[])
    frame = run(flow.resolve(owner, resolve_request(req, {"speech_act": "social", "social_reply": "记得你之前喜欢喝牛奶"}), SCOPE))
    assert frame.error_code == "MEMORY_UNAVAILABLE" and "没有" in frame.reply


def test_model_index_requires_literal_ordinal_or_live_location_disambiguation():
    owner, _, _ = service(multiple=True)
    req = request("牛奶还有多少", ctx=context(choices=[reference(), reference(batch_id="b2")]), episodes=[])
    plan = {"speech_act": "question", "selector": {"choice_index": 0}, "reads": [{"kind": "quantity"}]}
    frame = run(flow.resolve(owner, resolve_request(req, plan), SCOPE))
    assert frame.error_code == "CANDIDATE_SELECTION_UNGROUNDED" and frame.result is None
    req = req.model_copy(update={"text": "厨房那盒在哪里"})
    plan["selector"] = {"choice_index": 0, "location": "厨房"}
    frame = run(flow.resolve(owner, resolve_request(req, plan), SCOPE))
    assert frame.result["facts"][0]["id"] == "b2"


def test_p85_health_probe_does_not_accept_the_p84_runtime():
    from conversation.p85.health import check
    from conversation.p85.app import Profile
    body = {**Profile.health, "status": "ok", "inventory_writes": False, "shopping_writes": False}
    assert check(body)
    assert not check({**body, "maintenance_release": "V1-P8.4"})


@pytest.mark.parametrize("text", [
    "可以先从一个抽屉开始，给常用物品找固定位置。",
    "别急着一次全做完，不妨给自己10–15分钟，只收拾一个小区域。",
    "可以先检查标签，把明显过期的东西单独放，再整理常用物品。",
    "可以给常用东西留一个“回家就放这儿”的位置，用完归位。",
])
def test_ordinary_organizing_advice_is_not_inventory_facts(text):
    from conversation.p85.prose import household_prose
    assert household_prose(text) == text


@pytest.mark.parametrize("text", ["牛奶昨天开封", "牛奶过期了，可以清理", "牛奶有三个", "现在有一个苹果", "已经替你取消了"])
def test_advice_exceptions_do_not_authorize_real_stock_or_event_claims(text):
    from conversation.p85.prose import household_prose
    assert household_prose(text) is None
