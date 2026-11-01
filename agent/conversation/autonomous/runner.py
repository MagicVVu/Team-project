"""Bounded by time and progress, never by a fixed number of model calls."""
import asyncio
import copy
import hashlib
import json
import time

from p0.domain import DomainError
from p0.engines import EngineError
from p1.domain import guard
from ..dialogue import grounded_fields
from ..p85 import flow, render
from ..p85.memory import prepare, delta
from ..p85.schemas import P85Plan, P85ResolveRequest, P85Resolved
from . import engine
from . import physical
from .reads import ReadOnly
from .schemas import RunResponse, Decision, Step
from ..language import choose, using

REPAIRABLE = {"UNGROUNDED_FIELD", "UNGROUNDED_SELECTOR", "CANDIDATE_SELECTION_UNGROUNDED", "ACTION_SEMANTIC_CONFLICT"}
QUESTIONS = {"intent":"你希望我查询资料、登记操作，还是先讨论一下？",
    "object":"你想处理哪个物品或批次？", "quantity":"请补充这次要登记的明确数量。",
    "unit":"请补充数量对应的单位。", "date":"请补充明确的日期。",
    "location":"请补充要使用的位置。", "priority":"你提到了多项修改，想先处理哪一项？"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def merge(previous, current):
    """Keep the latest domain card, plus all previously verified fact blocks."""
    if previous is None: return current.model_copy(deep=True)
    frame = current.model_copy(deep=True)
    old = list(previous.facts.values())
    facts = old + [v for v in current.facts.values() if v not in old]
    frame.facts = {f"f{i}": text for i, text in enumerate(facts)}
    frame.reply = "\n".join(facts)
    frame.evidence = previous.evidence + [v for v in current.evidence if v not in previous.evidence]
    frame.filled_fields = {**previous.filled_fields, **current.filled_fields}
    frame.field_sources = {**previous.field_sources, **current.field_sources}
    frame.truncated |= previous.truncated
    frame.memory.truncated |= previous.memory.truncated
    if frame.result is None and previous.result is not None and not frame.error_code:
        frame.result = copy.deepcopy(previous.result)
        frame.kind = previous.kind
    return frame


def unavailable(frame):
    domain = frame.result or {}
    if domain.get("data_gaps"): return True
    for evidence in frame.evidence:
        value = evidence.get("result", {})
        if value.get("data_gaps"): return True
        for key in ("consumption_summary", "forecast", "recommendations", "risks"):
            for item in value.get(key, []):
                if item.get("status") in {"insufficient_data", "needs_review", "unavailable"} or item.get("missing_information"): return True
    return False


def terminal(frame, plan):
    domain = frame.result or {}
    if frame.error_code:
        if frame.error_code in REPAIRABLE: return None
        return "needs_input", "data_unavailable" if frame.error_code.startswith(("TOOL_", "PLANNING_")) or frame.error_code=="SPECIFICATION_READ_UNAVAILABLE" else "boundary"
    if domain.get("status") == "needs_confirmation": return "needs_confirmation", "confirmation_required"
    if frame.kind == "clarify" or frame.kind == "needs_input" or domain.get("status") == "needs_clarification":
        return "needs_input", "user_input_required"
    if unavailable(frame): return "needs_input", "data_unavailable"
    rows = domain.get("facts", [])
    if any(read.kind == "location" and any(not r.get("location") for r in rows)
           or read.kind == "dates" and any(r.get("opened_at") is None or r.get("label_expiry") is None for r in rows)
           for read in plan.reads):
        return "needs_input", "data_unavailable"
    if plan.speech_act in {"social", "discuss", "negation", "hypothesis", "status", "basis", "recall", "new_task"}:
        return "completed", "completed"
    # No actual row/result and no resolvable task is not successful inventory QA.
    if not domain and not frame.answers: return "needs_input", "user_input_required"
    return None


def observation(frame):
    if frame is None: return None
    # Transport IDs and clock stamps are not semantic progress.
    return {"kind":frame.kind, "facts":frame.facts, "error_code":frame.error_code,
            "result":{k:v for k,v in (frame.result or {}).items() if k in
                      {"status", "facts", "missing_fields", "data_gaps", "draft", "candidates"}},
            "filled_fields":frame.filled_fields}


async def _run(owner, body, scope):
    start = time.monotonic()
    deadline = start + min(58, body.remaining_seconds)
    ctx, episodes, memory = prepare(owner, body, scope)
    owner = copy.copy(owner)
    owner._autonomous_context_lease = (scope, ctx.conversation_id, ctx.revision, ctx.trusted_now, deadline)
    reader = owner.reader = ReadOnly(owner.reader, scope, deadline)
    calls, trace, plans = 0, [], []
    router = getattr(owner, "jev_router", None)
    jev = router.session() if router is not None else None
    verified, last, last_plan = None, None, None
    seen_plans, seen_results = set(), set()
    filled = {}

    def finish(status, reason, *, reply=None, code=None, fallback=False):
        if jev is not None:
            for item in trace:
                if item.action == "jev":
                    item.jev = jev.audit()
        frame = verified.model_copy(deep=True) if verified else last.model_copy(deep=True) if last else None
        if frame and frame.locale!=ctx.locale and last_plan:
            from ..language.render import localize_frame
            localize_frame(frame,P85ResolveRequest(**body.model_dump(exclude={'remaining_seconds'}),plan=last_plan,plan_context_revision=ctx.revision))
        text = reply or (frame.reply if frame else choose("本轮尚未完成，请保留原文并核对原请求。","This turn is incomplete. Keep the original input and check the original request."))
        if reason not in {"completed", "confirmation_required", "user_input_required", "data_unavailable", "boundary"}:
            note = {"deadline":"处理达到本轮时限，以上仅为已核实部分，请核对未完成事项。",
                "repeated_plan":"继续读取没有新增信息，先停在已核实结果；请说明还需核对哪一点。",
                "no_progress":"本轮没有取得新的核对进展，请补充或重新定位问题。",
                "model_error":"后续理解未完成，已停止调用；请核对以上结果或原请求。",
                "context_limit":"必要资料超出本轮输入容量，请缩小问题范围。",
                "context_refresh_required":"原任务状态需要重新读取后核对。"}[reason]
            if ctx.locale=='en':note={
                'deadline':'The turn reached its time limit. Only the verified partial results are shown.',
                'repeated_plan':'No new information was produced by the repeated plan. Review the verified results before continuing.',
                'no_progress':'No further verified progress was made. Please clarify the unresolved question.',
                'model_error':'Further interpretation failed. Calls have stopped; verified information is retained.',
                'context_limit':'The required context exceeds this turn’s capacity. Please narrow the question.',
                'context_refresh_required':'The original task status must be refreshed before continuing.'}[reason]
            text = text+"\n"+note if frame else note
        if frame:
            frame.reply = text
            if last_plan:
                replay_body = P85ResolveRequest(**body.model_dump(exclude={"remaining_seconds"}),
                    remaining_seconds=min(18, max(.001, deadline-time.monotonic())),
                    plan=last_plan, plan_context_revision=ctx.revision)
                frame.memory_delta = delta(replay_body, frame)
        return RunResponse(locale=ctx.locale,request_id=body.request_id, context_revision=ctx.revision, original_text=body.text,
            reply=text, status=status, stop_reason=reason, resolved=frame, plan=last_plan,
            verified_plans=plans, filled_fields=filled, model_calls=calls, tool_reads=reader.calls,
            elapsed_ms=(time.monotonic()-start)*1000, trace=trace,
            error_code=code or (last.error_code if last else None), fallback_used=fallback)

    literal = P85Plan(speech_act="negation") if guard(body.text) else flow.literal_plan(body)
    if not literal and getattr(owner,"inventory_model",None)=="single-object-1":
        described=physical.REFERENCE_QUERY.fullmatch(body.text.strip())
        if described:
            literal=P85Plan(speech_act="question",selector={"use_reference":True},
                reads=[{"kind":"quantity" if described[1] in {"数量","还剩多少"} else "location"}])
    pending = Decision(action="resolve", plan=literal) if literal else None
    if jev is not None and pending is None:
        fast = await jev.classify(body, ctx, deadline-time.monotonic())
        attempted = bool(jev.call and jev.call.attempted)
        calls += int(attempted)
        trace.append(Step(step=len(trace)+1, action="jev", model_call=attempted, jev=jev.audit()))
        if fast is not None:
            pending = Decision(action="resolve", plan=fast, finish_after_resolve=True)
    while True:
        remaining = deadline-time.monotonic()
        if remaining <= 0: return finish("stopped", "deadline", fallback=True)
        paid = pending is None
        if paid:
            payload = {"original_text":body.text, "context":ctx.model_dump(mode="json"),
                "working_summary":memory.summary,
                "inventory_model":getattr(owner,"inventory_model","batch-quantity-1"),
                "retrieved_episodes":[e.model_dump(mode="json") for e in episodes],
                "observations":observation(last), "verified_facts":verified.facts if verified else {},
                "previous_steps":[s.model_dump() for s in trace if s.action != "jev"][-6:]}
            if jev is not None and jev.hint() is not None:
                payload["jev_hint"] = jev.hint()
            # Do not silently remove active tasks or candidates to fit a prompt.
            while len(json.dumps(payload, ensure_ascii=False).encode()) > 30000 and payload["context"]["history"]:
                payload["context"]["history"].pop(0); memory.truncated = True
            while len(json.dumps(payload, ensure_ascii=False).encode()) > 30000 and payload["retrieved_episodes"]:
                payload["retrieved_episodes"].pop(0); memory.truncated = True
            if len(json.dumps(payload, ensure_ascii=False).encode()) > 30000:
                return finish("stopped", "context_limit", fallback=True)
            calls += 1
            try:
                async with asyncio.timeout(min(15, remaining)):
                    decision = await engine.next_step(owner, payload, min(15, remaining))
            except (EngineError, ValueError, TypeError, KeyError, TimeoutError) as error:
                trace.append(Step(step=len(trace)+1, action="model_error", model_call=True,
                                  error_code=getattr(error, "code", "AUTONOMOUS_MODEL_FAILED")))
                return finish("stopped", "deadline" if time.monotonic() >= deadline else "model_error",
                              code=getattr(error, "code", "AUTONOMOUS_MODEL_FAILED"), fallback=True)
        else:
            decision, pending = pending, None
        if jev is not None:
            decision = jev.protect(decision)
        step = Step(step=len(trace)+1, action=decision.action, model_call=paid)
        trace.append(step)
        if decision.action == "ask":
            question = QUESTIONS[decision.clarification] if ctx.locale!='en' else {
                'intent':'Would you like to query information, prepare a draft, or discuss an idea?',
                'object':'Which registered item would you like to use?',
                'quantity':'Please provide the exact quantity to record.','unit':'Which unit does that quantity use?',
                'date':'Please provide an unambiguous date.','location':'Please specify the location.',
                'priority':'You requested multiple changes. Which one should be handled first?'}[decision.clarification]
            return finish("needs_input", "user_input_required", reply=(verified.reply+"\n" if verified else "")+question)
        if decision.action == "finish":
            if not verified or last and last.error_code:
                return finish("needs_input", "user_input_required", fallback=True)
            try:
                reply = render.render(decision.expression, verified) if decision.expression else verified.reply
                return finish("completed", "completed", reply=reply)
            except (ValueError, TypeError):
                return finish("completed", "completed", fallback=True)
        plan = decision.plan
        key = digest(plan.model_dump(mode="json"))
        step.plan_sha256 = key
        if key in seen_plans: return finish("stopped", "repeated_plan", fallback=True)
        seen_plans.add(key)
        # Status facts keep their original timestamp. The backend refreshes and
        # zero-model revalidates plans after a long run, not a forged timestamp.
        if (plan.speech_act in {"status", "basis", "correction", "supplement"}
                and (owner.now()-ctx.trusted_now).total_seconds() > 30):
            last_plan = plan
            return finish("needs_input", "context_refresh_required", fallback=True)
        last_plan = plan
        for name, field in plan.fields.items():
            try:
                values, _ = grounded_fields(plan.model_copy(update={"fields":{name:field}}), body.text, ctx, body.household_timezone)
                filled.update(values)
            except DomainError: pass
        request = P85ResolveRequest(**body.model_dump(exclude={"remaining_seconds"}),
            plan=plan, plan_context_revision=ctx.revision, remaining_seconds=min(18, max(.001, deadline-time.monotonic())))
        try:
            last=physical.precheck(body,plan,memory,filled) if getattr(owner,"inventory_model",None)=="single-object-1" else None
            if last is None:
                async with asyncio.timeout(max(.001, deadline-time.monotonic())):
                    last = await flow.resolve(owner, request, scope)
                if getattr(owner,"inventory_model",None)=="single-object-1":last=physical.project(body,last,plan)
        except DomainError as error:
            if error.status == 403: raise
            return finish("needs_input", "boundary", code=error.code, fallback=True)
        except TimeoutError:
            return finish("stopped", "deadline", fallback=True)
        step.error_code = last.error_code
        if last.error_code:
            # Legacy error frames retain quoted fields before semantic checks.
            # Only independently grounded values may survive in a loop result.
            last.filled_fields = {k:v for k,v in last.filled_fields.items() if filled.get(k)==v}
        last.memory.truncated |= memory.truncated
        last.truncated |= last.memory.truncated
        signature = digest(observation(last))
        if signature in seen_results: return finish("stopped", "no_progress", fallback=True)
        seen_results.add(signature)
        if not last.error_code:
            verified = merge(verified, last)
            plans.append(plan)
            filled.update(last.filled_fields)
        end = terminal(last, plan)
        if end:
            # An error after a successful read must remain visible as well.
            if last.error_code and verified:
                verified = merge(verified, last)
            return finish(*end)
        if literal or decision.finish_after_resolve and not last.error_code:
            return finish("completed", "completed")


async def run(owner,body,scope):
    with using(body.context.locale):
        return await _run(owner,body,scope)
