"""Internal authenticated HTTP adapter for the existing P7.3 pure function.

The business backend owns the binding and time. This adapter owns no state,
does not read tools and never constructs an extraction engine.
"""
from pydantic import AwareDatetime, Field
from p0.schemas import Model
from .replies import BoundTask, ReplyResolution, resolve_reply


class ResolveRequest(Model):
    binding: BoundTask
    text: str = Field(min_length=1, max_length=1000)
    trusted_now: AwareDatetime
    selected_batch_id: str | None = Field(default=None, min_length=1, max_length=100)


def install(app, scope):
    from fastapi import Depends
    from p0.schemas import Scope

    @app.post("/agent/reply-resolution", response_model=ReplyResolution)
    def reply_resolution(body: ResolveRequest, identity: Scope = Depends(scope)):
        return resolve_reply(body.binding, body.text, identity, body.trusted_now,
                             selected_batch_id=body.selected_batch_id)
