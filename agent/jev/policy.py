"""Pure constraints. Decisions are suggestions; this module has no write tools."""
from zoneinfo import ZoneInfo
import re

from .schemas import Intent, Action, Node

WRITE = {"ADD", "CONSUME", "PLAN_ADD", "OPEN", "MOVE", "DISCARD"}
TARGET = {"CONSUME", "OPEN", "MOVE", "DISCARD"}
EXPECTED = {"ADD": {"ADDED"}, "CONSUME": {"CONSUMED", "FINISHED"}, "OPEN": {"OPENED"},
            "MOVE": {"MOVED"}, "DISCARD": {"DISCARDED"}, "PLAN_ADD": {"NONE"}}


def constraints(request, answers):
    facts = request.facts
    intent = answers[Node.INTENT.value].choice
    event = answers[Node.EVENT.value].choice
    speech = answers["speech_act"].choice
    reasons, missing = [], list(facts.missing_fields)
    if not facts.known:
        reasons.append("FACTS_UNKNOWN")
    if facts.scope_valid is not True:
        reasons.append("SCOPE_UNVERIFIED")
    if facts.task_status != "ready":
        reasons.append("TASK_NOT_READY")
    if intent not in {"UNKNOWN", "UNSUPPORTED"} and intent not in facts.capabilities:
        reasons.append("CAPABILITY_UNAVAILABLE")
    if intent == "UNSUPPORTED":
        reasons.append("UNSUPPORTED_TASK")
    if facts.has_reference and facts.reference_valid is not True:
        reasons.append("REFERENCE_INVALID")
    if facts.conflicts:
        reasons.append("FACT_CONFLICT")
    if intent in {"UNKNOWN", "UNSUPPORTED"} or event == "UNKNOWN" or speech == "UNKNOWN":
        reasons.append("SEMANTIC_UNCERTAINTY")
    if answers["multiple_actions"].noul >= 0.3:
        # Ambiguous (0.3..0.7) is deliberately not treated as a clear no.
        reasons.append("MULTIPLE_ACTIONS_OR_UNCERTAIN")
    fields = facts.fields
    if intent in WRITE:
        if event not in EXPECTED[intent]:
            reasons.append("INTENT_EVENT_CONFLICT")
        if speech not in {"FACT", "REQUEST"}:
            reasons.append("NON_AFFIRMATIVE_CHANGE")
        if re.search(r"是不是|吗|如果|假如|不要|别把|没(?:有)?.{0,8}完|明天|准备|打算|计划", request.text):
            reasons.append("NON_AFFIRMATIVE_TEXT")
        if intent in {"OPEN", "MOVE"} and re.search(r"其中|一部分|部分", request.text):
            reasons.append("PARTIAL_BATCH_UNSUPPORTED")
        required = {"name"}
        if intent in {"ADD", "PLAN_ADD"} or (intent in {"CONSUME", "DISCARD"} and event != "FINISHED"):
            required |= {"quantity", "unit"}
        if intent == "ADD": required.add("location")
        if intent == "MOVE": required.add("to_location")
        if intent == "OPEN": required.add("opened_at")
        missing += [key for key in sorted(required) if getattr(fields, key) is None]
        if fields.quantity is not None and fields.quantity.normalize().as_tuple().exponent < -6:
            reasons.append("QUANTITY_PRECISION")
        if fields.unit is not None:
            from p0.domain import normalize_unit, DomainError
            try:
                normalize_unit(fields.unit)
            except DomainError:
                reasons.append("UNIT_CONFLICT")
        if fields.purchased_at and fields.label_expiry and fields.label_expiry < fields.purchased_at:
            reasons.append("DATE_CONFLICT")
        if fields.opened_at and fields.opened_at > request.now.astimezone(ZoneInfo(request.timezone)).date():
            reasons.append("OPEN_DATE_IN_FUTURE")
    elif event != "NONE":
        reasons.append("INTENT_EVENT_CONFLICT")
    if intent in TARGET:
        rows = facts.candidates
        batch = next((c for c in rows if c.id == facts.selected_id), None)
        if batch is None and len(rows) == 1:
            batch = rows[0]
        if batch is None:
            missing.append("batch_id")
            reasons.append("TARGET_NOT_UNIQUE")
        else:
            if batch.status != "ACTIVE" or batch.quantity <= 0:
                reasons.append("BATCH_TERMINAL")
            if facts.version_current is not True:
                reasons.append("VERSION_UNVERIFIED")
            if facts.unit_compatible is not True:
                reasons.append("UNIT_UNVERIFIED")
            if fields.name and fields.name != batch.name:
                reasons.append("TARGET_NAME_CONFLICT")
            if fields.quantity is not None:
                # Reuse the existing pure, tested unit conversion (no service imports).
                from p0.domain import convert, DomainError
                try:
                    if fields.unit is None or convert(fields.quantity, fields.unit, batch.unit) > batch.quantity:
                        reasons.append("QUANTITY_EXCEEDS_STOCK_OR_UNIT_MISSING")
                except DomainError:
                    reasons.append("UNIT_CONFLICT")
    if missing:
        reasons.append("MISSING_FIELDS")
    return list(dict.fromkeys(reasons)), list(dict.fromkeys(missing))


WAIT_REASONS = {"FACTS_UNKNOWN", "SCOPE_UNVERIFIED", "TASK_NOT_READY", "CAPABILITY_UNAVAILABLE",
                "REFERENCE_INVALID", "VERSION_UNVERIFIED", "BATCH_TERMINAL", "UNSUPPORTED_TASK"}


def combine(request, answers, reasons):
    reasons = list(reasons)
    intent = answers[Node.INTENT.value].choice
    raw = Action(answers[Node.ACTION.value].choice)
    if WAIT_REASONS.intersection(reasons):
        return Action.WAIT, reasons
    if reasons:
        return Action.CLARIFY, reasons
    clarify = answers[Node.CLARIFICATION.value].choice
    if clarify != "PASS":
        return Action.CLARIFY, ["MODEL_REQUESTS_CLARIFICATION"]
    if raw in {Action.WAIT, Action.CLARIFY}:
        return raw, ["MODEL_REQUESTS_" + raw.value]
    expected = Action.CONFIRM if intent in WRITE else Action.READ
    if raw != expected:
        reasons.append("ACTION_POLICY_OVERRIDE")
    return expected, reasons
