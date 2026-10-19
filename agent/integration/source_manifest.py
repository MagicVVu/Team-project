"""Allowlist for code-only synchronization into ~/workspace/agent.

Documents, exports, fixtures and private configuration are not synchronized.
P4 explicitly includes the repaired shared P0/P1 runtime dependencies.
"""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "p0/text.py", "p0/engines.py", "p0/manager.py",
    "p1/engines.py", "p1/domain.py", "p1/manager.py",
    "p2/__init__.py", "p2/app.py", "p2/engines.py", "p2/knowledge.py",
    "p2/manager.py", "p2/risk.py", "p2/schemas.py", "p2/tools.py", "p2/rules.json",
    "integration/__init__.py", "integration/agent_health.py",
    "integration/backend_v06.py", "integration/source_manifest.py", "integration/runtime_config.py",
    "Dockerfile.p2", "Dockerfile.p2.dockerignore", "requirements.p2.runtime.txt",
    "p3/__init__.py", "p3/app.py", "p3/engines.py", "p3/forecast.py",
    "p3/health.py", "p3/history.py", "p3/manager.py", "p3/procurement.py",
    "p3/schemas.py", "p3/tools.py", "Dockerfile.p3", "Dockerfile.p3.dockerignore",
    "interaction/__init__.py", "interaction/app.py", "interaction/engines.py", "interaction/health.py",
    "interaction/manager.py", "interaction/policy.py", "interaction/schemas.py",
    "interaction/session.py", "interaction/tasks.py",
    "Dockerfile.interaction", "Dockerfile.interaction.dockerignore",
    "v1/__init__.py", "v1/app.py", "v1/engines.py", "v1/health.py", "v1/knowledge.py",
    "v1/manager.py", "v1/policy.py", "v1/render.py", "v1/schemas.py", "v1/tasks.py", "v1/tools.py",
    "Dockerfile.v1", "Dockerfile.v1.dockerignore",
    "conversation/__init__.py", "conversation/app.py", "conversation/schemas.py",
    "conversation/engines.py", "conversation/manager.py", "conversation/replies.py",
    "conversation/tasks.py", "conversation/health.py",
    "Dockerfile.conversation", "Dockerfile.conversation.dockerignore",
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
