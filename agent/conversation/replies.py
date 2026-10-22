"""Pure caller-side reply routing. Android/backend must own and persist state.

No task fetch, revision store, model call or HTTP endpoint is implemented here.
Business callers must load BoundTask under the authenticated owner's permission.
"""
import re
from datetime import timedelta
from typing import Literal
from pydantic import Field, field_validator, model_validator
from p0.domain import DomainError, normalize_unit
from p0.schemas import Model, Scope
from p0.text import AMOUNT_PATTERN, NUMBER_PATTERN, actions, number
from p1.domain import guard, parse_date
from p1.schemas import Answers, Message
from interaction.policy import review_reason
from .manager import PRONOUN, LOCATION_REFERENCE
from .schemas import ObjectReference
from .tasks import Task
from v1.schemas import PUBLIC_FIELDS

REPLY_PROTOCOL = "p7-reply-routing-1"


class BoundTask(Model):
    scope: Scope
    task: Task
    # Load from the authenticated task/original request, never infer from device time.
    household_timezone: str = "Asia/Shanghai"
    _timezone = field_validator("household_timezone")(Message.timezone.__func__)

    @model_validator(mode="after")
    def consistent(self):
        if self.scope.household_id != str(self.task.household_id):
            raise ValueError("Task binding belongs to another household")
        return self


class ReplyResolution(Model):
    protocol_version: Literal["p7-reply-routing-1"] = REPLY_PROTOCOL
    kind: Literal["clarify", "new_task", "needs_input", "clear_reference"]
    answers: dict[str, str] = Field(default_factory=dict, max_length=9)
    revision: int | None = Field(default=None, ge=1, strict=True)
    error_code: str | None = None
    clear_reference: bool = False
    model_calls: Literal[0] = 0

    @model_validator(mode="after")
    def consistent(self):
        if self.kind == "clarify":
            if not self.answers or self.revision is None or self.error_code or self.clear_reference:
                raise ValueError("Clarification needs answers/revision and preserves the reference")
            if not set(self.answers) <= PUBLIC_FIELDS:
                raise ValueError("Only the existing public clarification fields are allowed")
        elif self.answers or self.revision is not None:
            raise ValueError("Only clarification may contain answers or a revision")
        if self.kind == "needs_input" and not self.error_code:
            raise ValueError("Missing input requires a reason")
        if self.kind == "needs_input" and self.clear_reference:
            raise ValueError("An ambiguous supplement must not silently clear the reference")
        if self.kind != "needs_input" and self.error_code:
            raise ValueError("Only missing input carries a routing error")
        if self.kind == "clear_reference" and not self.clear_reference:
            raise ValueError("Reset must explicitly clear the reference")
        return self


def _check(binding, scope):
    if binding.scope != scope:
        raise DomainError("HOUSEHOLD_FORBIDDEN", "任务不属于当前用户或家庭。", 403)


def reference_from_task(binding, scope, now, *, selected_batch_id=None):
    """Issue only after a fresh explicit selection or a fresh unique-object result.

Never renew from cached history on reopen. The caller checks user ownership and
latest revision in its DB before constructing BoundTask; this is not a signature.
"""
    _check(binding, scope)
    task = binding.task
    result = task.result
    if result is None or task.status in {"processing", "error", "unsupported"}:
        raise DomainError("REFERENCE_REQUIRED", "当前任务没有可引用对象。")
    if selected_batch_id is None:
        if task.status != "answered" or len(result.facts) != 1:
            raise DomainError("REFERENCE_AMBIGUOUS", "请明确选择一个物品批次。")
        batch_id = result.facts[0].id
    else:
        candidates = [*result.facts, *result.candidates]
        if result.preview and result.preview.before:
            candidates.append(result.preview.before)
        if selected_batch_id not in {b.id for b in candidates}:
            raise DomainError("INVALID_CANDIDATE", "只能引用当前任务中的真实批次。")
        batch_id = selected_batch_id
    return ObjectReference(scope=scope, source_task_id=task.task_id, source_revision=task.revision,
        batch_id=batch_id, issued_at=now, expires_at=now+timedelta(minutes=15))


def resolve_reply(binding, text, scope, now, *, selected_batch_id=None):
    """Convert only unambiguous literal supplements to the existing nine fields."""
    _check(binding, scope)
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        return ReplyResolution(kind="needs_input", error_code="INVALID_CLARIFICATION_INPUT")
    text = text.strip().rstrip("。！! ")
    if text == "开始新任务":
        return ReplyResolution(kind="clear_reference", clear_reference=True)
    if not text or guard(text) or review_reason(text):
        return ReplyResolution(kind="needs_input", error_code="INVALID_CLARIFICATION_INPUT")
    task = binding.task
    # An explicit new request is independent of an expired previous task.
    if actions(text) or LOCATION_REFERENCE.fullmatch(text) or re.search(r"哪里|在哪|什么地方|多少|有什么|过期[了吗]?", text):
        return ReplyResolution(kind="new_task", clear_reference=not bool(PRONOUN.search(text)))
    if task.status != "needs_clarification":
        return ReplyResolution(kind="new_task", clear_reference=not bool(PRONOUN.search(text)))
    advice = task.result.clarification
    if advice is None or advice.revision != task.revision:
        return ReplyResolution(kind="needs_input", error_code="CLARIFICATION_CONFLICT")
    if advice.expires_at is None or now >= advice.expires_at or (task.expires_at and now >= task.expires_at):
        return ReplyResolution(kind="needs_input", error_code="CLARIFICATION_EXPIRED")
    allowed = set(advice.allowed_fields)
    if not allowed or not allowed <= PUBLIC_FIELDS:
        return ReplyResolution(kind="needs_input", error_code="INVALID_CLARIFICATION_FIELDS")
    answers = {}
    ordinal = re.fullmatch(r"(?:选|选择|我要|就)?第([一二两三四五六七八九十0-9]+)(?:个|批|项)(?:吧)?", text)
    candidates = task.result.candidates
    if ordinal:
        if "batch_id" not in allowed:
            return ReplyResolution(kind="needs_input", error_code="INVALID_CANDIDATE")
        n = number(ordinal[1])
        ids = [b.id for b in candidates]
        if n is None or n != int(n) or not 1 <= n <= len(ids) or len(ids) != len(set(ids)):
            return ReplyResolution(kind="needs_input", error_code="INVALID_CANDIDATE")
        answers = {"batch_id":ids[int(n)-1]}
    elif text in {"这一批", "这批", "这个", "它"}:
        if "batch_id" not in allowed or selected_batch_id not in {b.id for b in candidates}:
            return ReplyResolution(kind="needs_input", error_code="REFERENCE_REQUIRED")
        answers = {"batch_id":selected_batch_id}
    elif re.fullmatch(r"今天|昨天|\d{4}-\d{2}-\d{2}", text):
        requested = allowed & {"purchased_at", "label_expiry", "opened_at"}
        if len(requested) != 1:
            return ReplyResolution(kind="needs_input", error_code="AMBIGUOUS_SUPPLEMENT")
        field = next(iter(requested))
        try:
            value = parse_date(text, now, binding.household_timezone)
            if field == "opened_at" and value > parse_date("今天", now, binding.household_timezone):
                raise ValueError("Opening date is in the future")
        except ValueError:
            return ReplyResolution(kind="needs_input", error_code="INVALID_DATE")
        answers = {field:text}
    elif match := re.fullmatch(AMOUNT_PATTERN, text):
        if not {"quantity", "unit"} <= allowed:
            return ReplyResolution(kind="needs_input", error_code="AMBIGUOUS_SUPPLEMENT")
        value = number(match[1])
        if value is None:
            return ReplyResolution(kind="needs_input", error_code="INVALID_QUANTITY")
        answers = {"quantity":str(value), "unit":match[2]}
    elif "quantity" in allowed and re.fullmatch(NUMBER_PATTERN, text):
        value = number(text)
        if value is not None: answers = {"quantity":str(value)}
    elif allowed == {"unit"}:
        try: answers = {"unit":normalize_unit(text)}
        except DomainError: pass
    elif len(allowed) == 1 and next(iter(allowed)) in {"name", "location", "to_location"}:
        answers = {next(iter(allowed)):text}
    if not answers:
        return ReplyResolution(kind="needs_input", error_code="AMBIGUOUS_SUPPLEMENT")
    try:
        validated = Answers.model_validate(answers)
        # Zero/negative amounts must not become plausible structured supplements.
        if validated.quantity is not None:
            from p1.schemas import valid_quantity
            valid_quantity(validated.quantity)
    except (ValueError, TypeError):
        return ReplyResolution(kind="needs_input", error_code="INVALID_CLARIFICATION_INPUT")
    return ReplyResolution(kind="clarify", answers=answers, revision=task.revision)
