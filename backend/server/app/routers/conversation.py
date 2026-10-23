from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.conversation_schemas import ConversationMessage, ConversationResponse
from app.services.conversation import handle
from uuid import UUID
from app.services.chat_controls import ControlRequest, ControlResponse, handle as control

router = APIRouter(tags=["Conversation — authenticated P7.3 adapter"])


@router.post("/api/v1/agent/conversation-messages", response_model=ConversationResponse)
async def conversation_message(body: ConversationMessage, identity: Identity = Depends(get_identity),
                               db: Session = Depends(get_db)):
    return await handle(body, identity, db)


@router.post("/api/v1/agent/tasks/{task_id}/chat-control", response_model=ControlResponse)
def chat_control(task_id: UUID, body: ControlRequest, identity: Identity = Depends(get_identity),
                 db: Session = Depends(get_db)):
    try:
        result = control(db, identity, task_id, body)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
