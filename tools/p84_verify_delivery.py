"""Local delivery audit only. Does not sync, deploy, contact a model or open DBs."""
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"agent"))
from integration.source_manifest import manifest

docs=ROOT/"docs/versions/V1-P8.4"
broken=[]
for path in docs.glob("*.md"):
    for label,target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)",path.read_text(encoding="utf-8")):
        if not target.startswith(("https:","http:","#")) and not (path.parent/target.split("#")[0]).exists():
            broken.append({"file":path.name,"target":target})
assert not broken,broken
contracts=docs/"contracts"
for path in contracts.glob("*.json"):json.loads(path.read_text(encoding="utf-8"))
api=json.loads((contracts/"ai-openapi.json").read_text(encoding="utf-8"))
assert all("/agent/dialogue/"+stage in api["paths"] for stage in ("understand","resolve","respond"))
files=[*list((ROOT/"agent/conversation").glob("dialogue*.py")),ROOT/"backend/server/app/services/dialogue.py"]
for path in files:ast.parse(path.read_text(encoding="utf-8"))
out=ROOT/"reports/p84-dialogue"
summary=dict(stage="V1-P8.4",local_only=True,server_synchronized=False,server_version_replaced=False,
    android_modified=False,new_tables=False,migrations=False,git_committed=False,git_pushed=False,
    markdown_links_verified=True,json_contract_count=len(list(contracts.glob("*.json"))),
    protocol="p84-dialogue-1",source_manifest=manifest(),
    backend_adapter_sha256=hashlib.sha256((ROOT/"backend/server/app/services/dialogue.py").read_bytes()).hexdigest(),
    evaluation="evaluation-summary.json",human_naturalness_review="pending",app_joint_acceptance="not_run")
(out/"delivery-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({k:v for k,v in summary.items() if k not in {"source_manifest","backend_adapter_sha256"}},ensure_ascii=False))
