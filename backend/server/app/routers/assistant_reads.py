"""Authenticated, read-only summaries and post-commit feedback adapters."""
from uuid import UUID
import asyncio
import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.assistant_read_schemas import OperationFeedback, SharedOperationSummary, CompatibilityPage
from app.dependencies import Identity, get_db, get_identity
from app.execution_models import BusinessEvent, DraftOperation
from app.models import AITask, InventoryItem
from app.routers.agent_gateway import check_config
from app.services import draft_execution as service
from app.services.ai_inventory import IncompatibleInventory, to_p1_batch

router = APIRouter(tags=["Assistant read adapters"])
DISPLAY_FIELDS = {"name", "quantity", "unit", "storage_location", "opened_at", "status", "version",
                  "purchased_on", "expires_on", "is_checked", "source_inventory_item_id"}


@router.get("/api/v1/households/{household_id}/inventory-ai-compatibility", response_model=CompatibilityPage)
def inventory_compatibility(household_id: UUID, response: Response,
                            limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                            identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    service.membership(db, identity.user.id, household_id)
    filters = [InventoryItem.household_id == household_id]
    total = db.scalar(select(func.count()).select_from(InventoryItem).where(*filters))
    rows = db.scalars(select(InventoryItem).where(*filters).order_by(InventoryItem.id).limit(limit).offset(offset)).all()
    issues = []
    for item in rows:
        try:
            to_p1_batch(item)
        except IncompatibleInventory as error:
            message = str(error)
            field = next((k for k in ("name", "unit", "quantity", "location") if k in message.lower()), "lifecycle")
            issues.append({"batch_id": item.id, "inventory_version": item.version, "field": field, "message": message})
    response.headers["Cache-Control"] = "no-store"
    return CompatibilityPage(issues=issues, total=total, scanned_count=len(rows), limit=limit, offset=offset,
        next_offset=offset+len(rows) if offset+len(rows) < total else None, page_compatible=not issues)


@router.get("/api/v1/households/{household_id}/operations/{operation_id}/summary", response_model=SharedOperationSummary)
def shared_summary(household_id: UUID, operation_id: UUID, response: Response,
                   identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    service.membership(db, identity.user.id, household_id)
    row = db.execute(select(DraftOperation, BusinessEvent).join(BusinessEvent,
        BusinessEvent.operation_id == DraftOperation.id).where(DraftOperation.id == operation_id,
        DraftOperation.household_id == household_id, BusinessEvent.household_id == household_id)).one_or_none()
    if row is None:
        service.fail("OPERATION_NOT_FOUND", 404)
    operation, event = row
    response.headers["Cache-Control"] = "no-store"
    return SharedOperationSummary(operation_id=operation.id, household_id=household_id,
        actor_user_id=event.actor_user_id, action=operation.action, event_id=event.id, event_type=event.event_type,
        inventory_item_id=event.inventory_item_id, shopping_item_id=event.shopping_item_id,
        name=(event.after_json or {}).get("name") or (event.before_json or {}).get("name"),
        quantity=event.quantity, unit=event.unit, occurred_at=event.occurred_at,
        before={k:v for k,v in (event.before_json or {}).items() if k in DISPLAY_FIELDS},
        after={k:v for k,v in (event.after_json or {}).items() if k in DISPLAY_FIELDS})


@router.post("/api/v1/operations/{operation_id}/feedback", response_model=OperationFeedback)
async def operation_feedback(operation_id: UUID, response: Response,
                             identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    operation = service.operation_for(db, identity, operation_id)
    user_id, household_id = identity.user.id, operation.household_id
    receipt = operation.receipt_json
    task = db.get(AITask, UUID(receipt["task_id"]))
    if task is None:
        service.fail("TASK_NOT_FOUND", 404)
    timezone = task.household_timezone
    response.headers["Cache-Control"] = "no-store"
    if operation.action == "PLAN_ADD":
        return OperationFeedback(operation_id=operation_id, feedback_status="not_applicable",
            reason_code="INVENTORY_FEEDBACK_NOT_APPLICABLE",
            message="已加入待购清单，尚未购买或入库；该操作没有库存变更反馈。")
    # No connection/locks held while AI reads back through the internal adapter.
    db.rollback()
    result, code = None, "POST_COMMIT_FEEDBACK_UNAVAILABLE"
    try:
        url, token = check_config()
        async with asyncio.timeout(10), httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0),
                                     trust_env=False, follow_redirects=False) as client:
            res = await client.post(url+"/feedback/after-commit", json={"operation_id": str(operation_id),
                "household_timezone": timezone}, headers={"Authorization": "Bearer "+token,
                "X-User-Id": str(user_id), "X-Household-Id": str(household_id)})
        data = res.json() if res.status_code == 200 else None
        feedback = data.get("feedback") if isinstance(data, dict) else None
        if (isinstance(data, dict) and data.get("status") == "answered" and data.get("inventory_writes") is False
                and data.get("shopping_writes") is False and data.get("draft") is None
                and isinstance(feedback, dict) and feedback.get("operation_id") == str(operation_id)
                and feedback.get("business_committed") is True):
            result = data
    except (httpx.HTTPError, ValueError, HTTPException, TimeoutError):
        pass  # Read failure never changes or repeats the committed operation.
    service.membership(db, user_id, household_id)
    partial = bool(result and (result["feedback"].get("refresh_required") or result.get("data_gaps") or
        any(isinstance(section, dict) and section.get("status") != "available" for section in (result.get("sections") or []))))
    return OperationFeedback(operation_id=operation_id,
        feedback_status=("partial" if partial else "available") if result else "unavailable",
        reason_code=None if result else code, result=result,
        message="业务已成功，以下为只读反馈。" if result else "业务已成功；AI 反馈暂不可用，请查询原回执，不要重复提交。")
