import asyncio
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.dependencies import Identity, get_db, get_identity
from app.memory_schemas import Message, Reset, Response, Page, Recovery
from app.services import session_memory as service

router = APIRouter(tags=["Conversation memory — opt-in"])


@router.get("/api/v1/agent/conversation", response_model=Page)
def current(household_id: UUID, cursor: UUID | None = None, limit: int = Query(default=20, ge=1, le=100),
            identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    return service.page(db, identity, household_id, cursor, limit)


@router.post("/api/v1/agent/conversation/reset", response_model=Response)
def reset(body: Reset, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    try:
        return service.reset(db, identity, body)
    finally:
        db.rollback()


@router.post("/api/v1/agent/conversation-turns", response_model=Response)
async def message(body: Message, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    try:
        from app.services.dialogue import enabled
        async with asyncio.timeout(20 if enabled() else 10):
            if body.text.strip().rstrip("。！! ") in {"开始新会话", "清空当前会话"}:
                return service.reset(db, identity, Reset(household_id=body.household_id, request_id=body.request_id,
                    conversation_id=body.conversation_id, conversation_revision=body.conversation_revision), body.text)
            return await service.send(db, identity, body)
    except TimeoutError:
        raise HTTPException(504, detail={"code": "CONVERSATION_TIMEOUT", "request_id": body.request_id,
                                       "original_text": body.text, "recovery": "GET conversation-turns/{request_id}"}) from None


@router.get("/api/v1/agent/conversation-turns/{request_id}", response_model=Recovery)
def recover(request_id: str, household_id: UUID, identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    return service.recover(db, identity, household_id, request_id)
