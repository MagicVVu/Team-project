from datetime import timedelta
from decimal import Decimal, ROUND_CEILING
from zoneinfo import ZoneInfo

from p0.domain import DomainError, convert
from .history import consumption
from .schemas import Forecast


def current_stock(item):
    total = Decimal(0)
    ids = set()
    for batch in item.batches:
        if batch.id in ids:
            raise DomainError("DUPLICATE_BATCH", "商品批次重复，请核对。")
        ids.add(batch.id)
        if batch.status == "ACTIVE":
            total += convert(batch.quantity, batch.unit, item.unit)
        elif batch.quantity != 0:
            raise DomainError("TERMINAL_BATCH_QUANTITY", "终态批次数量不为零，请核对。")
    if total > Decimal("1000000000"):
        raise DomainError("STOCK_OUT_OF_RANGE", "商品库存总量超过支持范围。")
    return total


def evaluate(item, snapshot, timezone, window_days=28):
    summary = consumption(item, snapshot, timezone, window_days)
    result = Forecast(item_key=item.item_key, name=item.name, unit=item.unit,
        status="insufficient_data", summary=summary, reason_codes=list(summary.reason_codes))
    try:
        result.current_stock = current_stock(item)
    except DomainError as error:
        result.status = "needs_review"
        result.reason_codes.append(error.code)
        return result
    if summary.status == "needs_review":
        result.status = "needs_review"
        return result
    if result.current_stock == 0:
        result.status = "current_zero"
        result.reason_codes.append("CURRENT_RECORDED_STOCK_ZERO")
        return result
    if summary.status == "insufficient_data":
        return result
    if summary.observed_days < 14:
        result.reason_codes.append("FEWER_THAN_14_COMPLETE_DAYS")
        return result
    if summary.effective_quantity == 0:
        result.status = "no_recorded_consumption"
        result.reason_codes.append("NO_RECORDED_CONSUMPTION")
        return result
    if summary.effective_events < 5 or summary.consumption_dates < 3:
        result.reason_codes.append("TOO_FEW_CONSUMPTION_EVENTS_OR_DATES")
        return result
    rate = summary.effective_quantity / Decimal(summary.observed_days)
    # Divide once: stock / (1 / 21) must ceil to 21, not 22 after
    # rounding the repeating decimal rate first.
    days = result.current_stock * Decimal(summary.observed_days) / summary.effective_quantity
    # Keep arithmetic exact; date range overflow must degrade, never crash.
    try:
        result.reference_date = snapshot.as_of.astimezone(ZoneInfo(timezone)).date() + timedelta(days=int(days.to_integral_value(rounding=ROUND_CEILING)))
    except (OverflowError, ValueError):
        result.status = "needs_review"
        result.reason_codes.append("REFERENCE_DATE_OUT_OF_RANGE")
        return result
    result.status = "estimated"
    result.daily_recorded_consumption = rate
    result.remaining_days = days
    return result
