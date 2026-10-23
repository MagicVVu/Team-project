"""Authenticated confirmation and durable recovery; separate from the AI gateway."""
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.execution_models import BusinessEvent
from app.execution_schemas import CommitRequest, DraftRevision, ReferenceMessage, PreviewRequest, ExecutionPreview, OperationReceipt
from app.conversation_schemas import ConversationResponse
from app.routers.ai_inventory import _authorize
from app.services import draft_execution as service

router = APIRouter(tags=["Draft execution — business backend"])


@router.get("/api/v1/agent/execution-capabilities")
def capabilities(identity: Identity = Depends(get_identity)):
    from app.services.conversation import reference_enabled
    return {"protocol_version": "draft-execution-1", "owner": "business_backend",
            "actions": {"ADD": True, "MOVE": True, "PLAN_ADD": True, "CONSUME": True,
                        "OPEN": service.action_enabled("OPEN"), "DISCARD": service.action_enabled("DISCARD")},
            "automatic_planning_commit": False, "trusted_reference_messages": reference_enabled(),
            "manual_plan_only": True, "draft_ttl_seconds": 900,
            "inventory_quantity_decimal_places": 6, "shopping_quantity_decimal_places": 3,
            "location_max_length": 100}


@router.post("/api/v1/agent/reference-messages", response_model=ConversationResponse)
async def reference_message(body: ReferenceMessage, identity: Identity = Depends(get_identity),
                            db: Session = Depends(get_db)):
    from app.services.conversation import handle
    return await handle(body, identity, db, explicit_reference=True)


@router.get("/api/v1/drafts/{draft_id}/execution")
def execution(draft_id: UUID, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    return service.execution_status(db, identity, draft_id)


@router.post("/api/v1/drafts/{draft_id}/commit", responses={200: {"model": OperationReceipt}})
def commit(draft_id: UUID, body: CommitRequest, identity: Identity = Depends(get_identity),
           db: Session = Depends(get_db)):
    try:
        receipt = service.execute(db, identity, draft_id, body)
        db.commit()
        return receipt
    except IntegrityError:
        # A duplicate operation on another worker must roll back ALL local writes.
        db.rollback()
        try:
            receipt = service.recover(db, identity, draft_id, body)
            if receipt is None:
                service.fail("EXECUTION_CONFLICT")
            return receipt
        finally:
            db.rollback()
    except Exception:
        db.rollback()
        raise


@router.post("/api/v1/drafts/{draft_id}/execution-preview", response_model=ExecutionPreview)
def execution_preview(draft_id: UUID, body: PreviewRequest, identity: Identity = Depends(get_identity),
                      db: Session = Depends(get_db)):
    # Pure read: does not update draft/TTL, reserve an operation, or change business rows.
    return service.preview(db, identity, draft_id, body)


@router.post("/api/v1/drafts/{draft_id}/cancel")
def cancel(draft_id: UUID, body: DraftRevision, identity: Identity = Depends(get_identity),
           db: Session = Depends(get_db)):
    try:
        result = service.cancel(db, identity, draft_id, body)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.get("/api/v1/operations/{operation_id}", responses={200: {"model": OperationReceipt}})
def operation(operation_id: UUID, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    return service.operation_for(db, identity, operation_id).receipt_json


@router.get("/internal/v1/operations/{operation_id}")
def internal_operation(operation_id: UUID, household_id: UUID = Depends(_authorize),
                       x_user_id: str = Header(default=""), db: Session = Depends(get_db)):
    from app.execution_models import DraftOperation
    operation = db.scalar(select(DraftOperation).where(DraftOperation.id == operation_id,
        DraftOperation.user_id == UUID(x_user_id), DraftOperation.household_id == household_id))
    if operation is None:
        service.fail("OPERATION_NOT_FOUND", 404)
    receipt = operation.receipt_json
    if not receipt["batch_versions"]:
        # P6's inventory feedback schema requires real batch versions; a plan has none.
        service.fail("INVENTORY_RECEIPT_NOT_APPLICABLE")
    keys = ("scope", "operation_id", "status", "committed_at", "batch_versions", "event_ids", "trace_id")
    return {"data": {"protocol_version": "v1-operation-receipt-1", **{k: receipt[k] for k in keys}}}


@router.get("/api/v1/households/{household_id}/consumption-events")
def consumption_events(household_id: UUID, limit: int = Query(50, ge=1, le=100),
                       offset: int = Query(0, ge=0), identity: Identity = Depends(get_identity),
                       db: Session = Depends(get_db)):
    service.membership(db, identity.user.id, household_id)
    filters = [BusinessEvent.household_id == household_id, BusinessEvent.event_type == "Consumed"]
    total = db.scalar(select(func.count()).select_from(BusinessEvent).where(*filters))
    rows = db.scalars(select(BusinessEvent).where(*filters)
        .order_by(BusinessEvent.occurred_at.desc(), BusinessEvent.id).limit(limit).offset(offset)).all()
    return {"items": [{"id": str(row.id), "operation_id": str(row.operation_id),
            "inventory_item_id": str(row.inventory_item_id), "event_type": row.event_type,
            "quantity": format(row.quantity, "f"), "unit": row.unit, "occurred_at": row.occurred_at.isoformat(),
            "before": row.before_json, "after": row.after_json} for row in rows],
            "total": total, "limit": limit, "offset": offset,
            "planning_history_complete": False}
