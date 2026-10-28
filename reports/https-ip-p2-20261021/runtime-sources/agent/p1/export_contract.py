"""Export the actual P1 read-only API; no credentials, model calls or backend."""
import json
from pathlib import Path
from unittest.mock import patch

from .app import create_app
from .engines import RuleEngine


def export():
    # Factory dependencies are only needed to describe routes, never invoked here.
    with patch.dict("os.environ", {"AI_SERVICE_TOKEN": "contract-export-only", "P1_ENGINE": "rules"}):
        schema = create_app(engine=RuleEngine(), reader=object()).openapi()
    target = Path(__file__).resolve().parents[2] / "docs/versions/V1-P1/ai-openapi.json"
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    export()
