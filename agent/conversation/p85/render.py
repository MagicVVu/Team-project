"""Structured expression avoids unverifiable free prose around critical facts."""
from pydantic import Field
from typing import Literal
from p0.schemas import Model

OPENINGS = {
    "none": "", "understood": "明白，我帮你把这件事理清楚。",
    "check": "我重新核对了一下：", "gentle": "别着急，我们接着看。",
    "brief": "你关心的是这个：", "correction": "收到，按你这次的说法核对。",
    "focus": "先回答你现在的问题：", "together": "我们一起看一下。",
}
CLOSINGS = {
    "none": "", "continue": "还想接着了解哪一点？",
    "review_draft": "先看看草稿是否符合你的意思，再决定要不要确认。",
    "choose_batch": "你想继续处理哪一批？",
    "invite": "也可以告诉我你接下来想怎么处理。",
}


class Expression(Model):
    opening: Literal["none", "understood", "check", "gentle", "brief", "correction", "focus", "together"] = "none"
    fact_order: list[str] = Field(max_length=1000)
    layout: Literal["paragraph", "lines"] = "paragraph"
    closing: Literal["none", "continue", "review_draft", "choose_batch", "invite"] = "none"


def vocabulary():
    return {"opening": OPENINGS, "closing": CLOSINGS, "layout": ["paragraph", "lines"]}


def render(value, resolved):
    expression = Expression.model_validate(value)
    if sorted(expression.fact_order) != sorted(resolved.facts):
        raise ValueError("Missing, repeated or invented fact")
    domain = resolved.result or {}
    if expression.closing == "review_draft" and domain.get("status") != "needs_confirmation":
        raise ValueError("No editable pending draft")
    if expression.closing == "choose_batch" and "batch_id" not in domain.get("missing_fields", []):
        raise ValueError("No candidate selection required")
    # No 'I checked' opener if we only have a refusal/question without a read.
    if expression.opening == "check" and not resolved.evidence:
        raise ValueError("No fresh evidence")
    facts = [resolved.facts[key] for key in expression.fact_order]
    joiner = "\n" if expression.layout == "lines" else " "
    return joiner.join(part for part in [OPENINGS[expression.opening], *facts, CLOSINGS[expression.closing]] if part).strip()
