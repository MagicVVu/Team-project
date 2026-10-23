"""P8 literal draft controls. Business validation stays in draft_execution."""
import re
from decimal import Decimal
from uuid import UUID
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.models import AIDraft
from app.conversation_models import ConversationBinding
from app.execution_models import DraftDecision
from app.execution_schemas import DraftRevision
from app.services import draft_execution as execution
from app.routers.agent_gateway import owned_task


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000, pattern=r"\S")
    task_revision: int = Field(ge=1, strict=True)
    draft_revision: int = Field(ge=1, strict=True)
    edits: dict[str, str | None] = Field(default_factory=dict, max_length=9)


class ControlPreview(BaseModel):
    command: dict[str, Any]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    prospective: Literal[True] = True
    inventory_written: Literal[False] = False


class ControlResponse(BaseModel):
    protocol_version: Literal["p8-chat-control-1"] = "p8-chat-control-1"
    kind: Literal["edit", "cancel", "needs_input", "not_control"]
    task_id: UUID
    draft_id: UUID
    task_revision: int
    draft_revision: int
    edits: dict[str, str | None]
    preview: ControlPreview | None
    reply: str
    inventory_written: Literal[False] = False
    model_calls: Literal[0] = 0


def literal_edits(text, action):
    text = text.strip().rstrip("。！! ")
    if text == "校验草稿": return "edit", {}
    if text in {"算了", "不用了", "取消草稿", "取消这次任务", "取消这次操作", "先不做了"}:
        return "cancel", {}
    amount = re.fullmatch(r"(?:数量)?改(?:成|为)\s*([0-9]+(?:\.[0-9]+)?|[一二两三四五六七八九十])\s*(盒|瓶|包|袋|个|台|吨|千克|公斤|毫升|克|升|kg|g|ml|mL|L)?", text)
    if amount:
        value = amount[1]
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
            value = str({"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}[value])
        edits = {"quantity":value}
        if amount[2]: edits["unit"] = amount[2]
        return "edit", edits
    place = re.fullmatch(r"(?:位置改(?:成|为)|改放到|改放在)([^，,；;。！？!?]{1,100})", text)
    if place and action in {"ADD", "MOVE"}:
        if re.search(r"然后|同时|并且|忽略|直接执行|删除|丢弃|消耗", place[1]):
            return "needs_input", {}
        return "edit", {"to_location" if action == "MOVE" else "location":place[1].strip()}
    date = re.fullmatch(r"开封日期改(?:成|为)(今天|昨天|\d{4}-\d{2}-\d{2})", text)
    if date and action == "OPEN": return "edit", {"opened_at":date[1]}
    if re.match(r"(?:改成|改为|换成|修改|取消|算了|不用了|数量改|位置改|开封日期改|改放)", text):
        return "needs_input", {}
    return "not_control", {}


def handle(db, identity, task_id, body):
    # Owned task/household checked before any text-dependent response.
    task = owned_task(db, task_id, identity)
    draft = db.scalar(select(AIDraft).where(AIDraft.task_id == task.id))
    if draft is None: execution.fail("DRAFT_NOT_FOUND", 404)
    task, draft = execution.owned(db, identity, draft.id, lock=True)
    execution.revision(task, draft, body)
    action = (draft.command_json or {}).get("action")
    kind, new_edits = literal_edits(body.text, action)
    result = {"protocol_version":"p8-chat-control-1", "kind":kind, "task_id":str(task.id),
              "draft_id":str(draft.id), "task_revision":task.revision, "draft_revision":draft.revision,
              "edits":{}, "preview":None, "inventory_written":False, "model_calls":0}
    if kind == "cancel":
        cursor = db.scalar(select(ConversationBinding).where(ConversationBinding.user_id == identity.user.id).with_for_update())
        matching = cursor is not None and cursor.task_id == task.id and cursor.household_id == task.household_id and cursor.session_id == identity.session_id
        # A running continuation must finish/recover first. Otherwise its finalizer
        # could restore a binding just detached by cancellation.
        if matching and cursor.processing_nonce is not None:
            execution.fail("CONVERSATION_PROCESSING")
        execution.cancel(db, identity, draft.id, DraftRevision(task_revision=task.revision, draft_revision=draft.revision))
        if matching:
            cursor.task_id = None; cursor.reference_json = None
        result["reply"] = "这份草稿已取消，库存没有变动。可以开始新任务。"
    elif kind == "edit":
        if db.get(DraftDecision, draft.id) is not None: execution.fail("DRAFT_ALREADY_DECIDED")
        execution.pending(task, draft)
        if execution.expiry(task, draft) <= execution.now(): execution.fail("DRAFT_EXPIRED")
        edits = {**body.edits, **new_edits}
        action, target, fields, command = execution.command(task, draft, edits)
        before = after = None
        if target is not None:
            item = execution.target_item(db, draft.household_id, target)
            _, changes = execution.stock_changes(action, fields, item, command)
            before = execution.StockResponse.model_validate(item).model_dump(mode="json")
            after = {**before, **{k:str(v) if isinstance(v, Decimal) else v.isoformat() if hasattr(v, "isoformat") else v for k,v in changes.items()}}
        # No draft/stock mutation: edits must accompany the later explicit commit.
        result.update(edits=edits, preview={"command":command,"before":before,"after":after,
                      "prospective":True,"inventory_written":False},
                      reply="修改内容已校验，请核对更新后的草稿。尚未执行，需要你确认。")
    elif kind == "needs_input":
        result["reply"] = "可以说“改成三盒”“位置改成冰箱”或“取消草稿”。更换物品、动作或丢弃模式，请开始新任务。"
    else: result["reply"] = ""
    return result
