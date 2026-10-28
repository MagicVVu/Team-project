"""P8.5 compiles memory selections into the unchanged P8.4 read/draft path."""
import asyncio
import copy
import re
from decimal import Decimal

from p0.domain import DomainError, normalize_unit
from p0.engines import EngineError
from p0.text import number, NUMBER_PATTERN, UNIT_PATTERN
from p1.domain import guard
from p1.tools import check_scope
from .. import dialogue as previous
from ..dialogue_schemas import ResolveRequest, Plan, Read
from .schemas import P85Plan, P85Understood, P85Resolved, P85Responded
from .memory import prepare, delta
from . import engine, render
from .prose import household_prose, fallback

ORDINAL = re.compile(r"(?:请|麻烦|帮我|请帮我)?(?:查下|查询|核对|看看|查一下)?第([一二两三四五六七八九十0-9]+)(?:个|批)(?:的)?(?:(?:数量|余量|还有多少|剩多少)(?:帮我核对下|帮我查一下)?|在哪里|在哪|在哪儿|在什么地方|位置)?[。！？?!]?")
QUANTITY = re.compile(r"(?:请|麻烦|帮我)?(?:查下|查询|核对|看看|查一下)?(?:它|这一批|这批|那个)(?:的)?(?:数量|余量|还有多少|剩多少|还剩多少|还剩几盒)(?:呢|吧)?[。！？?!]?")
HOLD = re.compile(r"(?:先别执行|先不执行|不要执行|先别改|先不改)(?:[，, ]*(?:我)?(?:只是|先)?(?:核对|问问|看看)(?:一下)?)?[。！？?!]?")
CORRECTION = re.compile(r"(?:刚才说错了[，, ]*)?(?:还是|改成|改为|应该是)("+NUMBER_PATTERN+r")\s*("+UNIT_PATTERN+r")?(?:吧|好了)?[。！？?!]?")
OPEN = re.compile(r"(?:它|这批|这一批|那批)?(今天|昨天|\d{4}-\d{2}-\d{2})开封(?:了)?(?:[，, ]*(?:请)?(?:帮我)?(?:记一下|登记一下|记录一下))?[。！？?!]?")
OPEN_CORRECTION = re.compile(r"(?:说错了[，, ]*)?(?:还是|应该是|改为|改成)(今天|昨天|\d{4}-\d{2}-\d{2})开封[。！？?!]?")
MOVE_CORRECTION = re.compile(r"(?:不对[，, ]*)?(?:还是|改为|改成)(?:挪到|移到|放到)([^，,。！？?!]{1,100}?)(?:吧)?[。！？?!]?")
HISTORICAL = re.compile(r"之前|以前|先前|刚才的|上次|回到|最开始|一开始|开头|最早|刚开始|前面提到|接着.*话题")


def literal_plan(body):
    text = body.text.strip()
    ctx = body.context
    if HOLD.fullmatch(text):
        return P85Plan(speech_act="negation", social_reply="可以，先核对你的想法。草稿仍需你正式确认，聊天不会触发执行。")
    match = ORDINAL.fullmatch(text)
    if match and ctx.choices:
        n = number(match[1])
        if n is not None and n == int(n) and n >= 1:
            kind = "quantity" if re.search(r"数量|余量|多少", text) else "location"
            selecting = ctx.active and ctx.active.task.status == "needs_clarification"
            return P85Plan(speech_act="supplement" if selecting else "question",
                           selector={"choice_index": int(n)-1}, reads=[] if selecting else [{"kind": kind}])
    if QUANTITY.fullmatch(text):
        return P85Plan(speech_act="question", selector={"use_reference": True}, reads=[{"kind": "quantity"}])
    active = ctx.active.task if ctx.active else None
    command = active.result.draft if active and active.result else None
    if match := OPEN.fullmatch(text):
        return P85Plan(speech_act="request", action="OPEN", write_count=1, selector={"use_reference": True},
                       fields={"opened_at": {"value": match[1], "quote": text}})
    if command and active.status == "needs_confirmation":
        if command.action == "OPEN" and (match := OPEN_CORRECTION.fullmatch(text)):
            return P85Plan(speech_act="correction", fields={"opened_at": {"value": match[1], "quote": text}})
        if command.action == "MOVE" and (match := MOVE_CORRECTION.fullmatch(text)):
            return P85Plan(speech_act="correction", fields={"to_location": {"value": match[1], "quote": text}})
    match = CORRECTION.fullmatch(text)
    if match and ctx.active and ctx.active.task.status == "needs_confirmation":
        quantity = number(match[1])
        if quantity is not None:
            fields = {"quantity": {"value": str(quantity), "quote": text}}
            if match[2]: fields["unit"] = {"value": normalize_unit(match[2]), "quote": text}
            return P85Plan(speech_act="correction", fields=fields)
    plan = previous.literal_plan(body)
    return P85Plan(**plan.model_dump()) if plan else None


async def understand(owner, body, scope):
    ctx, episodes, use = prepare(owner, body, scope)
    if guard(body.text):
        plan, calls = P85Plan(speech_act="negation"), 0
    elif plan := literal_plan(body.model_copy(update={"context": ctx})):
        calls = 0
    else:
        async with asyncio.timeout(body.remaining_seconds):
            method = getattr(owner.engine, "p85_understand", None)
            value = await method(body.text, ctx, episodes, use) if method else await engine.understand(owner, body, ctx, episodes, use)
            plan = P85Plan.model_validate(value)
        calls = 1
    if plan.memory_id and plan.memory_id not in use.selected_ids:
        raise EngineError("P85_UNKNOWN_MEMORY_SELECTION")
    return P85Understood(original_text=body.text, plan=plan, context_revision=ctx.revision,
                         understanding_calls=calls, memory=use)


def problem(body, use, code, reply):
    return P85Resolved(original_text=body.text, kind="needs_input", reply=reply,
                       facts={"f0": reply}, error_code=code, memory=use, expression_required=False,
                       filled_fields={k: v.value for k, v in body.plan.fields.items() if v.quote and v.quote in body.text})


async def resolve(owner, body, scope):
    ctx, episodes, use = prepare(owner, body, scope)
    if body.plan_context_revision != ctx.revision:
        return problem(body, use, "CONVERSATION_REVISION_CONFLICT", "会话已更新，请刷新原任务后继续。")
    plan = body.plan
    normalizations = use.summary["plan_normalizations"] = []
    if (plan.speech_act in {"social", "discuss"} and re.search(r"还记得|之前.*说|聊过什么|我.*说过", body.text)
            and not ctx.history and not episodes):
        return problem(body, use, "MEMORY_UNAVAILABLE", "当前没有覆盖这段讨论的可靠记录，请告诉我你想接着聊哪件事。")
    # Normalize contradictions using only already-attested bindings. Never
    # synthesize user text or choose the first of real candidates.
    if plan.speech_act == "recall" and plan.reads and re.search(r"现在|数量|位置|还剩|在哪|多少", body.text):
        plan = plan.model_copy(update={"speech_act": "question"})
        normalizations.append("current_fact_question")
    if (plan.selector.name and plan.selector.name not in body.text and ctx.reference
            and plan.selector.choice_index is None):
        # P8.4 then verifies this name against the freshly-read referenced row.
        plan = plan.model_copy(update={"selector": plan.selector.model_copy(update={"use_reference": True})})
        normalizations.append("name_checked_against_current_reference")
    if (plan.selector.choice_index is not None and not ctx.choices and ctx.reference
            and plan.selector.use_reference and not re.search(r"第[一二两三四五六七八九十0-9]+", body.text)):
        plan = plan.model_copy(update={"selector": plan.selector.model_copy(update={"choice_index": None})})
        normalizations.append("current_reference_is_not_candidate_zero")
    if (plan.selector.choice_index is not None and ctx.choices
            and not re.search(r"第[一二两三四五六七八九十0-9]+(?:个|批)", body.text)):
        if plan.selector.location and plan.selector.location in body.text:
            # Verify the described location across ALL current candidates rather
            # than trusting the model's guessed index.
            plan = plan.model_copy(update={"selector": plan.selector.model_copy(update={"choice_index": None})})
            normalizations.append("described_candidate_requires_live_filter")
        else:
            return problem(body, use, "CANDIDATE_SELECTION_UNGROUNDED", "请明确选择候选批次或说明可核对的位置，不能默认选择第一批。")
    if plan.memory_id and ctx.reference and plan.selector.use_reference and not HISTORICAL.search(body.text):
        if plan.memory_id not in use.selected_ids:
            return problem(body, use, "MEMORY_SELECTION_STALE", "所选旧话题不可用，请重新核对对象。")
        # A bare 'it' refers to the latest explicit object, not an unrelated
        # old episode selected by the provider. Its original TTL still applies.
        plan = plan.model_copy(update={"memory_id": None})
        normalizations.append("bare_pronoun_uses_current_reference")
    hypothesis_half = plan.speech_act == "hypothesis" and plan.amount_mode == "half" and "一半" in body.text
    if hypothesis_half:
        plan = plan.model_copy(update={"reads": [Read(kind="quantity")], "action": None, "write_count": 0})
        normalizations.append("hypothesis_half_is_read_only_arithmetic")
    episode = None
    binding = False
    if plan.memory_id:
        episode = next((e for e in episodes if e.memory_id == plan.memory_id), None)
        if episode is None:
            return problem(body, use, "MEMORY_SELECTION_STALE", "原话题已不在当前可用记忆中，请重新定位。")
        # An explicit current name takes precedence. Never silently retarget it.
        names = [s.name for s in episode.subjects]
        current_name = plan.selector.name
        if "name" in plan.fields and plan.fields["name"].source == "current_text":
            current_name = plan.fields["name"].value
        if current_name and current_name in body.text and names and current_name not in names:
            return problem(body, use, "MEMORY_OBJECT_CONFLICT", "你本轮提到的物品与旧话题不同，请明确要继续哪一个。")
        if plan.speech_act == "recall":
            reply = "之前你提到：“"+episode.text+"”。这是历史讨论，当前库存和执行结果需要重新核对。"
            frame = P85Resolved(original_text=body.text, kind="explain", reply=reply, facts={"f0": reply},
                                memory=use, expression_required=False,
                                evidence=[{"kind": "historical_user_text", "memory_id": episode.memory_id,
                                           "request_id": episode.request_id, "created_at": episode.created_at.isoformat()}])
            frame.memory_delta = delta(body, frame)
            return frame
        object_needed = bool(plan.reads or plan.action or plan.speech_act in {"supplement", "correction"})
        if plan.speech_act in {"status", "basis"}:
            task_index = next((i for i, t in enumerate(ctx.tasks) if episode.reference and
                               t.task_id == episode.reference.source_task_id), None)
            if task_index is None:
                return problem(body, use, "TASK_REFERENCE_REQUIRED", "记得这个话题，但没有原任务的最新状态，请重新定位任务。")
            plan = plan.model_copy(update={"task_index": task_index})
        if object_needed and not episode.reference:
            return problem(body, use, "MEMORY_OBJECT_RESELECT_REQUIRED", "记得之前讨论过这个话题，但没有可用的批次引用，请重新选择当前物品。")
        if object_needed and not episode.reference.issued_at <= owner.now() < episode.reference.expires_at:
            return problem(body, use, "REFERENCE_EXPIRED", "记得之前讨论过这个对象，但原引用已过期，请重新选择当前批次。")
        if object_needed:
            same_topics = [e for e in body.archive.episodes if set(s.name for s in e.subjects) & set(names)]
            if len({e.reference.batch_id for e in same_topics if e.reference}) > 1:
                return problem(body, use, "MEMORY_OBJECT_AMBIGUOUS", "之前这个物品涉及不止一批，请重新查询并选择要继续的批次。")
            active = ctx.active.task if ctx.active else None
            command = active.result.draft if active and active.result else None
            if plan.speech_act == "correction" and command and getattr(command, "batch_id", None) != episode.reference.batch_id:
                return problem(body, use, "DRAFT_TARGET_CONFLICT", "旧话题对象与当前草稿不同，请确认要继续的对象并新建任务。")
        # Historical target binding is separate from original user text. Nothing
        # in an old reply supplies quantity/unit/date/location or receipt state.
        if object_needed:
            ctx = ctx.model_copy(update={"reference": episode.reference})
            if plan.selector.choice_index is not None:
                return problem(body, use, "AMBIGUOUS_OBJECT_SELECTION", "请分别确认是在选择当前候选，还是继续旧话题。")
            plan = plan.model_copy(update={"selector": plan.selector.model_copy(update={"use_reference": True})})
            # A batch may have been renamed/reassigned since the old discussion.
            # Verify identity inside the normal read deadline, without another fetch.
            reader, expected = owner.reader, set(names)
            if plan.selector.name: expected = {plan.selector.name}
            class BoundReader:
                def __getattr__(self, key): return getattr(reader, key)
                async def get_batch(self, read_scope, ident):
                    row = await reader.get_batch(read_scope, ident)
                    check_scope(read_scope, [row])
                    if row.id != ident or expected and row.name not in expected:
                        raise DomainError("REFERENCE_IDENTITY_CHANGED", "旧话题中的物品已变化，请重新选择。")
                    return row
            owner = copy.copy(owner)
            owner.reader = BoundReader()
            binding = True
    legacy = ResolveRequest(text=body.text, request_id=body.request_id,
        household_timezone=body.household_timezone, context=ctx,
        current_task_plan=body.current_task_plan, remaining_seconds=body.remaining_seconds,
        plan=Plan.model_validate(plan.model_dump(exclude={"memory_id"})))
    old = await previous.resolve(owner, legacy, scope)
    frame = P85Resolved(**old.model_dump(exclude={"protocol_version"}), memory=use)
    if (plan.speech_act in {"social", "discuss", "hypothesis", "negation"} and not plan.action and not plan.reads
            and not plan.fields and not plan.write_count and not guard(body.text) and not frame.error_code):
        if HOLD.fullmatch(body.text.strip()):
            frame.reply = "可以，先核对你的想法。聊天不会替你执行变更。"
            frame.facts = {"f0": frame.reply}
        elif prose := household_prose(plan.social_reply):
            frame.reply, frame.facts = prose, {"f0": prose}
            normalizations.append("non_factual_household_discussion")
        else:
            frame.reply = fallback(body.text)
            frame.facts = {"f0": frame.reply}
            normalizations.append("non_factual_discussion_fallback")
    if hypothesis_half and frame.result and frame.result.get("status") == "answered":
        rows = frame.result.get("facts", [])
        if len(rows) == 1:
            row = rows[0]
            remaining = Decimal(row["quantity"])/2
            if remaining.as_tuple().exponent >= -6:
                phrase = f"仅作假设：若消耗一半，余量为 {remaining} {row['unit']}。没有生成或执行变更。"
                frame.facts[f"f{len(frame.facts)}"] = phrase
                frame.reply = "\n".join(frame.facts.values())
                frame.evidence.append({"kind": "hypothetical_calculation", "batch_id": row["id"],
                                       "version": row["version"], "formula": "current_quantity / 2", "inventory_written": False})
    if episode and binding:
        frame.evidence.append({"kind": "memory_object_binding", "memory_id": episode.memory_id,
                               "request_id": episode.request_id, "batch_id": episode.reference.batch_id})
        frame.field_sources["object"] = {"source": "historical_attested_reference", "memory_id": episode.memory_id,
                                         "batch_id": episode.reference.batch_id}
    elif episode:
        frame.evidence.append({"kind": "historical_user_text", "memory_id": episode.memory_id,
                               "request_id": episode.request_id})
    if plan.speech_act in {"social", "discuss", "hypothesis", "negation", "status", "basis", "recall", "new_task"}:
        frame.expression_required = False
    frame.memory_delta = delta(body, frame)
    return frame


async def respond(owner, body):
    if not body.resolved.expression_required:
        return P85Responded(reply=body.resolved.reply, response_calls=0)
    try:
        async with asyncio.timeout(body.remaining_seconds):
            method = getattr(owner.engine, "p85_respond", None)
            value = await method(body.text, body.resolved) if method else await engine.respond(owner, body, render.vocabulary())
            reply = render.render(value, body.resolved)
        return P85Responded(reply=reply, response_calls=1)
    except (EngineError, ValueError, TypeError, KeyError, TimeoutError):
        return P85Responded(reply=body.resolved.reply, response_calls=1, fallback_used=True,
                            error_code="P85_RESPONSE_FALLBACK")
