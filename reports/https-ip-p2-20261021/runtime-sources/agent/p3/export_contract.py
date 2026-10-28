import json
from pathlib import Path
from unittest.mock import patch
from .app import create_app
from .schemas import PlanningSnapshot


def export():
    target = Path(__file__).resolve().parents[2] / "docs/versions/V1-P3"
    target.mkdir(parents=True, exist_ok=True)
    with patch.dict("os.environ", {"AI_SERVICE_TOKEN": "contract-export-only", "P3_ENGINE": "rules"}):
        schema = create_app(reader=object()).openapi()
    for name, body in (("ai-openapi.json", schema), ("planning-context.schema.json", PlanningSnapshot.model_json_schema())):
        (target/name).write_text(json.dumps(body, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    export()
