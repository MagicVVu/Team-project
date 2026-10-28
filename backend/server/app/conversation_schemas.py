"""Public input contains selectors only; binding, clock and inventory are server-owned."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    household_id: UUID
    text: str = Field(min_length=1, max_length=1000, pattern=r"\S")
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    task_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def selector(self):
        if (self.task_id is None) != (self.revision is None):
            raise ValueError("task_id and revision must be provided together")
        return self


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal["p7-reply-routing-1"] = "p7-reply-routing-1"
    kind: Literal["clarify", "new_task", "needs_input", "clear_reference"]
    answers: dict[str, str] = Field(default_factory=dict, max_length=9)
    revision: int | None = Field(default=None, ge=1, strict=True)
    error_code: str | None = None
    clear_reference: bool = False
    model_calls: Literal[0] = 0


class ConversationResponse(BaseModel):
    protocol_version: Literal["backend-conversation-1"] = "backend-conversation-1"
    request_id: str
    original_text: str
    resolution: Resolution
    task: dict | None
    reference: dict | None
    inventory_written: Literal[False] = False
