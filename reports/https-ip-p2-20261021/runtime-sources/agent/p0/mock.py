"""In-memory business-backend substitute, never a production persistence claim."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from threading import RLock

from .domain import DomainError, convert, new_id, normalize_command, normalize_unit
from .schemas import Batch, Command, PlanUpdate, Scope


class MockBackend:
    def __init__(self):
        self.lock = RLock()
        self.fail_event_once = False
        self.reset()

    def reset(self):
        with self.lock:
            self.state = {"batches": {}, "drafts": {}, "events": [], "requests": {}, "plans": {}}
            seeds = [
                ("milk-1", "h1", "牛奶", "2", "盒", "冰箱上层"),
                ("milk-2", "h1", "牛奶", "3", "盒", "冰箱下层"),
                ("bandage-1", "h1", "创可贴", "10", "片", "客厅/医药箱"),
                ("detergent-1", "h1", "洗衣液", "500", "ml", None),
                ("tissue-0", "h1", "纸巾", "0", "包", "储物柜"),
                ("private-1", "h2", "大米", "2", "kg", "厨房"),
            ]
            for batch_id, home, name, qty, unit, location in seeds:
                self.state["batches"][batch_id] = Batch(id=batch_id, household_id=home, name=name,
                    quantity=Decimal(qty), unit=unit, location=location, version=1,
                    status="ACTIVE" if Decimal(qty) else "FINISHED")

    def atomic(self, operation):
        with self.lock:
            before = deepcopy(self.state)
            try:
                return deepcopy(operation())
            except Exception:
                self.state = before
                raise

    def batch(self, scope: Scope, batch_id: str) -> Batch:
        batch = self.state["batches"].get(batch_id)
        if batch is None or batch.household_id != scope.household_id:
            raise DomainError("BATCH_NOT_FOUND", "批次不存在或不可访问。", 404)
        return batch

    async def search(self, scope: Scope, name: str | None) -> list[Batch]:
        with self.lock:
            return [b.model_copy(deep=True) for b in self.state["batches"].values()
                    if b.household_id == scope.household_id and b.status != "REVERSED" and (not name or name in b.name)]

    def validate(self, scope: Scope, command: Command) -> Command:
        command = normalize_command(command)
        if command.action == "CONSUME":
            batch = self.batch(scope, command.batch_id)
            if batch.version != command.expected_version:
                raise DomainError("VERSION_CONFLICT", "库存已变化，请重新核对并确认。", 409)
            if batch.status != "ACTIVE":
                raise DomainError("INVALID_STATE_TRANSITION", "批次已结束，不能继续消耗。", 409)
            if command.name != batch.name:
                raise DomainError("VALIDATION_ERROR", "名称与选择的批次不一致。")
            quantity = convert(command.quantity, command.unit, batch.unit)
            if quantity > batch.quantity:
                raise DomainError("INSUFFICIENT_STOCK", "扣减量超过库存。")
            command = command.model_copy(update={"quantity": quantity, "unit": batch.unit})
        return command

    def create_draft(self, scope: Scope, command: Command, trace_id: str):
        def operation():
            command_checked = self.validate(scope, command)
            draft = {"id": new_id("draft"), "household_id": scope.household_id, "revision": 1,
                     "status": "DRAFT", "command": command_checked.model_dump(mode="json"), "trace_id": trace_id}
            self.state["drafts"][draft["id"]] = draft
            return draft
        return self.atomic(operation)

    def draft(self, scope: Scope, draft_id: str):
        draft = self.state["drafts"].get(draft_id)
        if not draft or draft["household_id"] != scope.household_id:
            raise DomainError("DRAFT_NOT_FOUND", "草稿不存在或不可访问。", 404)
        return draft

    def edit_draft(self, scope: Scope, draft_id: str, revision: int, command: Command):
        def operation():
            draft = self.draft(scope, draft_id)
            self.check_draft(draft, revision)
            draft["command"] = self.validate(scope, command).model_dump(mode="json")
            draft["revision"] += 1
            return draft
        return self.atomic(operation)

    @staticmethod
    def check_draft(draft, revision):
        if draft["status"] != "DRAFT":
            raise DomainError("DRAFT_CLOSED", "草稿已确认或取消。", 409)
        if draft["revision"] != revision:
            raise DomainError("DRAFT_CONFLICT", "草稿已编辑，请确认最新版本。", 409)

    def cancel_draft(self, scope: Scope, draft_id: str):
        def operation():
            draft = self.draft(scope, draft_id)
            self.check_draft(draft, draft["revision"])
            draft["status"] = "CANCELLED"
            return draft
        return self.atomic(operation)

    def once(self, scope: Scope, key: str, payload: dict, operation):
        if not key or len(key) > 128:
            raise DomainError("IDEMPOTENCY_REQUIRED", "提交需要 1–128 字符的幂等键。")
        identity = f"{scope.household_id}:{scope.user_id}:{key}"
        fingerprint = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        def run():
            previous = self.state["requests"].get(identity)
            if previous:
                if previous["hash"] != fingerprint:
                    raise DomainError("IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同操作。", 409)
                return previous["result"]
            result = operation()
            self.state["requests"][identity] = {"hash": fingerprint, "result": deepcopy(result)}
            return result
        return self.atomic(run)

    def append_event(self, event):
        if self.fail_event_once:
            self.fail_event_once = False
            raise DomainError("TRANSACTION_FAILED", "模拟事件写入失败，库存操作已回滚。", 503)
        self.state["events"].append(event)

    def confirm(self, scope: Scope, draft_id: str, revision: int, key: str):
        def operation():
            draft = self.draft(scope, draft_id)
            self.check_draft(draft, revision)
            command = self.validate(scope, Command.model_validate(draft["command"]))
            if command.action == "PLAN_ADD":
                plan = self.current_plan(scope)
                if plan["status"] == "CONFIRMED":
                    self.state["plans"].pop(scope.household_id)
                    plan = self.current_plan(scope)
                plan["items"].append({"name": command.name, "quantity": str(command.quantity), "unit": command.unit})
                plan["revision"] += 1
                draft["status"] = "CONFIRMED"
                return {"plan": plan, "draft_id": draft_id, "trace_id": draft["trace_id"]}
            before = None
            if command.action == "ADD":
                batch = Batch(id=new_id("batch"), household_id=scope.household_id, name=command.name,
                              quantity=command.quantity, unit=command.unit, location=command.location,
                              purchased_at=command.purchased_at, label_expiry=command.label_expiry, version=1)
                self.state["batches"][batch.id] = batch
                delta, event_type = command.quantity, "Added"
            else:
                batch = self.batch(scope, command.batch_id)
                before = batch.model_dump(mode="json")
                batch.quantity -= command.quantity
                batch.version += 1
                if batch.quantity == 0:
                    batch.status = "FINISHED"
                delta, event_type = -command.quantity, "Consumed"
            event = {"id": new_id("event"), "batch_id": batch.id, "household_id": scope.household_id,
                     "type": event_type, "quantity_delta": str(delta), "unit": batch.unit,
                     "before": before, "after": batch.model_dump(mode="json"), "actor_id": scope.user_id,
                     "request_id": key, "trace_id": draft["trace_id"], "source": "mock",
                     "created_at": datetime.now(timezone.utc).isoformat(), "original_event_id": None}
            self.append_event(event)
            draft["status"] = "CONFIRMED"
            return {"batch": batch.model_dump(mode="json"), "event": event, "draft_id": draft_id, "trace_id": draft["trace_id"]}
        return self.once(scope, key, {"operation": "confirm", "id": draft_id, "revision": revision}, operation)

    def events(self, scope: Scope):
        with self.lock:
            return deepcopy([e for e in self.state["events"] if e["household_id"] == scope.household_id])

    def undo(self, scope: Scope, event_id: str, expected_version: int, key: str):
        def operation():
            event = next((e for e in self.state["events"] if e["id"] == event_id and e["household_id"] == scope.household_id), None)
            if not event:
                raise DomainError("EVENT_NOT_FOUND", "事件不存在或不可访问。", 404)
            batch = self.batch(scope, event["batch_id"])
            latest = [e for e in self.state["events"] if e["batch_id"] == batch.id][-1]
            if latest["id"] != event_id or event["type"] == "Correction":
                raise DomainError("UNDO_NOT_LATEST", "存在后续变更或已撤销，请核对库存。", 409)
            if batch.version != expected_version or batch.version != event["after"]["version"]:
                raise DomainError("VERSION_CONFLICT", "库存已变化，请重新核对。", 409)
            before = batch.model_dump(mode="json")
            if event["before"] is None:
                restored = batch.model_copy(update={"quantity": Decimal(0), "status": "REVERSED", "version": batch.version + 1})
            else:
                restored = Batch.model_validate(event["before"]).model_copy(update={"version": batch.version + 1})
            self.state["batches"][batch.id] = restored
            correction = {**event, "id": new_id("event"), "type": "Correction", "original_event_id": event_id,
                          "quantity_delta": str(restored.quantity - batch.quantity), "before": before,
                          "after": restored.model_dump(mode="json"), "request_id": key,
                          "trace_id": new_id("trace"), "actor_id": scope.user_id,
                          "created_at": datetime.now(timezone.utc).isoformat()}
            self.append_event(correction)
            return {"batch": restored.model_dump(mode="json"), "event": correction, "trace_id": correction["trace_id"]}
        return self.once(scope, key, {"operation": "undo", "id": event_id, "version": expected_version}, operation)

    def current_plan(self, scope: Scope):
        with self.lock:
            if scope.household_id not in self.state["plans"]:
                self.state["plans"][scope.household_id] = {"id": new_id("plan"), "revision": 1, "status": "DRAFT", "items": []}
            return self.state["plans"][scope.household_id]

    def update_plan(self, scope: Scope, update: PlanUpdate):
        def operation():
            plan = self.current_plan(scope)
            if plan["status"] != "DRAFT" or update.revision != plan["revision"]:
                raise DomainError("PLAN_CONFLICT", "采购清单已变化或已确认。", 409)
            plan["items"] = [{**item.model_dump(mode="json"), "unit": normalize_unit(item.unit)} for item in update.items]
            plan["revision"] += 1
            return plan
        return self.atomic(operation)

    def confirm_plan(self, scope: Scope, revision: int, key: str):
        def operation():
            plan = self.current_plan(scope)
            if plan["status"] != "DRAFT" or plan["revision"] != revision:
                raise DomainError("PLAN_CONFLICT", "请确认最新采购清单。", 409)
            plan["status"] = "CONFIRMED"
            plan["revision"] += 1
            return plan
        return self.once(scope, key, {"operation": "confirm-plan", "revision": revision}, operation)
