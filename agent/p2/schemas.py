from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator
from p0.schemas import Model
from p1.schemas import (AgentResult as P1Result, Batch as P1Batch,
                        ClarificationContext as P1Context, ClarificationRequest as P1ClarificationRequest,
                        Message, Name, Parsed as P1Parsed)


Category = Literal["food", "medicine", "household", "unknown"]
Storage = Literal["ambient", "refrigerated", "frozen"]
Level = Literal["green", "yellow", "orange", "red", "unknown"]


class Intent(StrEnum):
    ADD = "ADD"
    CONSUME = "CONSUME"
    QUERY_INVENTORY = "QUERY_INVENTORY"
    QUERY_LOCATION = "QUERY_LOCATION"
    PLAN_ADD = "PLAN_ADD"
    OPEN = "OPEN"
    MOVE = "MOVE"
    DISCARD = "DISCARD"
    QUERY_RISK = "QUERY_RISK"
    UNSUPPORTED = "UNSUPPORTED"


class Parsed(P1Parsed):
    intent: Intent


class Batch(P1Batch):
    category: Category = "unknown"
    product_id: str | None = Field(default=None, min_length=1, max_length=100)
    label_date_type: Literal["use_by", "best_before", "expiry", "unknown"] = "unknown"
    # True only when the backend has recorded that the label still applies to
    # this batch. Cooking/freezing/repacking can invalidate that assumption.
    label_context_valid: bool | None = None
    storage_condition: Storage | None = None
    label_storage_condition: Storage | None = None
    is_opened: bool | None = None


class Source(Model):
    title: str = Field(min_length=1, max_length=200)
    ref: str = Field(min_length=1, max_length=500)
    kind: Literal["official_guidance", "manufacturer_label", "project_policy"]
    checked_on: date
    verification_note: str = Field(min_length=1, max_length=500)


class Rule(Model):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    kind: Literal["label_date", "storage", "near_expiry", "after_open"]
    categories: list[Category] = Field(min_length=1)
    product_ids: list[str] = Field(default_factory=list, max_length=100)
    storage_condition: Storage | None = None
    opened: bool | None = None
    max_days_after_open: int | None = Field(default=None, ge=1, le=3650)
    source: Source
    reviewed: bool = False
    review_kind: Literal["source_check", "human_review"] | None = None
    reviewed_by: str | None = Field(default=None, max_length=120)
    reviewed_on: date | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def review_and_threshold(self):
        if self.reviewed and (not self.review_kind or not self.reviewed_by or not self.reviewed_on):
            raise ValueError("审核规则必须保存审核方式 人员和日期")
        if self.kind == "after_open":
            if self.max_days_after_open is None or not self.product_ids or self.source.kind != "manufacturer_label" or self.opened is not True:
                raise ValueError("开封天数规则必须有对应商品 包装标签来源 明确天数及已开封条件")
        elif self.max_days_after_open is not None:
            raise ValueError("只有开封规则可以设置开封天数")
        if self.source.kind != "project_policy" and not self.source.ref.startswith("https://"):
            raise ValueError("来源需保留可核验 HTTPS 引用")
        return self


class RuleFile(Model):
    version: str
    rules: list[Rule] = Field(max_length=1000)


class Evidence(Model):
    reason_code: str
    explanation: str
    facts: dict[str, str | None] = Field(default_factory=dict)
    rule_id: str | None = None
    rule_version: str | None = None
    source: Source | None = None


class RiskResult(Model):
    batch_id: str
    name: str
    batch_version: int
    level: Level
    attention: bool
    excluded: bool = False
    reason_codes: list[str]
    evidence: list[Evidence]
    missing_information: list[str]
    recommended_action: str
    evaluated_at: AwareDatetime
    household_timezone: str
    ruleset_version: str
    rule_versions: dict[str, str]
    source_human_reviewed: bool
    safety_guaranteed: Literal[False] = False


class RiskQuery(Model):
    name: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"\S")
    batch_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    household_timezone: str = "Asia/Shanghai"
    reminder_days: int = Field(default=3, ge=0, le=365)
    attention_only: bool = False

    _timezone = field_validator("household_timezone")(Message.timezone.__func__)

    @model_validator(mode="after")
    def selectors(self):
        if self.name and self.batch_ids:
            raise ValueError("name 与 batch_ids 只能选一种")
        if self.batch_ids and len(set(self.batch_ids)) != len(self.batch_ids):
            raise ValueError("批次 ID 不可重复")
        return self


class RiskMessage(Message):
    reminder_days: int = Field(default=3, ge=0, le=365)


class RiskSelectionParsed(Model):
    intent: Literal["QUERY_RISK"] = "QUERY_RISK"
    name: Name | None = None


class RiskSelectionContext(P1Context):
    """Server-stored selection only; answers cannot update inventory facts."""
    protocol_version: Literal["p2-risk-selection-1"]
    parsed: RiskSelectionParsed
    allowed_fields: list[Literal["name"]] = Field(default_factory=lambda: ["name"], max_length=1)
    reminder_days: int = Field(default=3, ge=0, le=365)
    # Selection by name returns every matching batch. No implicit batch choice.
    candidates: list[P1Batch] = Field(default_factory=list, max_length=0)
    selected_batch_id: None = None


class ClarificationRequest(P1ClarificationRequest):
    context: RiskSelectionContext | P1Context


class RiskResponse(Model):
    trace_id: str
    evaluated_count: int
    returned_count: int
    risks: list[RiskResult]
    facts: list[Batch]
    inventory_writes: Literal[False] = False


class AgentResult(P1Result):
    intent: Intent | None = None
    clarification: RiskSelectionContext | P1Context | None = None
    facts: list[Batch] = Field(default_factory=list)
    risks: list[RiskResult] = Field(default_factory=list)
    evaluated_count: int = 0
