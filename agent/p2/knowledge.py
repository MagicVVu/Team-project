import hashlib
import json
from pathlib import Path

from .schemas import Batch, Rule, RuleFile


class RuleCatalog:
    """Trusted local configuration; no browsing, rule writes or executable expressions."""
    def __init__(self, rules: RuleFile):
        identities = [(r.id, r.version) for r in rules.rules]
        if len(identities) != len(set(identities)):
            raise ValueError("重复的规则 ID 与版本")
        self.data = rules.model_copy(deep=True)
        self.sha256 = hashlib.sha256(self.data.model_dump_json().encode()).hexdigest()

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path else Path(__file__).with_name("rules.json")
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError("重复 JSON 字段")
                obj[key] = value
            return obj
        return cls(RuleFile.model_validate(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)))

    def applicable(self, batch: Batch) -> list[Rule]:
        return [r.model_copy(deep=True) for r in self.data.rules if r.enabled and r.reviewed
                and batch.category in r.categories
                and (not r.product_ids or batch.product_id in r.product_ids)
                and (r.storage_condition is None or batch.storage_condition == r.storage_condition)
                and (r.opened is None or batch.is_opened == r.opened)]

    def list_rules(self, category=None):
        return [rule.model_copy(deep=True) for rule in self.data.rules
                if category is None or category in rule.categories]
