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
    # Autonomous turns intentionally widen only the session call counter and
    # add a discriminated metadata branch. Older wire routes/business models
    # remain exact; runtime tests separately enforce old protocol call limits.
    if old.get("title")=="Response" and "maximum" in old.get("properties",{}).get("model_calls",{}) and "maximum" not in current.get("properties",{}).get("model_calls",{}):
        current=deepcopy(current)
        counter=current["properties"]["model_calls"]
        assert counter["minimum"]==0 and counter["type"]=="integer"
        if "maximum" not in counter:
            choices=current["properties"]["dialogue"]["anyOf"][0]["discriminator"]["mapping"]
            assert set(choices)=={"p84-dialogue-1","p85-dialogue-1","inventory-autonomous-1"}
        counter["maximum"]=old["properties"]["model_calls"]["maximum"]
        if "dialogue" in old["properties"]:
            # Existing records retain the exact same legacy metadata type.
            refs=[v["$ref"] for v in old["properties"]["dialogue"].get("anyOf",[]) if "$ref" in v]
            assert len(refs)==1 and choices["p84-dialogue-1"]==choices["p85-dialogue-1"]==refs[0]
            current["properties"]["dialogue"]=deepcopy(old["properties"]["dialogue"])
        else: current["properties"].pop("dialogue")
        for name in ("AutonomousCalls","AutonomousMetadata"):
            if name not in old.get("$defs",{}):current.get("$defs",{}).pop(name,None)
    def dialogue_protocols(value):
        if isinstance(value, list): return [dialogue_protocols(v) for v in value]
        if not isinstance(value, dict): return value
        value = deepcopy(value)
        if value.get("title") == "DialogueMetadata":
            # Optional output feedback added after P8.5; historical business bounds stay exact.
            for name in ("status", "stop_reason"):
                assert name not in value.get("required", [])
                value.get("properties", {}).pop(name, None)
            field = value.get("properties", {}).get("protocol_version", {})
            if field.get("const") == "p84-dialogue-1":
                field.pop("const")
                field["enum"] = ["p84-dialogue-1", "p85-dialogue-1"]
        if value.get("title") == "Recovery":
            for name in ("conversation_id", "current_conversation_revision"):
                assert name not in value.get("required", [])
                value.get("properties", {}).pop(name, None)
        return {k: dialogue_protocols(v) for k, v in value.items()}
    # P8.5 adds a protocol choice; all other historical bounds remain exact.
    assert decimal_schema_projection(dialogue_protocols(old)) == decimal_schema_projection(dialogue_protocols(current))
