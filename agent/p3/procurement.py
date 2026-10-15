from decimal import Decimal, ROUND_CEILING

from p0.domain import DomainError, convert
from p1.schemas import PlanCommand, valid_quantity
from .schemas import PlanningBasis, Recommendation


def suggest(item, snapshot, forecast, risks):
    result = Recommendation(item_key=item.item_key, name=item.name, unit=item.unit,
        status="insufficient_data", current_stock=forecast.current_stock, reason_codes=[])
    if item.category == "medicine":
        result.status, result.reason_codes = "excluded", ["MEDICINE_PROCUREMENT_OUT_OF_SCOPE"]
        return result
    if forecast.current_stock is None:
        result.status, result.reason_codes = "needs_review", ["STOCK_QUANTITY_UNVERIFIED"]
        return result
    if not item.usable_quantity_verified or any(r.level in {"red", "orange", "unknown"} for r in risks if not r.excluded):
        result.status, result.reason_codes = "needs_review", ["USABLE_STOCK_REQUIRES_REVIEW"]
        return result
    if not snapshot.pending_complete or snapshot.next_cursor:
        result.status, result.reason_codes = "needs_review", ["PENDING_INCOMPLETE"]
        return result
    pending, seen = Decimal(0), {}
    try:
        for row in snapshot.pending:
            if row.id in seen:
                if seen[row.id] != row:
                    raise DomainError("PENDING_ID_CONFLICT", "待购记录冲突。")
                continue
            seen[row.id] = row
            if row.item_key == item.item_key and row.confirmed and row.status == "pending":
                pending += convert(row.quantity, row.unit, item.unit)
    except DomainError as error:
        result.status, result.reason_codes = "needs_review", [error.code]
        return result
    result.pending_quantity = pending
    pref = item.preferences
    target = pref.minimum_stock
    if forecast.status == "estimated" and pref.coverage_days is not None and pref.lead_days is not None:
        history_target = forecast.summary.effective_quantity * (pref.coverage_days + pref.lead_days) / Decimal(forecast.summary.observed_days)
        target = max(target or Decimal(0), history_target)
        result.source = "recorded_history"
    elif target is not None:
        result.source = "minimum_stock"
    else:
        result.reason_codes = ["EXPLICIT_PURCHASE_PREFERENCES_REQUIRED"]
        return result
    result.target_stock = target
    amount = max(Decimal(0), target - result.current_stock - pending)
    if amount == 0:
        result.status, result.suggested_quantity = "covered", Decimal(0)
        result.reason_codes = ["EXISTING_STOCK_AND_PENDING_COVER_TARGET"]
        return result
    if pref.pack_size is not None:
        amount = (amount / pref.pack_size).to_integral_value(rounding=ROUND_CEILING)
        result.unit = pref.order_unit
    try:
        valid_quantity(amount)
    except ValueError:
        result.status, result.reason_codes = "needs_review", ["QUANTITY_PRECISION_OR_RANGE"]
        return result
    result.status, result.suggested_quantity = "suggested", amount
    result.reason_codes = ["RECORDED_TARGET_SHORTFALL"]
    return result


def draft(item, snapshot, recommendation):
    command = PlanCommand(name=item.name, quantity=recommendation.suggested_quantity, unit=recommendation.unit)
    basis = PlanningBasis(item_key=item.item_key, item_version=item.version,
        batch_versions={b.id: b.version for b in item.batches}, shopping_version=snapshot.shopping_version,
        event_watermark=snapshot.event_watermark, snapshot_id=snapshot.snapshot_id, as_of=snapshot.as_of,
        preference_version=item.preferences.version, calculation=recommendation,
        original_suggested_quantity=recommendation.suggested_quantity)
    return command, basis
