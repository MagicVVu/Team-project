"""Two-round orchestration, opt-in only. No imports from production managers."""
import asyncio
import hashlib
import time

from .config import MODEL
from .policy import constraints, combine
from .providers import MockProvider, canonical, fingerprint
from .questions import (QUESTION_VERSION, POLICY_VERSION, first_questions,
                        second_questions, validate_response)
from .schemas import (DecisionRequest, DecisionResult, Node, NodeResult, NodeState,
                      CallTrace, Action, JevError)


class Engine:
    def __init__(self, provider=None, *, total_timeout=10):
        if not 0 < total_timeout <= 10:
            raise ValueError("total timeout must be at most 10 seconds")
        self.provider = provider if provider is not None else MockProvider()
        self.total_timeout = total_timeout

    async def evaluate(self, request):
        request = DecisionRequest.model_validate(request).model_copy(deep=True)
        return await self._run(request)

    async def evaluate_node(self, node, state):
        node = Node(node)
        if isinstance(state, DecisionRequest):
            state = NodeState(request=state)
        state = NodeState.model_validate(state).model_copy(deep=True)
        return await self._run(state.request, node=node, upstream=state.upstream)

    async def _run(self, request, *, node=None, upstream=None):
        started = time.perf_counter()
        input_hash = hashlib.sha256(canonical(request.model_dump(mode="json")).encode()).hexdigest()
        nodes = {n: NodeResult(node=n) for n in Node}
        result = DecisionResult(request_id=request.request_id, input_sha256=input_hash,
            question_version=QUESTION_VERSION, policy_version=POLICY_VERSION,
            status="unavailable", nodes=nodes)
        nodes = result.nodes
        active = []

        async def call(phase, state, questions):
            nonlocal active
            active = [Node(k) for k in questions if k in Node._value2member_map_]
            payload = {"model": MODEL, "state": state, "questions": questions}
            trace = CallTrace(phase=phase, source=self.provider.source, fingerprint=fingerprint(payload))
            result.calls.append(trace)
            try:
                response = validate_response(await self.provider.ask(payload, trace), payload)
            except JevError as error:
                trace.status, trace.error_code = "error", error.code
                raise
            trace.status = "ok"
            for n in active:
                nodes[n] = NodeResult(node=n, status="ok", source=self.provider.source,
                    answer=response.answers[n.value], model=response.model if self.provider.source != "mock" else None)
            return response.answers

        try:
            async with asyncio.timeout(self.total_timeout):
                first_state = {"synthetic": True, "text": request.text,
                               "now": request.now.isoformat(), "timezone": request.timezone}
                if node in {Node.INTENT, Node.EVENT}:
                    await call(1, first_state, {node.value: first_questions()[node.value]})
                    result.status, result.reasons = "needs_review", ["STANDALONE_NODE_ONLY"]
                    return result
                if node is not None:
                    # Downstream debugging must supply explicit, fully validated upstream answers.
                    required = first_questions()
                    from .schemas import WireResponse
                    if set(upstream or {}) != set(required):
                        raise JevError("UPSTREAM_REQUIRED")
                    first = validate_response(WireResponse(model=MODEL, answers=upstream,
                        usage={"input_tokens": 0, "output_tokens": 0}), {"questions": required}).answers
                else:
                    first = await call(1, first_state, first_questions())
                result.auxiliary = {k: v for k, v in first.items() if k not in Node._value2member_map_}
                hard_reasons, missing = constraints(request, first)
                result.missing_fields = missing
                state = {**first_state, "facts": request.facts.model_dump(mode="json"),
                         "upstream": {k: v.model_dump(mode="json", exclude_none=True) for k, v in first.items()},
                         "hard_reasons": hard_reasons, "missing_fields": missing}
                second = await call(2, state, {node.value: second_questions()[node.value]} if node else second_questions())
                if node is not None:
                    result.status, result.reasons = "needs_review", ["STANDALONE_NODE_ONLY", *hard_reasons]
                    if node == Node.ACTION:
                        result.raw_action = Action(second[node.value].choice)
                    return result
                answers = {**first, **second}
                result.raw_action = Action(second[Node.ACTION.value].choice)
                result.final_action, result.reasons = combine(request, answers, hard_reasons)
                result.status = "needs_review" if result.reasons or result.final_action in {Action.CLARIFY, Action.WAIT} else "ok"
        except (JevError, TimeoutError, OSError) as error:
            code = error.code if isinstance(error, JevError) else "TOTAL_TIMEOUT" if isinstance(error, TimeoutError) else "LOCAL_STORAGE_UNAVAILABLE"
            result.reasons = [code]
            for n in active:
                if nodes[n].status == "skipped":
                    nodes[n] = NodeResult(node=n, status="error", source=self.provider.source, error_code=code)
            if result.calls and result.calls[-1].status == "pending":
                result.calls[-1].status, result.calls[-1].error_code = "error", code
            result.final_action, result.status = Action.WAIT, "unavailable"
        finally:
            result.elapsed_ms = (time.perf_counter() - started) * 1000
        return result
