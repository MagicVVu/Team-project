import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from p0.domain import DomainError, UNITS, convert, normalize_unit
from .engines import ALL_PATTERN, AMOUNT_PATTERN, NUMBER_PATTERN, actions, number
from .schemas import (AddCommand, Batch, ChangePreview, ConsumeCommand, DiscardCommand,
    Intent, MoveCommand, OpenCommand, Parsed, PlanCommand, ProposedState, valid_quantity)

TARGET_ACTIONS = {Intent.CONSUME, Intent.OPEN, Intent.MOVE, Intent.DISCARD}
WRITE_ACTIONS = TARGET_ACTIONS | {Intent.ADD, Intent.PLAN_ADD}
INJECTION = r"忽略.*(?:指令|规则|系统)|跳过确认|不[用要需]确认|直接(?:执行|扣减|落库)|(?:system|assistant)\s*:|删库"


def guard(text: str, parsed: Parsed | None = None) -> str | None:
    if re.search(INJECTION, text, re.I):
        return "库存变更必须先生成草稿并由你确认。"
    if parsed is None:
        return None
    detected = actions(text)
    if parsed.multiple_items or parsed.multiple_actions or len(detected) > 1 or re.search(r"以及|、|和", text):
        return "请一次提交一个物品的一种操作。"
    if parsed.intent == Intent.UNSUPPORTED:
        return "当前支持新增、消耗、查询、采购草稿、整批开封、整批移动和丢弃。"
    if parsed.intent in WRITE_ACTIONS and parsed.intent not in detected:
        return "未找到明确的操作依据，请说明要新增、消耗、开封、移动或丢弃。"
    if parsed.intent == Intent.DISCARD and re.search(ALL_PATTERN, text) and re.search(AMOUNT_PATTERN, text):
        return "全部丢弃与明确数量同时出现，请选择一种方式重新说明。"
    if parsed.intent in {Intent.OPEN, Intent.MOVE} and (parsed.partial_batch or re.search(r"其中|只开|一部分|部分", text) or re.search(AMOUNT_PATTERN, text)):
        return "本阶段只支持整批开封或整批移动；部分操作需要先拆批。"
    return None


def ground(parsed: Parsed, text: str) -> Parsed:
    """Discard ungrounded proposals, never let model JSON manufacture a fact."""
    result = parsed.model_copy(deep=True)
    missing = list(result.uncertainties)
    for field in ("name", "location", "to_location", "opened_at", "purchased_at", "label_expiry"):
        value = getattr(result, field)
        if value:
            value = value.strip()
            setattr(result, field, value or None)
            if not value or value.casefold() not in text.casefold():
                setattr(result, field, None)
                missing.append(field)
    # Remove date literals before looking for quantity evidence.
    quantity_text = re.sub(r"\d{4}-\d{1,2}-\d{1,2}", "", text)
    numbers = [number(m[0]) for m in re.finditer(NUMBER_PATTERN, quantity_text)]
    if result.quantity is not None and result.quantity not in numbers:
        result.quantity = None
        missing.append("quantity")
    if result.unit:
        try:
            target = normalize_unit(result.unit)
            if not any(alias in text for alias, canonical in UNITS.items() if canonical == target):
                result.unit = None
                missing.append("unit")
        except DomainError:
            missing.append("unit")
    if result.intent == Intent.DISCARD and result.discard_mode == "all" and not re.search(ALL_PATTERN, text):
        result.discard_mode = "partial"
        result.quantity = None
        missing.append("quantity")
    result.uncertainties = list(dict.fromkeys(missing))
    return result


def parse_date(value: str, reference: datetime, timezone_name: str) -> date:
    today = reference.astimezone(ZoneInfo(timezone_name)).date()
    if value in {"今天", "昨天"}:
        return today - timedelta(days=value == "昨天")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("日期必须是 YYYY-MM-DD、今天或昨天")
    return date.fromisoformat(value)


def missing_fields(parsed: Parsed, reference: datetime, timezone_name: str, today: date):
    missing = []
    if parsed.intent != Intent.QUERY_INVENTORY and not parsed.name:
        missing.append("name")
    if parsed.intent in {Intent.ADD, Intent.CONSUME, Intent.PLAN_ADD} or (parsed.intent == Intent.DISCARD and parsed.discard_mode == "partial"):
        try:
            valid_quantity(parsed.quantity)
        except (ValueError, TypeError, AttributeError):
            missing.append("quantity")
        try:
            normalize_unit(parsed.unit)
        except (DomainError, TypeError):
            missing.append("unit")
    if parsed.intent == Intent.MOVE and not parsed.to_location:
        missing.append("to_location")
    if parsed.intent == Intent.OPEN and not parsed.opened_at:
        missing.append("opened_at")
    dates = {}
    for field in ("opened_at", "purchased_at", "label_expiry"):
        value = getattr(parsed, field)
        if value:
            try:
                dates[field] = parse_date(value, reference, timezone_name)
                if field == "opened_at" and dates[field] > today:
                    missing.append(field)
            except ValueError:
                missing.append(field)
    if dates.get("purchased_at") and dates.get("label_expiry") and dates["label_expiry"] < dates["purchased_at"]:
        missing.extend(["purchased_at", "label_expiry"])
    relevant = {"name"}
    if parsed.intent in {Intent.ADD, Intent.CONSUME, Intent.PLAN_ADD, Intent.DISCARD}:
        relevant |= {"quantity", "unit"}
    if parsed.intent == Intent.ADD:
        relevant |= {"location", "purchased_at", "label_expiry"}
    if parsed.intent == Intent.OPEN:
        relevant.add("opened_at")
    if parsed.intent == Intent.MOVE:
        relevant.add("to_location")
    missing += [field for field in parsed.uncertainties if field in relevant]
    return list(dict.fromkeys(missing)), dates


def make_draft(parsed: Parsed, batch: Batch | None, dates: dict):
    name = batch.name if batch else parsed.name
    if parsed.intent == Intent.ADD:
        command = AddCommand(name=name, quantity=parsed.quantity, unit=parsed.unit,
            location=parsed.location, purchased_at=dates.get("purchased_at"), label_expiry=dates.get("label_expiry"))
        preview = ChangePreview(event_type="Added", quantity_delta=command.quantity,
            after=ProposedState(quantity=command.quantity, unit=command.unit, location=command.location, status="ACTIVE"))
    elif parsed.intent == Intent.PLAN_ADD:
        command = PlanCommand(name=name, quantity=parsed.quantity, unit=parsed.unit)
        preview = ChangePreview(inventory_changes=False)
    else:
        target = {"name": name, "batch_id": batch.id, "expected_version": batch.version}
        after = ProposedState(quantity=batch.quantity, unit=batch.unit, location=batch.location,
                              opened_at=batch.opened_at, status="ACTIVE")
        delta = Decimal(0)
        if parsed.intent == Intent.OPEN:
            command = OpenCommand(**target, opened_at=dates["opened_at"])
            after.opened_at = command.opened_at
            event = "Opened"
        elif parsed.intent == Intent.MOVE:
            command = MoveCommand(**target, to_location=parsed.to_location.strip())
            after.location = command.to_location
            event = "Moved"
        else:
            quantity = batch.quantity if parsed.intent == Intent.DISCARD and parsed.discard_mode == "all" else convert(parsed.quantity, parsed.unit, batch.unit)
            valid_quantity(quantity)
            if quantity > batch.quantity:
                raise DomainError("INSUFFICIENT_STOCK", "操作数量超过当前库存，请核对数量。")
            if parsed.intent == Intent.DISCARD:
                command = DiscardCommand(**target, discard_mode=parsed.discard_mode, quantity=quantity, unit=batch.unit)
                event = "Discarded"
                if quantity == batch.quantity:
                    after.status = "DISCARDED"
            else:
                command = ConsumeCommand(**target, quantity=quantity, unit=batch.unit)
                event = "Consumed"
                if quantity == batch.quantity:
                    after.status = "FINISHED"
            after.quantity -= quantity
            delta = -quantity
        preview = ChangePreview(batch_id=batch.id, before=batch, after=after, event_type=event, quantity_delta=delta)
    return command, preview
