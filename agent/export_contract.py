"""Export both actually registered API contracts without calling a provider."""
import json
import os
from pathlib import Path

from p0.app import create_app


def export():
    target = Path(__file__).resolve().parents[1] / "docs/versions/V1-P0"
    target.mkdir(parents=True, exist_ok=True)
    mock = create_app("mock").openapi()
    mock["info"]["description"] = "Proposed team contract implemented by an in-memory MOCK. Production backend and database acceptance is pending."
    os.environ.setdefault("AI_SERVICE_TOKEN", "export-only-not-a-credential")
    os.environ.setdefault("BACKEND_TOOL_TOKEN", "export-only-not-a-credential")
    os.environ.setdefault("BACKEND_BASE_URL", "http://127.0.0.1:8080")
    service = create_app("service").openapi()
    service["info"]["description"] = "Read-only AI service; authenticated business backend owns draft storage and all inventory writes."
    for name, spec in [("openapi.json", mock), ("ai-openapi.json", service)]:
        (target / name).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Exported mock/team and read-only AI OpenAPI contracts")


if __name__ == "__main__":
    export()
