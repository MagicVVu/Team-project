from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.conversation_schemas import ConversationMessage, ConversationResponse
from app.services.conversation import handle

router = APIRouter(tags=["Conversation — authenticated P7.3 adapter"])


@router.post("/api/v1/agent/conversation-messages", response_model=ConversationResponse)
async def conversation_message(body: ConversationMessage, identity: Identity = Depends(get_identity),
                               db: Session = Depends(get_db)):
    return await handle(body, identity, db)
