"""P8.4 staged dialogue. Plans carry intent; only deterministic reads create facts.

This module never confirms a draft or mutates inventory/shopping. The business
caller persists each stage and supplies a fresh, permission-checked context.
"""
import asyncio
import re
import time
from decimal import Decimal
from datetime import timedelta

from p0.domain import DomainError, normalize_unit, new_id
from p0.engines import EngineError
from p0.text import number, NUMBER_PATTERN
from p1.domain import guard, TARGET_ACTIONS
from p1.schemas import Parsed, Message, Batch
from p1.tools import check_scope
from .manager import LifecycleManager, LOCATION_REFERENCE, business_fields
from .memory import bounded_context, STATUS, BASIS, RECALL, ORDINAL, START_TASK, explain_state, basis_text
from .replies import resolve_reply
from .schemas import AgentResult
from .dialogue_schemas import (Request, Plan, FieldSource, Selector, Read, Understood, ResolveRequest,
                               Resolved, RespondRequest, Responded)
from . import dialogue_engine


def checked(owner, body, scope):
    if body.context.scope != scope:
        raise DomainError("HOUSEHOLD_FORBIDDEN", "会话不属于当前用户或家庭。", 403)
    # The autonomous owner can retain its originally authenticated context for
    # one bounded run. This never renews timestamps, task facts or object TTLs.
    lease = getattr(owner, "_autonomous_context_lease", None)
    accepted = lease and lease[:4] == (scope, body.context.conversation_id, body.context.revision,
                                      body.context.trusted_now) and time.monotonic() < lease[4]
    if abs((owner.now()-body.context.trusted_now).total_seconds()) > 30 and not accepted:
        raise DomainError("MEMORY_SNAPSHOT_EXPIRED", "请重新读取会话与任务状态。", 409)
    return bounded_context(body.context)


def literal_plan(body):
    """Only unambiguous controls/structured continuations bypass understanding."""
    text, context = body.text.strip().rstrip("。！？?! "), body.context
    if text in START_TASK: return Plan(speech_act="new_task", preserve_active=False)
    if re.fullmatch(r"(?:再试一下|再试一次|重试一下|重新执行)(?:吧)?",text) and any(
            t.execution_status in {"committed","unknown","processing"} for t in context.tasks):
        return Plan(speech_act="status")
    if STATUS.fullmatch(text): return Plan(speech_act="status")
    if context.tasks and re.search(r"执行|生效|确认|取消|提交|成功|完成|做完|扣掉",text) and re.search(r"[吗呢？?]|有没有|到底|核对.*结果|状态|之后|还需要|需要.*什么",text):
        return Plan(speech_act="status")
    if BASIS.fullmatch(text): return Plan(speech_act="basis")
    if context.tasks and re.search(r"建议",text) and re.search(r"依据|来源|怎么计算|为什么|有依据",text):
        return Plan(speech_act="basis")
    if RECALL.fullmatch(text): return Plan(speech_act="recall")
    ordinal = ORDINAL.fullmatch(text)
    if ordinal:
        n = number(ordinal[1])
        if n is not None and n == int(n) and n >= 1:
            return Plan(speech_act="supplement" if context.active and context.active.task.status == "needs_clarification" else "question",
                        selector=Selector(choice_index=int(n)-1), reads=[Read(kind="quantity" if "多少" in text else "location")])
    if LOCATION_REFERENCE.fullmatch(text):
        return Plan(speech_act="question", selector=Selector(use_reference=True), reads=[Read(kind="location")])
    if context.active and context.active.task.status == "needs_clarification":
        route = resolve_reply(context.active, body.text, context.scope, context.trusted_now,
                              selected_batch_id=context.reference.batch_id if context.reference else None)
        if route.kind == "clarify":
            fields = {k: FieldSource(value=v, quote=body.text) for k, v in route.answers.items() if k != "batch_id"}
            index = next((i for i, r in enumerate(context.choices) if r.batch_id == route.answers.get("batch_id")), None)
            return Plan(speech_act="supplement", fields=fields, selector=Selector(choice_index=index))
    return None


async def understand(owner, body, scope):
    context = checked(owner, body, scope)
    if guard(body.text):
        return Understood(original_text=body.text, plan=Plan(speech_act="negation"), understanding_calls=0)
    if plan := literal_plan(body):
        return Understood(original_text=body.text, plan=plan, understanding_calls=0, truncated=context.truncated)
    async with asyncio.timeout(body.remaining_seconds):
        method = getattr(owner.engine, "dialogue_understand", None)
        plan = await method(body.text, context) if method else await dialogue_engine.understand(owner, body.text, context, body.remaining_seconds)
    return Understood(original_text=body.text, plan=Plan.model_validate(plan), understanding_calls=1, truncated=context.truncated)


def grounded_fields(plan, text, context, timezone_name="Asia/Shanghai"):
    values, sources = {}, {}
    active = context.active.task if context.active else None
    command = active.result.draft.model_dump(mode="json") if active and active.result and active.result.draft else {}
    if active and active.result and active.result.clarification:
        # Public clarification intentionally contains no trusted parsed fields.
        command = {**command}
    for field, source in plan.fields.items():
        value = source.value.strip()
        if source.source == "current_task":
            if plan.speech_act != "correction" or not command or str(command.get(field)) != value:
                raise DomainError("UNGROUNDED_FIELD", "这个字段没有当前任务依据，请重新说明。")
        else:
            quote = source.quote
            if not quote or quote not in text:
                raise DomainError("UNGROUNDED_FIELD", "请明确本轮要填写的字段，不能使用猜测值。")
            if field == "quantity":
                numbers = [number(m[0]) for m in re.finditer(NUMBER_PATTERN, re.sub(r"\d{4}-\d{2}-\d{2}", "", quote))]
                try: valid = Decimal(value) in numbers
                except Exception: valid = False
            elif field == "unit":
                from p0.text import UNIT_PATTERN
                valid = any(normalize_unit(match[0]) == normalize_unit(value) for match in re.finditer(UNIT_PATTERN,quote))
            else:
                valid = value in quote
                if not valid and field in {"opened_at","purchased_at","label_expiry"}:
                    from p1.domain import parse_date
                    relative=re.findall(r"今天|昨天",quote)
                    if len(set(relative))==1:
                        expected=parse_date(relative[0],context.trusted_now,timezone_name).isoformat()
                        valid=value==expected
                        if valid:value=relative[0]
            if not valid: raise DomainError("UNGROUNDED_FIELD", "该字段与本轮原文不一致，请核对。")
        values[field] = value
        sources[field] = source.model_dump()
    # Literal unit inference is allowed only from the quantity's exact quote.
    if "quantity" in values and "unit" not in values:
        from p0.text import UNIT_PATTERN
        quote=plan.fields["quantity"].quote
        units={normalize_unit(m[0]) for m in re.finditer(UNIT_PATTERN,quote)}
        if len(units)==1:
            values["unit"]=next(iter(units))
            sources["unit"]={"source":"current_text","quote":quote,"value":values["unit"],"parser":"literal_unit"}
    return values, sources


class Snapshot:
    """Request-local cache: compound quantity/location/date reads share one row."""
    def __init__(self, reader): self.reader, self.rows, self.searches = reader, {}, {}
    async def get_batch(self, scope, ident):
        if ident not in self.rows:
            value = await self.reader.get_batch(scope, ident)
            check_scope(scope, [value])
            if value.id != ident: raise DomainError("TOOL_UNAVAILABLE", "库存工具返回错误批次。", 503)
            self.rows[ident] = value
        return self.rows[ident]
    async def search(self, scope, name):
        if name not in self.searches:
            rows = check_scope(scope, await self.reader.search(scope, name))
            self.searches[name] = [self.rows.setdefault(row.id, row) for row in rows]
        return self.searches[name]


async def _resolve(owner, body, scope):
    context, plan = checked(owner, body, scope), body.plan
    result = Resolved(original_text=body.text, kind="explain", reply="", truncated=context.truncated)
    def finish(reply=None, **kwargs):
        for key, value in kwargs.items(): setattr(result, key, value)
        result.reply = reply if reply is not None else "\n".join(result.facts.values())
        if result.reply and not result.facts: result.facts["f0"] = result.reply
        return result
    def fact(text): result.facts[f"f{len(result.facts)}"] = text
    if guard(body.text):
        return finish("库存变更需要核对草稿并由你确认，不能通过聊天绕过。", kind="needs_input", error_code="INVALID_CONVERSATION_INPUT")
    if plan.speech_act == "new_task":
        return finish("已开始新任务。之前的草稿没有被取消或执行。", kind="clear_reference", preserve_active=False)
    if plan.speech_act=="question" and plan.task_index is not None and not plan.action and not plan.reads:
        plan=plan.model_copy(update={"speech_act":"status"})
    if plan.speech_act in {"status", "basis"}:
        evidence = context.tasks[plan.task_index] if plan.task_index is not None and plan.task_index < len(context.tasks) else next(
            (t for t in context.tasks if context.active and t.task_id == context.active.task.task_id), None)
        if plan.task_index is not None and plan.task_index >= len(context.tasks): evidence = None
        if evidence is None:
            return finish("请选择要核对的原任务，我不能从聊天推断执行结果。", kind="needs_input", error_code="TASK_REFERENCE_REQUIRED")
        result.evidence = [{"task_id": str(evidence.task_id), "revision": evidence.revision, "kind": "fresh_task_read", "checked_at": evidence.checked_at.isoformat()}]
        return finish(explain_state(evidence) if plan.speech_act == "status" else
                      "已记录的建议依据："+basis_text(evidence.basis) if evidence.basis else "原任务缺少可核实的计算依据，暂时不能可靠解释。")
    if plan.speech_act == "recall":
        return finish("最近讨论过："+"；".join(t.text for t in context.history[-3:])+"。这是历史讨论，不代表当前库存或执行结果。" if context.history else "当前没有可可靠回顾的历史，请选择原任务。")
    values, result.field_sources = grounded_fields(plan, body.text, context,body.household_timezone)
    result.filled_fields = values.copy()
    selector = plan.selector
    referenced_name = None
    for key in ("name", "location"):
        value = getattr(selector, key)
        if value and value not in body.text:
            if key=="name" and selector.use_reference and context.reference:
                referenced_name=value
                selector=selector.model_copy(update={"name":None})
                result.field_sources["object"]={"source":"trusted_reference","batch_id":context.reference.batch_id}
                continue
            if key=="location" and plan.speech_act=="correction" and context.active and context.active.task.result.preview and context.active.task.result.preview.before and value==context.active.task.result.preview.before.location:
                selector=selector.model_copy(update={"location":None})
                continue
            raise DomainError("UNGROUNDED_SELECTOR", "请明确本轮查询的对象或位置。")
    # Discussion/hypothesis/negation never produces a draft, even if a model proposes action.
    allowed_write = plan.speech_act in {"request", "correction", "supplement"} and plan.write_count <= 1
    action = plan.action if allowed_write else None
    active = context.active.task if context.active else None
    editing = plan.speech_act == "correction" and active and active.status == "needs_confirmation"
    command = active.result.draft.model_dump(mode="json") if editing and active.result and active.result.draft else {}
    # Duplicate aliases of the same edit are not two edits. Check equality first.
    if editing and command.get("action")=="MOVE" and values.get("location")==values.get("to_location"):
        values.pop("location",None)
    if editing:
        state = next((t for t in context.tasks if t.task_id == active.task_id), None)
        if state is None or state.execution_status != "pending" or not active.expires_at or active.expires_at <= owner.now():
            return finish(explain_state(state) if state else "请先核实原草稿最新状态，不能覆盖之前的执行结果。", kind="needs_input", error_code="DRAFT_NOT_EDITABLE")
        different_choice = selector.choice_index is not None and (selector.choice_index >= len(context.choices) or
            context.choices[selector.choice_index].batch_id != command.get("batch_id"))
        if action and action != command.get("action") or selector.name and selector.name != command.get("name") or different_choice:
            editing, command = False, {}
        else:
            action = command.get("action")
            if (command.get("discard_mode")=="all" or active.result.consume_mode=="all") and ("quantity" in values or plan.amount_mode=="half"):
                return finish("这份草稿按全部余量处理，数量不能单独修改。请新建定量任务。",kind="needs_input",error_code="PROTECTED_DRAFT_MODE")
            permitted = {"ADD":{"quantity","unit","location","purchased_at","label_expiry"}, "CONSUME":{"quantity","unit"},
                         "PLAN_ADD":{"quantity","unit"}, "MOVE":{"to_location"}, "OPEN":{"opened_at"}, "DISCARD":{"quantity","unit"}}.get(action, set())
            if (not values and plan.amount_mode not in {"half","all"}) or not set(values) <= permitted:
                return finish("请说明要修改的数量、位置或日期；更换对象或动作需要新建任务。", kind="needs_input", error_code="INVALID_DRAFT_EDIT")
    if plan.speech_act not in {"discuss","hypothesis","negation","social"} and re.search(r"然后|再|同时|并|还要",body.text):
        patterns={"OPEN":r"开封(?!日期|时间)","MOVE":r"移到|移动到|搬到","CONSUME":r"消耗|喝掉|用掉",
                  "DISCARD":r"丢弃|扔","ADD":r"新增|入库","PLAN_ADD":r"待购|采购清单"}
        if sum(bool(re.search(p,body.text)) for p in patterns.values())>1:plan.write_count=max(2,plan.write_count)
    if not plan.reads and not action and plan.write_count<=1 and plan.speech_act not in {"supplement", "correction"}:
        # Social text is untrusted natural prose. No stock/receipt claims are accepted.
        reply = plan.social_reply or "可以，我们先核对你的想法。你想了解哪个物品或任务？"
        factual = re.search(r"\d|库存(?:有|剩|是)|已经|已(?:执行|移动|消耗|丢弃|加入|开封|被|由)|执行成功|安全食用|不会过期|还剩|余量|到期日是",reply)
        asserted_location = re.search(r"(?:放在|位于|在)(?:[\u4e00-\u9fff]{1,20})(?:里|中|上|下|。|，|$)",reply) and not re.search(r"建议|可以|通常|不妨|如果",reply)
        if factual or asserted_location:
            reply = "可以聊聊你的家庭安排。如果要核对库存或登记操作，告诉我物品和想做的事。"
        return finish(reply)
    reader = Snapshot(owner.reader)
    reference = None
    if selector.choice_index is not None:
        if selector.choice_index >= len(context.choices):
            return finish("请从当前展示的候选中重新选择。", kind="needs_input", error_code="INVALID_CANDIDATE")
        reference = context.choices[selector.choice_index]
    elif not (selector.location and context.choices) and (selector.use_reference or not selector.name and not values.get("name")):
        reference = context.reference
    # Same-target corrections use the saved draft's identity, never a guessed ID.
    target = command.get("batch_id") if editing else None
    if reference:
        if not reference.issued_at <= owner.now() < reference.expires_at or reference.expires_at-reference.issued_at > timedelta(minutes=15):
            return finish("我记得之前讨论过这个对象，但引用已过期，请重新确认当前批次。", kind="needs_input", error_code="REFERENCE_EXPIRED")
        result.reference = reference.model_dump(mode="json")
    if not reference and not target and not (selector.name or values.get("name")) and context.reference_error:
        return finish("之前讨论的对象需要重新确认，请重新选择当前批次。", kind="needs_input", error_code=context.reference_error)
    if target or reference:
        rows = [await reader.get_batch(scope, target or reference.batch_id)]
    elif selector.name or values.get("name"):
        name = selector.name or values["name"]
        rows = await reader.search(scope, name)
        rows = [r for r in rows if name.casefold() in r.name.casefold()]
        exact = [r for r in rows if r.name.casefold() == name.casefold()]
        rows = exact or rows
    elif selector.location and context.choices:
        if any(not r.issued_at <= owner.now() < r.expires_at for r in context.choices):
            return finish("原候选已过期，请重新查询。", kind="needs_input", error_code="REFERENCE_EXPIRED")
        rows = [await reader.get_batch(scope, r.batch_id) for r in context.choices]
    else:
        rows = []
    if selector.location: rows = [r for r in rows if selector.location in (r.location or "")]
    if referenced_name and (len(rows)!=1 or rows[0].name!=referenced_name):
        return finish("当前对象与提到的名称不一致，请重新选择。",kind="needs_input",error_code="REFERENCE_IDENTITY_CHANGED")
    for row in rows:
        result.evidence.append({"kind":"inventory_read", "batch_id":row.id, "version":row.version, "checked_at":owner.now().isoformat()})
    for read in plan.reads:
        if read.kind in {"quantity", "location", "dates"}:
            for row in rows:
                if read.kind == "quantity": fact(f"{row.name}：登记数量 {row.quantity} {row.unit}，状态 {row.status}。")
                elif read.kind == "location": fact(f"{row.name}：位置 {row.location or '尚未登记'}。")
                else: fact(f"{row.name}：开封日期 {row.opened_at or '未知'}，标示到期日 {row.label_expiry or '未知'}。")
        else:
            from p3.schemas import Query
            intent = {"risk":"QUERY_RISK", "consumption":"QUERY_CONSUMPTION", "forecast":"QUERY_FORECAST", "purchase":"SUGGEST_PURCHASE"}[read.kind]
            name = selector.name or values.get("name")
            if not name and len(rows) != 1:
                fact("统计或建议需要明确一个对象；当前资料不足，暂不可用。")
            else:
                if read.kind=="risk":
                    from p2.manager import Manager as RiskManager
                    from p2.schemas import RiskQuery
                    risk=RiskManager(None,reader,owner.catalog,now=owner.now)
                    evaluated=await risk.evaluate(RiskQuery(batch_ids=[r.id for r in rows],household_timezone=body.household_timezone),scope)
                    fact(risk.explain(evaluated.risks))
                    result.evidence.append({"kind":"verified_calculation","result":evaluated.model_dump(mode="json")})
                else:
                    query = Query(name=None if len(rows)==1 else name, item_key=rows[0].id if len(rows)==1 else None,
                                  household_timezone=body.household_timezone)
                    computed = await owner.query(query, scope, intent)
                    fact(computed.reply)
                    result.evidence.append({"kind":"verified_calculation", "result":computed.model_dump(mode="json")})
    if plan.write_count > 1:
        fact("你提到了多项修改。想先处理哪一项？目前没有生成或执行变更。")
        return finish(kind="needs_input", error_code="MULTIPLE_WRITES")
    if plan.speech_act == "supplement" and active and active.status == "needs_clarification":
        allowed = set(active.result.clarification.allowed_fields)
        answers = {k:v for k,v in values.items() if k in allowed}
        if len(rows) == 1 and "batch_id" in allowed: answers["batch_id"] = rows[0].id
        previous = body.current_task_plan
        if previous and previous.amount_mode in {"half","all"} and previous.action in {"CONSUME","DISCARD"} and len(rows)==1 and {"quantity","unit"} <= allowed:
            amount = rows[0].quantity / (2 if previous.amount_mode=="half" else 1)
            answers.update(quantity=str(amount),unit=rows[0].unit)
            result.field_sources["quantity"]={"source":"deterministic_calculation","formula":previous.amount_mode,
                "batch_id":rows[0].id,"version":rows[0].version,"stock":str(rows[0].quantity)}
        if answers:
            return finish("继续核对原任务，尚未执行。", kind="clarify", answers=answers, task_revision=active.revision)
    if not action:
        if not result.facts: fact("请明确要核对的物品或选择一个批次。")
        if rows:
            result.kind = "task"
            result.result = AgentResult(status="answered", original_text=body.text, reply="\n".join(result.facts.values()),
                                       trace_id=new_id("trace"), intent="QUERY_INVENTORY", facts=rows).model_dump(mode="json")
            if reference:
                result.result.update(object_source="trusted_reference",reference_used={"source_task_id":str(reference.source_task_id),
                    "source_revision":reference.source_revision,"batch_id":reference.batch_id})
        return finish()
    if action in {"MOVE","OPEN"} and plan.amount_mode=="all" and "quantity" not in values:
        plan.amount_mode="literal"
    if action in {"MOVE","OPEN"} and ("quantity" in values or plan.amount_mode=="half"):
        return finish("目前支持整批移动或开封。部分操作需要先拆分批次。",kind="needs_input",error_code="PARTIAL_BATCH_UNSUPPORTED")
    if action in TARGET_ACTIONS and len(rows) != 1 and (selector.location or reference):
        # Lifecycle returns real candidates/clarification, never first-row default.
        pass
    if editing and target and rows and rows[0].version != command.get("expected_version"):
        return finish("库存已变化，请重新核对原草稿。", kind="needs_input", error_code="INVENTORY_VERSION_CONFLICT")
    parsed_values = {k:v for k,v in command.items() if k in Parsed.model_fields}
    for field,value in parsed_values.items():
        if field not in values:
            result.field_sources[field]={"source":"current_task","task_id":str(active.task_id),
                "revision":active.revision,"value":str(value)}
    parsed_values.update(values)
    parsed_values.update(intent=action, name=rows[0].name if len(rows)==1 else selector.name or values.get("name") or command.get("name"))
    if command.get("discard_mode"): parsed_values["discard_mode"] = command["discard_mode"]
    if plan.amount_mode in {"half", "all"}:
        if not re.search(r"一半|半数|50[%％]" if plan.amount_mode=="half" else r"全部|剩下|剩余|余下|都",body.text):
            return finish("请明确要记录的数量或比例。",kind="needs_input",error_code="UNGROUNDED_AMOUNT_MODE")
        if action not in {"CONSUME", "DISCARD"}:
            return finish("此操作不支持按比例处理。", kind="needs_input", error_code="QUANTITY_TARGET_REQUIRED")
        if action == "DISCARD": parsed_values["discard_mode"] = "all" if plan.amount_mode=="all" else "partial"
        if len(rows)==1:
            parsed_values["quantity"] = rows[0].quantity / (2 if plan.amount_mode=="half" else 1)
            parsed_values["unit"] = rows[0].unit
            result.field_sources["quantity"] = {"source":"deterministic_calculation", "formula":plan.amount_mode,
                "batch_id":rows[0].id, "version":rows[0].version, "stock":str(rows[0].quantity)}
    elif plan.amount_mode == "unknown" and "quantity" not in values:
        parsed_values.pop("quantity", None)
        parsed_values.pop("unit", None)
    parsed = Parsed.model_validate(parsed_values)
    parsed.uncertainties += business_fields(parsed)
    lifecycle = LifecycleManager(None, reader, now=owner.now)
    ctx = lifecycle._context(Message(text=body.text, request_id=body.request_id, household_timezone=body.household_timezone), scope, new_id("trace"), parsed)
    # Freeze the exact verified target set for this resolution, including source filters.
    async def selected_search(scope, name): return rows if action in TARGET_ACTIONS else await reader.search(scope, name)
    class BoundReader:
        search = staticmethod(selected_search)
        get_batch = reader.get_batch
    lifecycle.reader = BoundReader()
    base = await lifecycle._resolve(ctx, scope, [])
    domain = AgentResult.model_validate(base.model_dump())
    if domain.draft and hasattr(domain.draft,"quantity"):
        domain.quantity_source="current_batch" if plan.amount_mode in {"half","all"} else "user_input"
    if domain.draft and action=="CONSUME" and plan.amount_mode=="all":
        domain.consume_mode="all"
        domain.quantity_source="current_batch"
    if reference:
        from .schemas import ReferenceUse
        domain.object_source = "trusted_reference"
        domain.reference_used = ReferenceUse(source_task_id=reference.source_task_id,
            source_revision=reference.source_revision,batch_id=reference.batch_id)
    result.result = domain.model_dump(mode="json")
    result.kind = "edit" if editing and domain.status=="needs_confirmation" else "task"
    result.preserve_active = False if action else True
    if result.kind == "edit":
        if plan.amount_mode in {"half","all"}:
            values.update(quantity=str(domain.draft.quantity),unit=domain.draft.unit)
        result.edit = {"task_id":str(active.task_id), "task_revision":active.revision, "edits":values,
                       "draft_id":str(active.draft_id), "expires_at":active.expires_at.isoformat()}
    fact(domain.reply)
    if domain.draft:
        draft = domain.draft
        fact("本次草稿：" + (f"{draft.quantity} {draft.unit}。" if hasattr(draft,"quantity") else
             f"目标位置 {draft.to_location}。" if hasattr(draft,"to_location") else f"开封日期 {draft.opened_at}。"))
    return finish()


async def resolve(owner, body, scope):
    try:
        async with asyncio.timeout(body.remaining_seconds):
            return await _resolve(owner, body, scope)
    except (DomainError, ValueError, TimeoutError) as error:
        if isinstance(error, DomainError) and error.status == 403: raise
        reply = getattr(error, "message", "资料核对未完成，请保留原文并重新选择对象或手动核对。")
        return Resolved(original_text=body.text, kind="needs_input", reply=reply, facts={"f0":reply},
                        error_code=getattr(error,"code","DIALOGUE_RESOLVE_FAILED"),
                        filled_fields={k:v.value for k,v in body.plan.fields.items() if v.quote and v.quote in body.text})


def validate_template(template, facts):
    if not isinstance(template,str) or len(template)>8000: raise ValueError("Invalid response")
    used = re.findall(r"\{\{fact:(f\d+)\}\}", template)
    if sorted(used)!=sorted(facts): raise ValueError("Missing or invented evidence")
    prose = re.sub(r"\{\{fact:f\d+\}\}", "", template)
    # Unrestricted facts cannot escape the verified placeholders.
    if re.search(r"\d|[一二两三四五六七八九十半]+(?:盒|瓶|克|升|天|个)|已执行|执行成功|已移动|已消耗|已丢弃|待确认|未执行|过期|安全|风险|位置|库存|剩余|数量|冷藏|冰箱|厨房|昨天|今天|明天|已取消|已加入|耗尽", prose):
        raise ValueError("Ungrounded factual prose")
    # A blacklist alone cannot prove arbitrary prose factual. Keep connective
    # language to a small reviewed vocabulary; all other content uses anchors.
    connective = re.sub(r"[\s，,。.!！?？：:；;、～~]", "", prose)
    allowed = ("好的","嗯","明白了","我理解你的意思","我来帮你核对","先一起核对一下","请核对", "请看看", "你想先处理哪一项", "需要我继续帮你核对吗", "我们可以继续", "如果需要可以继续问我", "接下来")
    for phrase in sorted(allowed,key=len,reverse=True): connective=connective.replace(phrase,"")
    if connective: raise ValueError("Unverified response prose")
    for key, value in facts.items(): template = template.replace("{{fact:"+key+"}}", value)
    if "{{" in template or "}}" in template: raise ValueError("Unknown placeholder")
    return template.strip()


async def respond(owner, body):
    try:
        async with asyncio.timeout(body.remaining_seconds):
            method = getattr(owner.engine,"dialogue_respond",None)
            template = await method(body.text, body.resolved) if method else await dialogue_engine.respond(owner, body.text, body.resolved, body.remaining_seconds)
        return Responded(reply=validate_template(template, body.resolved.facts), response_calls=1)
    except (EngineError, ValueError, TypeError, TimeoutError, KeyError):
        return Responded(reply=body.resolved.reply, response_calls=1, fallback_used=True, error_code="DIALOGUE_RESPONSE_FALLBACK")


def install(app, owner, scope):
    from fastapi import Depends
    from p0.schemas import Scope
    @app.post("/agent/dialogue/understand", response_model=Understood)
    async def understanding(body:Request, identity:Scope=Depends(scope)):
        return await understand(owner,body,identity)
    @app.post("/agent/dialogue/resolve", response_model=Resolved)
    async def resolving(body:ResolveRequest, identity:Scope=Depends(scope)):
        return await resolve(owner,body,identity)
    @app.post("/agent/dialogue/respond", response_model=Responded)
    async def responding(body:RespondRequest, identity:Scope=Depends(scope)):
        return await respond(owner,body)
