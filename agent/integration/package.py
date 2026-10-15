"""Build an allowlisted AI-only handoff; no credentials, inventory or ledger."""
import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def package(output, root=REPO):
    root = root.resolve()
    paths = []
    for module in ("p0", "p1", "p2", "integration"):
        paths.extend((root / "agent" / module).glob("*.py"))
    paths.extend(root / name for name in (
        "agent/p2/rules.json", "agent/p2/README.md", "agent/integration/README.md",
        "agent/requirements.runtime.txt", "agent/requirements.p2.runtime.txt", "agent/Dockerfile.p2",
        "agent/Dockerfile.p2.dockerignore", "agent/.dockerignore", "agent/eval/pricing.json",
        "deploy/compose.p2.override.yaml", "docs/versions/V1-P2/ai-openapi.json",
        "docs/versions/V1-P2/ai-contract.md"))
    members = {}
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError("handoff member missing or outside repository")
        members[path.relative_to(root).as_posix()] = path.read_bytes()
    manifest = {"kind": "AI-only V1-P2 integration handoff", "remote_deployed": False,
                "files": {name: hashlib.sha256(payload).hexdigest() for name, payload in members.items()}}
    members["p2-integration-manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2)+"\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(payload), 0o644, 0
            archive.addfile(info, io.BytesIO(payload))
    return {"archive": str(output.resolve()), "member_count": len(members),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "remote_deployed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO/"agent/.cache/p2-integration/magicvvu-ai-p2-integration.tar.gz")
    args = parser.parse_args()
    print(json.dumps(package(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
