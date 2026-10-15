"""Allowlist for code-only synchronization into ~/workspace/agent.

Documents, exports, fixtures, private configuration and existing P0/P1 files are
not synchronized. The JSON rule catalog is required executable input data.
"""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "p2/__init__.py", "p2/app.py", "p2/engines.py", "p2/knowledge.py",
    "p2/manager.py", "p2/risk.py", "p2/schemas.py", "p2/tools.py", "p2/rules.json",
    "integration/__init__.py", "integration/agent_health.py",
    "integration/backend_v06.py", "integration/source_manifest.py",
    "Dockerfile.p2", "Dockerfile.p2.dockerignore", "requirements.p2.runtime.txt",
)


def manifest(root=ROOT):
    root = root.resolve()
    hashes = {}
    for relative in SOURCE_PATHS:
        path = root / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError("AI source missing or outside agent directory")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"kind": "AI runtime code-only sync", "files": hashes,
            "documents_included": False, "credentials_included": False}


if __name__ == "__main__":
    print(json.dumps(manifest(), ensure_ascii=True, indent=2))
