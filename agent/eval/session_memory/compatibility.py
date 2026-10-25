"""Frozen P8.1 contracts remain exact except the explicit compatible release tag."""
def assert_legacy_schema(old, new):
    if old == new:
        return
    if isinstance(old, dict) and old.get("const") == "V1-P8.1" and old.get("default") == "V1-P8.1":
        expected = {key:value for key,value in old.items() if key not in {"const", "default"}}
        expected.update(enum=["V1-P8.1", "V1-P8.2"], default="V1-P8.2")
        assert new == expected, "Unexpected maintenance-release schema change"
        return
    if isinstance(old, dict) and isinstance(new, dict):
        assert old.keys() == new.keys(), "Unexpected legacy schema key change"
        for key in old: assert_legacy_schema(old[key], new[key])
        return
    if isinstance(old, list) and isinstance(new, list):
        assert len(old) == len(new)
        for before, after in zip(old, new): assert_legacy_schema(before, after)
        return
    assert old == new, "Unexpected legacy schema value change"
