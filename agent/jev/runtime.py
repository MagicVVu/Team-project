"""Optional P8.6 decision adapter. Lab/synthetic contracts remain unchanged.

Only the authenticated Agent caller invokes this module. It sends current text
and a few context flags, never inventory rows, history, business IDs or receipts.
"""
import asyncio
import re
import time
from dataclasses import dataclass

from .config import Config, MODEL, CACHE
from .providers import LiveProvider, fingerprint
from .questions import choice, first_questions, validate_response
from .schemas import CallTrace, JevError, Node, WireResponse

PROTOCOL = "p9-optional-routing-1"


@dataclass(frozen=True)
class Options:
    timeout_seconds: float = 2.0
    minimum_confidence: float = .8
    minimum_probability: float = .9

    def __post_init__(self):
        if not 0 < self.timeout_seconds <= 4:
            raise ValueError("Jev runtime timeout must be at most four seconds")
        if not 0 <= self.minimum_confidence <= 1 or not 0 <= self.minimum_probability <= 1:
            raise ValueError("invalid experimental routing thresholds")


def runtime_questions():
    questions = first_questions()
    for question in questions.values():
        question["instructions"] = question["instructions"].replace(
            "仅判断 state 中的合成家庭库存场景。", "仅判断当前家庭库存请求的语义，不推断库存事实。")
        if question["type"] == "choice":
            question["criteria"] = {k: v.replace("整批", "整件") for k, v in question["criteria"].items()}
    questions[Node.CLARIFICATION.value] = choice(
        "仅从当前表达判断是否仍需澄清。没有提供完整库存资料，不得断言对象唯一或字段完整。",
        {"PASS": "表达的单一意图明确，实际资料仍由业务代码校验。",
         "CLARIFY": "表达本身含糊或混合多个任务。", "UNKNOWN": "无法可靠判断。"})
    questions[Node.ACTION.value] = choice(
        "建议处理方向，不是执行授权。逐件实物消耗与丢弃必须选定整件，不允许按规格扣减。",
        {"READ": "只读问答方向，仍需真实读取。", "CONFIRM": "明确变更方向，仍需原解析和用户确认。",
         "CLARIFY": "原文有待补充语义。", "WAIT": "不能可靠确定处理方向。"})
    return questions


class Router:
    def __init__(self, provider, *, options=None):
        self.provider = provider
        self.options = options or Options()

    def session(self):
        return Session(self)


def from_environment(mode):
    """Called only by the P8.6 app factory when the operator enables assist."""
    if mode != "assist":
        raise ValueError("unknown Jev runtime mode")
    return Router(LiveProvider(Config.from_environment()))


class Session:
    """One request's decisions and billing; never shared between conversations."""
    def __init__(self, router):
        self.router = router
        self.answers = {}
        self.call = None
        self.status = "bypassed"
        self.reason = None
        self.elapsed_ms = 0

    async def classify(self, body, context, remaining):
        started = time.monotonic()
        budget = min(self.router.options.timeout_seconds, remaining / 4)
        if remaining < 1:
            self.reason = "INSUFFICIENT_TIME"
            return None
        # No production request is represented as a synthetic lab request.
        state = {"origin": "authenticated_business_request", "inventory_model": "single-object-1",
                 "text": body.text, "has_active_task": context.active is not None,
                 "has_current_reference": context.reference is not None,
                 "protocol_version": PROTOCOL}
        payload = {"model": MODEL, "state": state, "questions": runtime_questions()}
        self.call = CallTrace(phase=1, source=self.router.provider.source, fingerprint=fingerprint(payload))
        try:
            # A mounted existing cache may lack Docker's new child directory.
            # Storage errors fall back too; they do not prevent service startup.
            if self.router.provider.source == "live" and CACHE.is_symlink() and not CACHE.exists():
                CACHE.resolve().mkdir(parents=True, exist_ok=True)
            async with asyncio.timeout(budget):
                response = await self.router.provider.ask(payload, self.call)
                response = validate_response(WireResponse.model_validate(response), payload)
            self.answers = response.answers
            self.status = "fallback"
            plan = self.read_plan(body, context)
            if plan is not None:
                self.status = "routed_read"
            return plan
        except (JevError, TimeoutError, OSError, ValueError, TypeError, KeyError) as error:
            self.status = "fallback"
            self.reason = getattr(error, "code", "JEV_TIMEOUT" if isinstance(error, TimeoutError) else "JEV_UNAVAILABLE")
            self.call.status, self.call.error_code = "error", self.reason
            return None
        finally:
            self.elapsed_ms = (time.monotonic() - started) * 1000

    def confident(self, key):
        answer = self.answers.get(key)
        return (answer is not None and answer.type == "choice"
                and answer.confidence >= self.router.options.minimum_confidence
                and answer.probabilities[answer.choice] >= self.router.options.minimum_probability)

    def read_plan(self, body, context):
        # Do not bypass active tasks, history selection, compound requests or
        # references. All of these retain the existing semantic/selection flow.
        if context.active or context.reference or context.choices or context.reference_error:
            self.reason = "CONTEXT_REQUIRES_ORIGINAL_FLOW"
            return None
        keys = (Node.INTENT.value, Node.EVENT.value, Node.CLARIFICATION.value, Node.ACTION.value, "speech_act")
        if not all(self.confident(key) for key in keys) or self.answers["multiple_actions"].noul > .2:
            self.reason = "UNCERTAIN_SEMANTICS"
            return None
        if (self.answers[Node.EVENT.value].choice != "NONE"
                or self.answers[Node.CLARIFICATION.value].choice != "PASS"
                or self.answers[Node.ACTION.value].choice != "READ"
                or self.answers["speech_act"].choice not in {"QUESTION", "REQUEST"}):
            self.reason = "ORIGINAL_UNDERSTANDING_REQUIRED"
            return None
        text = body.text.strip()
        match = re.fullmatch(r"([^\s，,。！？?!、]{1,30}?)(还有多少|剩多少|库存多少|在哪里|在哪儿|在哪)[？?。]?", text)
        if not match:
            self.reason = "FIELDS_REQUIRE_ORIGINAL_PARSER"
            return None
        name, suffix = match.groups()
        if re.search(r"它|这|那|之前|刚才|昨天|明天|不要|如果|是不是|家里|冰箱里|和|并|再|第", name):
            self.reason = "SELECTOR_REQUIRES_ORIGINAL_FLOW"
            return None
        kind = "quantity" if suffix in {"还有多少", "剩多少", "库存多少"} else "location"
        expected = "QUERY_INVENTORY" if kind == "quantity" else "QUERY_LOCATION"
        if self.answers[Node.INTENT.value].choice != expected:
            self.reason = "INTENT_SELECTOR_CONFLICT"
            return None
        from conversation.p85.schemas import P85Plan
        # Name is an exact current-text span; original scoped resolver still reads it.
        return P85Plan(speech_act="question", selector={"name": name}, reads=[{"kind": kind}])

    def hint(self):
        # A hint is untrusted semantic data, never an alternative instruction or fact.
        return {"protocol_version": PROTOCOL, "source": self.router.provider.source,
                "choices": {k: a.choice for k, a in self.answers.items() if a.type == "choice"},
                "execution_authorized": False} if self.answers else None

    def protect(self, decision):
        plan = decision.plan
        if not plan or not plan.action or plan.speech_act not in {"request", "correction", "supplement"}:
            return decision
        if self.confident("speech_act") and self.answers["speech_act"].choice in {"QUESTION", "PLAN", "NEGATED"}:
            from conversation.autonomous.schemas import Decision
            self.status, self.reason = "guarded", "NON_AFFIRMATIVE_CHANGE"
            return Decision(action="ask", clarification="intent")
        return decision

    def audit(self):
        return {"protocol_version": PROTOCOL, "source": self.router.provider.source,
                "status": self.status, "reason": self.reason, "elapsed_ms": self.elapsed_ms,
                "nodes": {k: a.model_dump(mode="json", exclude_none=True) for k, a in self.answers.items()},
                "call": self.call.model_dump(mode="json") if self.call else None,
                "calibrated": False}
