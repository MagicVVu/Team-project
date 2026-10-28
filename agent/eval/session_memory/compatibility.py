"""Frozen contracts: permit only named P8.3 additions; all old fields stay exact."""
from copy import deepcopy

P83_FIELDS = {"planning_calculation", "product_planning", "planning_context", "planning_review"}
P83_DEFS = {"Basis", "ProductPlanning", "PlanningContext", "PlanningReview", "Product", "AggregateBatch"}

def assert_legacy_schema(old, new):
    if old == new:
        return
    if old == ["V1-P8.1", "V1-P8.2", "V1-P8.3"]:
        assert new == ["V1-P8.1", "V1-P8.2", "V1-P8.3", "V1-P8.4"]
        return
    if isinstance(old, dict) and old.get("const") == "V1-P8.1" and old.get("default") == "V1-P8.1":
        expected = {key:value for key,value in old.items() if key not in {"const", "default"}}
        expected.update(enum=["V1-P8.1", "V1-P8.2", "V1-P8.3", "V1-P8.4"], default="V1-P8.2")
        assert new == expected, "Unexpected maintenance-release schema change"
        return
    if isinstance(old, dict) and isinstance(new, dict):
        new = deepcopy(new)
        if "$defs" in old and "$defs" in new:
            additions = set(new["$defs"])-set(old["$defs"])
            assert additions <= P83_DEFS, "Unapproved schema addition"
            for name in additions: new["$defs"].pop(name)
        if "properties" in old and "product_planning" in new.get("properties", {}):
            additions = set(new["properties"])-set(old["properties"])
            assert additions <= P83_FIELDS
            for name in additions: new["properties"].pop(name)
        if "anyOf" in new:
            added_basis = any(branch.get("$ref", "").endswith("/Basis") for branch in new["anyOf"])
            new["anyOf"] = [branch for branch in new["anyOf"] if not branch.get("$ref", "").endswith("/Basis")]
            if added_basis and "title" not in old and new.get("title") == "Planning Basis":
                new.pop("title")
        assert old.keys() == new.keys(), "Unexpected legacy schema key change"
        for key in old: assert_legacy_schema(old[key], new[key])
        return
    if isinstance(old, list) and isinstance(new, list):
        assert len(old) == len(new)
        for before, after in zip(old, new): assert_legacy_schema(before, after)
        return
    assert old == new, "Unexpected legacy schema value change"
