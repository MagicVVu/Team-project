"""Pure mapping helper for the future business adapter, not a storage service.

Only call after authenticating the user and reading authorized ConversationTurn
rows. This helper cannot authenticate a phone or attest a business receipt.
"""
from datetime import timedelta
from uuid import UUID
from pydantic import AwareDatetime, Field
from p0.schemas import Model, Scope
from p0.domain import DomainError
from ..schemas import ObjectReference
from .schemas import P85Archive, P85Episode, P85Subject


class P85StoredTurn(Model):
    scope: Scope
    conversation_id: UUID
    revision: int = Field(ge=0, strict=True)
    request_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    reply: str = Field(max_length=8000)
    completed_at: AwareDatetime
    completed: bool = True
    subjects: list[P85Subject] = Field(default_factory=list, max_length=4)
    reference: ObjectReference | None = None


def build_archive(context, turns, *, source_has_more=False):
    """30-day filter and bounded archive; conflicts are never 'last row wins'."""
    from hashlib import sha256
    import json
    by_id = {}
    for raw in turns:
        turn = P85StoredTurn.model_validate(raw)
        if turn.scope != context.scope or turn.conversation_id != context.conversation_id:
            raise DomainError("MEMORY_SCOPE_MISMATCH", "历史记录不属于当前用户、家庭或会话。", 403)
        if turn.revision > context.revision or turn.completed_at > context.trusted_now:
            raise DomainError("MEMORY_REVISION_CONFLICT", "历史快照不一致，请重新读取。", 409)
        if not turn.completed or turn.completed_at <= context.trusted_now-timedelta(days=30):
            continue
        if turn.request_id in by_id and turn != by_id[turn.request_id]:
            raise DomainError("MEMORY_REQUEST_CONFLICT", "相同请求存在不同历史内容，请核对原记录。", 409)
        by_id[turn.request_id] = turn
    chosen = sorted(by_id.values(), key=lambda t: (t.completed_at, t.revision, t.request_id))[-100:]
    episodes = []
    for turn in chosen:
        key = json.dumps([context.scope.model_dump(), str(context.conversation_id), turn.request_id], sort_keys=True)
        episodes.append(P85Episode(memory_id="mem_"+sha256(key.encode()).hexdigest()[:32],
            request_id=turn.request_id, text=turn.text, reply=turn.reply, created_at=turn.completed_at,
            subjects=turn.subjects, reference=turn.reference))
    return P85Archive(scope=context.scope, conversation_id=context.conversation_id, revision=context.revision,
                       episodes=episodes, has_more=source_has_more or len(by_id) > 100)
