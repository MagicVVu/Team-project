import json
from pathlib import Path
from unittest.mock import patch

from .app import create_app
from .engines import RuleEngine


def export():
    with patch.dict("os.environ", {"AI_SERVICE_TOKEN": "contract-export-only", "P2_ENGINE": "rules"}):
        schema = create_app(engine=RuleEngine(), reader=object()).openapi()
    target = Path(__file__).resolve().parents[2] / "docs/versions/V1-P2/ai-openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    export()
