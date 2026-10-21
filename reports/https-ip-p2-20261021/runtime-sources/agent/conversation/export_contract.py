"""Export local-only P7 artifacts, never synchronize these to the server."""
import json
import os
from pathlib import Path
from unittest.mock import patch
from .app import create_app
from .schemas import ObjectReference, ReferenceContext
from .tasks import Task, Draft
from .replies import BoundTask, ReplyResolution


def export():
    target = Path(__file__).resolve().parents[2]/"docs/versions/V1-P7"
    target.mkdir(parents=True, exist_ok=True)
    with patch.dict(os.environ, {"AI_SERVICE_TOKEN":"export-only-not-a-real-token", "P3_ENGINE":"rules"}):
        schema = create_app(reader=object()).openapi()
    schema["x-public-gateway"] = "unchanged; reference requires separate trusted business adapter"
    for name, value in {"ai-openapi.json":schema,
        "object-reference.schema.json":ObjectReference.model_json_schema(),
        "reference-continuation.schema.json":ReferenceContext.model_json_schema(),
        "public-task.schema.json":Task.model_json_schema(), "public-draft.schema.json":Draft.model_json_schema(),
        "caller-task-binding.schema.json":BoundTask.model_json_schema(),
        "reply-resolution.schema.json":ReplyResolution.model_json_schema()}.items():
        (target/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(target)


if __name__ == "__main__": export()
