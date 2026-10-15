"""Known-at-cutoff event netting; no name matching and no inferred ledger."""
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from p0.domain import DomainError, convert
from .schemas import ConsumptionSummary


def consumption(item, snapshot, timezone, window_days=28):
    zone = ZoneInfo(timezone)
    end = snapshot.as_of.astimezone(zone).date()
    start = end - timedelta(days=window_days)
    reasons, excluded = [], 0
    coverage = {}
    for row in item.coverage:
        if row.day in coverage and coverage[row.day] != row:
            reasons.append("COVERAGE_CONFLICT")
        coverage[row.day] = row
    # Most recent consecutive fully observed calendar days. A gap is never
    # treated as a zero-consumption day; today is always excluded.
    cursor = end - timedelta(days=1)
    valid_days = 0
    while cursor >= start:
        day = coverage.get(cursor)
        if not day or not day.records_complete or day.stockout or day.unexplained_adjustment:
            break
        valid_days += 1
        cursor -= timedelta(days=1)
    start = end - timedelta(days=valid_days)
    boundary = coverage.get(cursor)
    if valid_days < 14 and boundary and (boundary.stockout or boundary.unexplained_adjustment):
        reasons.append("UNEXPLAINED_STOCKOUT_OR_ADJUSTMENT")
    if not snapshot.history_complete or snapshot.next_cursor:
        reasons.append("HISTORY_TRANSPORT_INCOMPLETE")
    if not item.recording_completeness_source:
        reasons.append("RECORDING_COMPLETENESS_UNKNOWN")
    known = {}
    for event in item.events:
        if event.item_key != item.item_key:
            reasons.append("EVENT_ITEM_CONFLICT")
            continue
        if event.recorded_at > snapshot.as_of:
            excluded += 1
            continue
        if event.id in known and known[event.id] != event:
            reasons.append("EVENT_ID_CONFLICT")
        known[event.id] = event
    known = {key: e for key, e in known.items() if e.committed}
    quantities, originals = {}, {}
    for event in sorted(known.values(), key=lambda e: (e.recorded_at, e.id)):
        if event.occurred_at > snapshot.as_of:
            reasons.append("FUTURE_OCCURRED_EVENT")
            continue
        try:
            if event.kind == "Consumed":
                if event.related_event_id or event.quantity <= 0:
                    reasons.append("INVALID_CONSUMPTION_EVENT")
                    continue
                quantities[event.id] = convert(event.quantity, event.unit, item.unit)
                originals[event.id] = event
            elif event.kind in {"Reversed", "Corrected"}:
                target = originals.get(event.related_event_id)
                # References to reversals, missing targets or future known
                # targets are not guessed. A correction replaces total usage.
                if target is None or target.recorded_at >= event.recorded_at:
                    reasons.append("UNRESOLVED_EVENT_RELATION")
                    continue
                amount = convert(event.quantity, event.unit, item.unit)
                previous = quantities[target.id]
                if event.kind == "Corrected":
                    quantities[target.id] = amount
                else:
                    amount = previous if event.quantity == 0 else amount
                    if amount > previous:
                        reasons.append("REVERSAL_EXCEEDS_CONSUMPTION")
                    else:
                        quantities[target.id] = previous - amount
            else:
                excluded += 1
        except DomainError:
            reasons.append("EVENT_UNIT_CONFLICT")
    rows = [(key, q) for key, q in quantities.items()
            if start <= originals[key].occurred_at.astimezone(zone).date() < end and q > 0]
    total = sum((q for _, q in rows), Decimal(0))
    dates = {originals[key].occurred_at.astimezone(zone).date() for key, _ in rows}
    quality_reasons = list(dict.fromkeys(reasons))
    conflicts = [r for r in quality_reasons if r != "RECORDING_COMPLETENESS_UNKNOWN"]
    status = "needs_review" if conflicts else "insufficient_data" if quality_reasons else "complete"
    if not valid_days:
        quality_reasons.append("NO_COMPLETE_COVERAGE_DAYS")
        if status == "complete":
            status = "insufficient_data"
    return ConsumptionSummary(item_key=item.item_key, name=item.name, unit=item.unit,
        window_start=start, window_end_exclusive=end, observed_days=valid_days,
        effective_quantity=total, effective_events=len(rows), consumption_dates=len(dates),
        status=status, reason_codes=quality_reasons, excluded_events=excluded,
        event_ids=[key for key, _ in rows])
