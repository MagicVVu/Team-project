"""Compare backend contracts across Pydantic's Decimal JSON-schema renderers.

P9's supplied export omits Decimal string regex. The local 2.12 runtime emits
one, also in output-only and nullable schemas. Normalize only the known
Pydantic Decimal pattern prefix; bounds and unrelated string rules stay exact.
"""
from copy import deepcopy


def decimal_schema_projection(value):
    if isinstance(value, list): return [decimal_schema_projection(v) for v in value]
    if not isinstance(value, dict): return value
    value = deepcopy(value)
    if value.get("type") == "string" and value.get("pattern", "").startswith("^(?!^[-+.]*$)"):
        value.pop("pattern")
    return {k:decimal_schema_projection(v) for k,v in value.items()}


def assert_backend_contract(old, current):
    # P8.4 adds opt-in counters to the session response only. Legacy AIResolution
    # and all business schemas still compare exactly, including numeric bounds.
    if old.get("title")=="Response" and "dialogue" not in old.get("properties",{}) and "dialogue" in current.get("properties",{}):
        current=deepcopy(current)
        assert current["properties"]["model_calls"]["maximum"]==2
        current["properties"]["model_calls"]["maximum"]=1
        current["properties"].pop("dialogue")
    assert decimal_schema_projection(old) == decimal_schema_projection(current)
