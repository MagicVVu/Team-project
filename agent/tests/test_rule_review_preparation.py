from datetime import date
import pytest
from p2.knowledge import RuleCatalog
from v1.knowledge import HumanRuleCatalog
from review.rules import approved_catalog, candidates, digest


def approval(rule, **changes):
    return {"rule_id": rule.id, "rule_version": rule.version, "rule_sha256": digest(rule),
            "decision": "approved", "reviewed_by": "审核负责人（合成测试）", "reviewed_on": "2026-10-24",
            "evidence": "isolated unit-test approval; not a real review", **changes}


def test_candidates_remain_disabled_and_runtime_is_unchanged():
    catalog = RuleCatalog.load()
    before = catalog.data.model_dump_json()
    result = candidates(catalog)
    assert len(result["rules"]) == 5
    assert all(not row["rule"]["enabled"] and not row["rule"]["reviewed"] and row["human_approval"] is None for row in result["rules"])
    assert catalog.data.model_dump_json() == before
    assert not HumanRuleCatalog.from_catalog(catalog).list_rules()


def test_only_explicit_matching_approvals_can_enter_separate_artifact():
    catalog = RuleCatalog.load()
    result = approved_catalog(catalog, [approval(catalog.data.rules[0])], today=date(2026, 10, 24))
    assert len(HumanRuleCatalog.from_catalog(result).list_rules()) == 1
    assert not HumanRuleCatalog.from_catalog(catalog).list_rules()
    assert all(not r.enabled for r in result.data.rules[1:])


@pytest.mark.parametrize("changes", [{"rule_sha256": "0"*64}, {"reviewed_by": "Codex automated verification"},
    {"reviewed_on": "2026-10-25"}, {"reviewed_on": "2020-01-01"}, {"rule_id": "unknown"}])
def test_invalid_approval_is_rejected(changes):
    catalog = RuleCatalog.load()
    with pytest.raises(ValueError):
        approved_catalog(catalog, [approval(catalog.data.rules[0], **changes)], today=date(2026, 10, 24))


def test_duplicate_or_rejected_reviews_do_not_enable_rules():
    catalog = RuleCatalog.load()
    record = approval(catalog.data.rules[0])
    with pytest.raises(ValueError): approved_catalog(catalog, [record, record])
    result = approved_catalog(catalog, [{**record, "decision": "rejected"}], today=date(2026, 10, 24))
    assert not HumanRuleCatalog.from_catalog(result).list_rules()
