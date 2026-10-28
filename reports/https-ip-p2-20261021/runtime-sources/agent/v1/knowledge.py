from p2.knowledge import RuleCatalog

class HumanRuleCatalog(RuleCatalog):
    """Release policy: automatic source verification never counts as human review."""
    def applicable(self, batch):
        return [rule for rule in super().applicable(batch) if rule.review_kind == "human_review"]

    @classmethod
    def from_catalog(cls, catalog):
        return cls(catalog.data)

    def list_rules(self, category=None):
        return [r for r in super().list_rules(category) if r.enabled and r.reviewed and r.review_kind=="human_review"]
