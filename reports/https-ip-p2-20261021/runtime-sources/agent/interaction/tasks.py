"""Typed AI-task client for the formal gateway, never inventory confirmation.

This is caller/integration code. It is not a replacement business backend and
does not store sessions, proxy requests or expose a new HTTP service.
"""
import asyncio
from typing import Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import AwareDatetime, Field, field_validator, model_validator
from p0.domain import DomainError
from p0.schemas import Model
from p1.schemas import Command, ChangePreview
from .schemas import AgentResult
from .session import public_message

V06_ANSWERS={"name","quantity","unit","location","purchased_at","label_expiry","opened_at","to_location","batch_id"}


class PublicClarification(Model):
    revision: int = Field(ge=1)
    allowed_fields: list[str]
    expires_at: AwareDatetime | None


class PublicResult(AgentResult):
    clarification: PublicClarification | None = None


class Task(Model):
    task_id: UUID
    household_id: UUID
    status: Literal["processing","answered","needs_clarification","needs_confirmation","unsupported","error"]
    revision: int = Field(ge=1)
    expires_at: AwareDatetime | None
    draft_id: UUID | None
    result: PublicResult | None
    inventory_written: Literal[False]

    @field_validator("result", mode="before")
    @classmethod
    def empty_processing(cls, value):
        return None if value == {} else value

    @model_validator(mode="after")
    def state(self):
        if self.status != "processing" and (self.result is None or self.result.status != self.status):
            raise ValueError("任务和结果状态不一致")
        if self.result and any(b.household_id != str(self.household_id) for b in self.result.facts+self.result.candidates):
            raise ValueError("结果包含其他家庭事实")
        if self.result and self.result.preview and self.result.preview.before and self.result.preview.before.household_id != str(self.household_id):
            raise ValueError("预览属于其他家庭")
        if self.result and any(b.household_id != str(self.household_id) for i in self.result.item_candidates for b in i.batches):
            raise ValueError("候选属于其他家庭")
        if self.result and self.result.status == "needs_confirmation" and (self.result.draft is None or self.draft_id is None):
            raise ValueError("待确认任务缺少草稿或草稿引用")
        if self.result and self.result.status == "needs_clarification" and self.result.clarification is None:
            raise ValueError("待澄清任务缺少公开选择信息")
        if self.result and self.result.clarification and self.result.clarification.revision != self.revision:
            raise ValueError("公开澄清修订号与任务不一致")
        return self


class Draft(Model):
    id: UUID
    task_id: UUID
    revision: int = Field(ge=1)
    status: str
    draft: Command
    preview: ChangePreview
    prospective: Literal[True]
    inventory_written: Literal[False]


def parse_task(value, household_id, *, task_type=Task):
    if not isinstance(value,dict) or "task_id" not in value:
        raise DomainError("WRONG_GATEWAY_PROTOCOL","返回不是正式任务协议，不能使用旧手机快照网关。",503)
    try:
        task = task_type.model_validate(value)
    except (ValueError,TypeError):
        raise DomainError("TASK_CONTRACT_INVALID","任务返回格式或权限事实不符合契约。",503) from None
    if str(task.household_id) != str(UUID(household_id)):
        raise DomainError("HOUSEHOLD_FORBIDDEN","任务不属于当前家庭。",403)
    return task


class TaskClient:
    task_type = Task

    def __init__(self, base_url, user_access_token, household_id, *, timeout_seconds=15, transport=None):
        url = httpx.URL(base_url)
        if (url.scheme not in {"http","https"} or not url.host or url.username or url.password or url.query or url.fragment or url.path not in {"","/"}
            or (url.scheme == "http" and url.host not in {"localhost","127.0.0.1","::1","backend"})):
            raise ValueError("需要不含凭据的HTTPS根地址，HTTP只限受信本机或容器后端")
        if not user_access_token.strip() or any(c in user_access_token for c in "\r\n"):
            raise ValueError("需要有效业务用户令牌")
        if not 0 < timeout_seconds <= 30:
            raise ValueError("任务总等待须在0到30秒内")
        self.base_url, self._token = str(url).rstrip("/"), user_access_token
        self.household_id = str(UUID(household_id))
        self.timeout_seconds, self.transport = timeout_seconds, transport

    async def _request(self, method, path, body=None):
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport,timeout=self.timeout_seconds,trust_env=False,follow_redirects=False) as client:
                    response = await client.request(method,self.base_url+path,json=body,
                        headers={"Authorization":"Bearer "+self._token})
            if response.status_code in {401,403}:
                raise DomainError("BUSINESS_UNAUTHENTICATED" if response.status_code==401 else "HOUSEHOLD_FORBIDDEN","用户身份或家庭权限需要重新核对。",response.status_code)
            if response.status_code == 409:
                raise DomainError("TASK_CONFLICT","幂等键、任务或库存版本冲突，请读取已有任务核对。",409)
            if response.status_code == 422:
                raise DomainError("TASK_REQUEST_INVALID","任务字段不符合当前后端契约，请核对后再提交。",422)
            if response.status_code == 404:
                raise DomainError("TASK_NOT_FOUND","任务或草稿不可访问，请核对当前身份与任务。",404)
            if response.status_code not in {200,201}:
                raise DomainError("TASK_UNAVAILABLE","任务请求未能返回结果，请查询原任务；不自动重发。",503)
            value = response.json()
            if isinstance(value,dict) and "success" in value:
                if value.get("success") is not True: raise ValueError("failed envelope")
                value = value["data"]
            return value
        except (TimeoutError,httpx.HTTPError):
            raise DomainError("TASK_OUTCOME_UNKNOWN","任务结果未知，请查询原任务，或明确使用同一键恢复；不自动重试。",503) from None
        except (ValueError,KeyError,TypeError):
            raise DomainError("TASK_CONTRACT_INVALID","任务返回不是有效的正式协议。",503) from None

    async def submit(self, state):
        if state.scope.household_id != self.household_id:
            raise DomainError("HOUSEHOLD_FORBIDDEN","输入会话不属于当前家庭。",403)
        return parse_task(await self._request("POST","/api/v1/agent/messages",public_message(state)),self.household_id,task_type=self.task_type)

    async def get_task(self, task_id):
        task_id = str(UUID(str(task_id)))
        task = parse_task(await self._request("GET","/api/v1/agent/tasks/"+task_id),self.household_id,task_type=self.task_type)
        if str(task.task_id) != task_id:
            raise DomainError("TASK_CONTRACT_INVALID","返回了其他任务。",503)
        return task

    async def clarify(self, task_id, revision, answers):
        task_id = str(UUID(str(task_id)))
        if not isinstance(revision,int) or isinstance(revision,bool) or revision < 1:
            raise DomainError("INVALID_CLARIFICATION","澄清修订号必须为正整数。")
        from .schemas import Answers
        values = Answers.model_validate(answers).model_dump(mode="json",exclude_none=True)
        if not values or not set(values)<=V06_ANSWERS:
            raise DomainError("TASK_CAPABILITY_UNAVAILABLE","当前数据库网关不接收空答案或item_key，请使用已有补字段协议或明确重新提交。",422)
        task = parse_task(await self._request("POST","/api/v1/agent/clarifications/"+task_id,
            {"revision":revision,"answers":values}),self.household_id,task_type=self.task_type)
        if str(task.task_id) != task_id:
            raise DomainError("TASK_CONTRACT_INVALID","返回了其他任务。",503)
        return task

    async def get_draft(self, draft_id, task_id):
        draft_id,task_id = str(UUID(str(draft_id))),str(UUID(str(task_id)))
        try:
            draft = Draft.model_validate(await self._request("GET","/api/v1/drafts/"+draft_id))
        except (ValueError,TypeError):
            raise DomainError("TASK_CONTRACT_INVALID","草稿返回格式不符合契约。",503) from None
        if str(draft.id)!=draft_id or str(draft.task_id)!=task_id:
            raise DomainError("TASK_CONTRACT_INVALID","草稿归属或引用不一致。",503)
        return draft
