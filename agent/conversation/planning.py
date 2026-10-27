"""P8.3 backend adapter. Fresh GETs only; no execution tools or model calls."""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo
import httpx

from p0.domain import DomainError, convert
from p1.tools import check_scope
from p3.tools import validate_scope
from v1.schemas import PlanningSnapshot
from v1.tools import Reader as LegacyReader, RemoteReader as LegacyRemoteReader
from .planning_schemas import BackendSnapshot, Provenance, ProductPlanning, PlanningContext, PlanningReview

KINDS = {"StockAdded":"Added", "Created":"Added", "StockMoved":"Moved", "Consumed":"Consumed",
         "Opened":"Opened", "Discarded":"Discarded", "Purchased":"Purchased", "Adjusted":"Adjusted",
         "Edited":"Adjusted", "Corrected":"Adjusted", "ProductLinked":"Adjusted", "Archived":"Adjusted"}


def invalid():
    raise DomainError("PLANNING_CONTRACT_INVALID", "规划事实、商品映射或版本不一致，请联系后端核对。", 503)


class RemoteReader(LegacyRemoteReader):
    async def planning_context(self, scope, *, name=None, item_key=None):
        # Product metadata is household-wide. Read one complete MVCC envelope,
        # then select locally; never join individually fetched batch snapshots.
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
                response = await client.get(self.base_url+"/internal/v1/planning/context", headers={
                    "Authorization":"Bearer "+self.token, "X-User-Id":scope.user_id,
                    "X-Household-Id":scope.household_id})
            if response.status_code == 404:
                raise DomainError("PLANNING_CONTEXT_UNAVAILABLE", "没有可访问的规划资料，请手动核对。", 503)
            response.raise_for_status()
            envelope = response.json()
            data = envelope["data"]
            # Authorize before exposing any diagnostics from a foreign response.
            if data.get("scope") != scope.model_dump():
                raise DomainError("HOUSEHOLD_FORBIDDEN", "规划数据不属于当前用户或家庭。", 403)
            if "provenance" not in envelope:
                result = PlanningSnapshot.model_validate(data)
            else:
                result = BackendSnapshot.model_validate({**data, "provenance":envelope["provenance"]})
            validate_scope(result, scope)
            return result
        except DomainError:
            raise
        except httpx.HTTPError:
            raise DomainError("TOOL_UNAVAILABLE", "规划服务暂不可用，请保留原文并手动核对。", 503) from None
        except (ValueError, TypeError, KeyError):
            invalid()


def checked_snapshot(raw, scope):
    """Validate the two representations before accepting aggregate quantities."""
    validate_scope(raw, scope)
    p, basis = raw.provenance, raw.provenance.revalidation_basis
    if (basis.snapshot_id, basis.event_watermark, basis.shopping_version) != (raw.snapshot_id, raw.event_watermark, raw.shopping_version):
        invalid()
    if p.risk_rules != basis.risk_rules:
        invalid()
    batches = {b.id:b for item in raw.items for b in item.batches}
    if basis.inventory_versions != {b.id:b.version for b in batches.values()}:
        invalid()
    if set(basis.facts_versions) != set(batches):
        invalid()
    if ((p.pending_state == "none" and (p.pending_count != 0 or not raw.pending_complete))
        or (p.pending_state == "linked_complete" and (p.pending_count == 0 or not raw.pending_complete))
        or (p.pending_state in {"association_unknown", "shopping_list_missing"} and raw.pending_complete)):
        invalid()
    pending_by_id = {}
    for row in raw.pending:
        if not row.confirmed or row.status not in {"pending", "purchased"}: invalid()
        if row.id in pending_by_id and pending_by_id[row.id] != row: invalid()
        pending_by_id[row.id] = row
    raw.pending = list(pending_by_id.values())
    known_pending = {row.id for row in raw.pending if row.status == "pending"}
    if len(known_pending) > p.pending_count or (raw.pending_complete and len(known_pending) != p.pending_count):
        invalid()
    products, mapped = set(), set()
    for product in p.product_aggregates_v1:
        try: UUID(product.product_id)
        except (ValueError, TypeError): invalid()
        if product.product_id in products or product.item_key != "product:"+product.product_id:
            invalid()
        products.add(product.product_id)
        if basis.product_versions.get(product.product_id) != product.version:
            invalid()
        total = eligible = Decimal(0)
        complete = True
        for row in product.batches:
            batch = batches.get(row.batch_id)
            if batch is None or row.batch_id in mapped or batch.product_id != product.product_id:
                invalid()
            mapped.add(row.batch_id)
            if (row.version, row.quantity, row.unit, row.status, row.location, row.label_expiry, row.opened_at) != (
                    batch.version, batch.quantity, batch.unit, batch.status, batch.location, batch.label_expiry, batch.opened_at):
                invalid()
            if row.expiry_known != (row.label_expiry is not None) or row.facts_version != basis.facts_versions[row.batch_id]:
                invalid()
            try: amount = convert(row.quantity, row.unit, product.base_unit)
            except DomainError: amount = None
            # Backend permits at most six decimal places for each conversion.
            if amount is not None and (amount > 1_000_000_000 or amount.normalize().as_tuple().exponent < -6): amount = None
            if row.base_quantity != amount: invalid()
            complete &= amount is not None
            if amount is not None:
                total += amount
                if row.status == "ACTIVE" and not row.expired: eligible += amount
        if (product.quantity_complete != complete or product.total_quantity != (total if complete else None)
                or product.nonexpired_active_quantity != (eligible if complete else None)):
            invalid()
    if set(basis.product_versions) != products or any(b.product_id is not None and b.id not in mapped for b in batches.values()):
        invalid()
    seen = set()
    for source in p.events.values():
        if source.get("household_id") != scope.household_id or source.get("relation_support") != "inventory-ledger-1":
            invalid()
        if source.get("batch_id") is not None and source["batch_id"] not in batches: invalid()
    # The deployed backend projects inventory Corrected to Adjusted, never to
    # legacy consumption replacement. Enforce that even for a mismatched kind.
    for item in raw.items:
        for event in item.events:
            source = p.events.get(event.id)
            if event.id in seen or source is None: invalid()
            seen.add(event.id)
            if source.get("batch_id") not in {b.id for b in item.batches}: invalid()
            kind = KINDS.get(source.get("event_type"))
            if kind is None or datetime.fromisoformat(source.get("occurred_at")) != event.occurred_at or datetime.fromisoformat(source.get("recorded_at")) != event.recorded_at:
                invalid()
            if event.quantity != Decimal(source.get("quantity") or 0) or event.unit != source.get("unit") or not event.committed:
                invalid()
            if source.get("event_type") == "Consumed" and (event.related_event_id or event.quantity <= 0): invalid()
            if kind != event.kind and not (kind == "Adjusted" and event.kind == "Corrected"): invalid()
            event.kind = kind
    expected = {key for key, source in p.events.items() if source.get("event_type") in KINDS and source.get("batch_id") is not None}
    if seen != expected: invalid()
    return raw


class Reader(LegacyReader):
    def __init__(self, *args):
        super().__init__(*args)
        self.backend_snapshots = {}

    async def read_planning_snapshot(self, scope, *, name=None, item_key=None):
        raw = await self.delegate.planning_context(scope, name=name, item_key=item_key)
        if not isinstance(raw, BackendSnapshot):
            return raw  # Frozen P0-P6 fixtures and old backend data stay valid.
        try: raw = checked_snapshot(raw.model_copy(deep=True), scope)
        except (ValueError, TypeError, InvalidOperation): invalid()
        self.backend_snapshots[(scope.user_id, scope.household_id, name, item_key)] = raw
        value = raw.model_dump(exclude={"provenance"})
        # Local projection keeps original batch IDs and versions. Explicit
        # product selectors are answered by product_query, not relabelled data.
        if item_key and item_key.startswith("product:"):
            ids = {b.batch_id for p in raw.provenance.product_aggregates_v1 if p.item_key == item_key for b in p.batches}
            value["items"] = [i for i in value["items"] if any(b["id"] in ids for b in i["batches"])]
            keys = {i["item_key"] for i in value["items"]}
            value["pending"] = [r for r in value["pending"] if r["item_key"] in keys]
        return PlanningSnapshot.model_validate(value)

    def enrich(self, result, *, timezone="Asia/Shanghai", window_days=28, product_selector=None, collapse=True):
        if not self.backend_snapshots or result.status not in {"answered", "needs_confirmation", "needs_clarification"}:
            return result
        # Every operation owns this cache. Prefer the last actual selector read.
        selector, snapshot = next(reversed(self.backend_snapshots.items()))
        p = snapshot.provenance
        result.planning_context = PlanningContext(pending_state=p.pending_state, pending_count=p.pending_count,
            pending_complete=snapshot.pending_complete, ledger_coverage=p.ledger_coverage, revalidation_basis=p.revalidation_basis.model_copy(deep=True))
        batch_selector = selector[3] and not selector[3].startswith("product:")
        if not snapshot.pending_complete:
            result.data_gaps = sorted(set([*result.data_gaps, "PENDING_ASSOCIATION_UNKNOWN"]))
            for row in result.recommendations:
                row.pending_quantity = row.suggested_quantity = None
                row.status = "excluded" if row.status == "excluded" else "needs_review"
                row.reason_codes = list(dict.fromkeys([*row.reason_codes, "PENDING_ASSOCIATION_UNKNOWN"]))
        if p.risk_rules.get("review_status") != "human_reviewed":
            result.data_gaps = sorted(set([*result.data_gaps, "HUMAN_RULE_REVIEW_REQUIRED"]))
            for row in result.recommendations:
                row.status = "excluded" if row.status == "excluded" else "needs_review"
                row.suggested_quantity = None
                row.reason_codes = list(dict.fromkeys([*row.reason_codes, "HUMAN_RULE_REVIEW_REQUIRED"]))
            if result.planning_basis:
                result.draft = result.preview = result.planning_basis = None
                result.status = "answered"
                result.reply = "平台规划快照缺少已审核规则，不能生成自动补货草稿。尚未写入。"
        if result.planning_basis:
            old = result.planning_basis
            result.planning_calculation = old
            result.planning_basis = p.revalidation_basis.model_copy(deep=True)
            candidates = [b for item in snapshot.items if item.item_key == old.item_key for b in item.batches]
            if len(candidates) == 1:
                from .schemas import ProcurementSource
                result.procurement_source = ProcurementSource(batch_id=candidates[0].id, expected_version=candidates[0].version)
            else:
                result.draft = result.preview = None
                result.status = "answered"
                result.data_gaps.append("PROCUREMENT_SOURCE_REQUIRED")
        if result.recommendations and not result.draft:
            # Text must describe the redacted structured values too. A prior
            # positive suggestion cannot survive a new provenance blocker.
            from v1.render import reply
            result.reply = reply(result)
        if not snapshot.pending_complete:
            result.reply += "\n待购关联不完整，待购量未知；请在采购清单修正来源，不能按零待购补货。"
        if result.intent not in {"QUERY_CONSUMPTION", "QUERY_FORECAST", "SUGGEST_PURCHASE", "QUERY_OVERVIEW"} or batch_selector:
            return result
        target_ids = {b.id for b in [*result.facts, *result.candidates]}
        name = selector[2]
        products = p.product_aggregates_v1
        if product_selector:
            products = [v for v in products if v.item_key == product_selector]
        elif target_ids:
            products = [v for v in products if any(b.batch_id in target_ids for b in v.batches)]
        elif name:
            products = [v for v in products if name.casefold() in v.name.casefold() or any(
                name.casefold() in b.name.casefold() for item in snapshot.items for b in item.batches if b.product_id == v.product_id)]
        result.product_planning = [product_report(v, snapshot, timezone, window_days) for v in products]
        # A read about a unique explicit product needs no arbitrary batch choice.
        unique_product = len(products) == 1 and ((target_ids and target_ids == {b.batch_id for b in products[0].batches})
            or (not target_ids and name and name.casefold() == products[0].name.casefold()))
        if collapse and result.status == "needs_clarification" and result.intent in {"QUERY_CONSUMPTION", "QUERY_FORECAST"} and unique_product:
            result.status = "answered"
            result.clarification = None
            result.missing_fields = []
            product_ids = {b.batch_id for b in products[0].batches}
            result.facts = [b for item in snapshot.items for b in item.batches if b.id in product_ids]
            result.candidates = []
            result.reply = "已按明确的商品关联汇总；商品整体预测依据不足，暂不提供耗尽日期。" if result.intent == "QUERY_FORECAST" else "已汇总明确关联批次的已登记消费；不代表完整实际消费。"
        if result.product_planning:
            descriptions = []
            for row in result.product_planning:
                product = row.product
                amount = str(product.total_quantity) if product.total_quantity is not None else "未知（单位不兼容）"
                descriptions.append(f"{product.name}（商品 {product.product_id}）：登记总量 {amount} {product.base_unit}，共 {len(product.batches)} 批；可用量、商品整体耗尽日期和自动补货量尚不可确定。")
                if result.intent == "QUERY_CONSUMPTION":
                    subtotal = row.recorded_consumption_quantity
                    descriptions.append(f"{row.window_start} 至 {row.window_end_exclusive}（不含结束日）的已登记消费小计 {subtotal} {product.base_unit}，不代表完整实际消费。" if subtotal is not None and subtotal > 0 else
                        "窗口内没有已登记消费事件，不能当作实际零消费。" if subtotal == 0 else "已登记消费单位或读取范围不完整，无法提供完整小计。")
            result.reply += "\n"+"\n".join(descriptions)+"\n商品及标签由家庭确认，不代表平台规则已审核。本次未写入。"
        return result


def product_report(product, snapshot, timezone, window_days):
    end = snapshot.as_of.astimezone(ZoneInfo(timezone)).date()
    start = end-timedelta(days=window_days)
    ids = {b.batch_id for b in product.batches}
    reasons = ["PRODUCT_USABLE_QUANTITY_UNKNOWN", "PRODUCT_COVERAGE_UNKNOWN", "PRODUCT_PREFERENCES_NOT_AGGREGATED", "HUMAN_RULE_REVIEW_REQUIRED"]
    if not product.quantity_complete: reasons.append("PRODUCT_UNIT_CONFLICT")
    if any(not b.expiry_known for b in product.batches): reasons.append("PRODUCT_EXPIRY_UNKNOWN")
    if any(b.expired for b in product.batches): reasons.append("PRODUCT_EXPIRED_BATCH_PRESENT")
    if any(b.status != "ACTIVE" for b in product.batches): reasons.append("PRODUCT_TERMINAL_BATCH_PRESENT")
    events, total, complete = [], Decimal(0), snapshot.history_complete
    for item in snapshot.items:
        for event in item.events:
            source = snapshot.provenance.events[event.id]
            if source["batch_id"] not in ids or source["event_type"] != "Consumed": continue
            if event.recorded_at > snapshot.as_of or event.occurred_at > snapshot.as_of: continue
            if not start <= event.occurred_at.astimezone(ZoneInfo(timezone)).date() < end: continue
            try: total += convert(event.quantity, event.unit, product.base_unit)
            except DomainError:
                complete = False
                reasons.append("EVENT_UNIT_CONFLICT")
            events.append(event.id)
    if not snapshot.history_complete: reasons.append("HISTORY_TRANSPORT_INCOMPLETE")
    pending = Decimal(0) if snapshot.pending_complete else None
    if pending is None: reasons.append("PENDING_ASSOCIATION_UNKNOWN")
    else:
        keys = {i.item_key for i in snapshot.items if any(b.id in ids for b in i.batches)}
        for row in snapshot.pending:
            if row.item_key in keys and row.confirmed and row.status == "pending":
                try: pending += convert(row.quantity, row.unit, product.base_unit)
                except DomainError:
                    pending = None
                    reasons.append("PENDING_UNIT_CONFLICT")
                    break
    return ProductPlanning(product=product.model_copy(deep=True), as_of=snapshot.as_of, window_start=start,
        window_end_exclusive=end, recorded_consumption_quantity=total if complete else None,
        recorded_consumption_event_ids=events, pending_quantity=pending, reason_codes=list(dict.fromkeys(reasons)))


def attach_review(result, request):
    if result.planning_context is None:
        if result.status != "error":
            result.status = "error"
            result.error_code = "PLANNING_REVALIDATION_UNAVAILABLE"
            result.reply = "后端未提供当前重验依据，不能核实旧建议；请保留原任务并手动核对。"
            result.manual_entry = True
        return result
    current = result.planning_context.revalidation_basis
    before, after = request.original_basis.model_dump(), current.model_dump()
    changes = [key for key in before if before[key] != after[key]]
    if request.diagnostic and request.diagnostic.current_basis != current:
        changes.append("diagnostic_snapshot_changed")
    blockers = ["AUTOMATIC_PLANNING_NOT_APPROVED"]
    if current.risk_rules.get("review_status") != "human_reviewed": blockers.append("RISK_RULE_REVIEW_REQUIRED")
    if not result.planning_context.pending_complete: blockers.append("PENDING_ASSOCIATION_UNKNOWN")
    blockers.extend(result.data_gaps)
    if request.diagnostic:
        changes.extend(request.diagnostic.mismatches)
        blockers.extend(request.diagnostic.blockers)
    stale = bool(changes or (request.diagnostic and request.diagnostic.status == "stale"))
    result.planning_review = PlanningReview(status="stale" if stale else "blocked", mismatches=list(dict.fromkeys(changes)),
        blockers=sorted(set(blockers)), original_basis=request.original_basis, current_basis=current)
    result.reply += "\n"+("原建议已失效，已重新读取并生成只读建议；请重新核对。" if stale else "已重新核对当前依据，自动建议提交仍未开放。")
    if stale: result.error_code = "PLANNING_BASIS_STALE"
    result.draft = result.preview = None
    return result
