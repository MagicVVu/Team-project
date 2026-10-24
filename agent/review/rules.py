"""Prepare disabled candidates and validate externally supplied human approvals.

This checks a trusted local review record; it cannot authenticate a human or
replace professional review. It never updates the runtime catalog/configuration.
"""
import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from p2.knowledge import RuleCatalog


def digest(rule):
    payload = rule.model_dump(mode="json", exclude={"reviewed", "review_kind", "reviewed_by", "reviewed_on", "enabled"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    rule_version: str
    rule_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: str = Field(pattern=r"^(approved|rejected)$")
    reviewed_by: str = Field(min_length=1, max_length=120, pattern=r"\S")
    reviewed_on: date
    evidence: str = Field(min_length=1, max_length=1000, pattern=r"\S")


def candidates(catalog):
    return {"status": "pending_human_review", "runtime_unchanged": True, "rules": [
        {"rule": {**r.model_dump(mode="json"), "reviewed": False, "review_kind": None,
                  "reviewed_by": None, "reviewed_on": None, "enabled": False},
         "rule_sha256": digest(r), "review_status": "pending", "human_approval": None}
        for r in catalog.data.rules]}


def approved_catalog(catalog, approvals, *, today=None):
    today = today or date.today()
    records = [Approval.model_validate(a) for a in approvals]
    indexed = {(a.rule_id, a.rule_version): a for a in records}
    if len(indexed) != len(records):
        raise ValueError("Duplicate review identity")
    known = {(r.id, r.version) for r in catalog.data.rules}
    if set(indexed)-known:
        raise ValueError("Review refers to an unknown rule")
    result = catalog.data.model_copy(deep=True)
    for rule in result.rules:
        rule.reviewed, rule.enabled = False, False
        rule.review_kind = rule.reviewed_by = rule.reviewed_on = None
        approval = indexed.get((rule.id, rule.version))
        if approval is None:
            continue
        if approval.rule_sha256 != digest(rule):
            raise ValueError("Reviewed rule content changed")
        if not rule.source.checked_on <= approval.reviewed_on <= today:
            raise ValueError("Invalid review/source dates")
        if re.search(r"codex|automated|synthetic|test.only|自动", approval.reviewed_by, re.I):
            raise ValueError("Automated/test verification is not human approval")
        if approval.decision == "approved":
            rule.reviewed = rule.enabled = True
            rule.review_kind = "human_review"
            rule.reviewed_by, rule.reviewed_on = approval.reviewed_by, approval.reviewed_on
    return RuleCatalog(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--approvals", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_path = Path(__file__).resolve().parents[1]/"p2/rules.json"
    if args.output.resolve() == runtime_path.resolve() or (args.catalog and args.output.resolve() == args.catalog.resolve()):
        parser.error("Output must be a separate local artifact")
    catalog = RuleCatalog.load(args.catalog)
    value = (approved_catalog(catalog, json.loads(args.approvals.read_text(encoding="utf-8"))).data.model_dump(mode="json")
             if args.approvals else candidates(catalog))
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
