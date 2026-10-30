"""Check local deliverables, source hashes, schemas and test evidence."""
import ast
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/"docs/versions/V1-P8.6"
REPORTS=ROOT/"reports/p86-autonomous/initial-20261029"
sys.path.insert(0,str(ROOT/"agent"))


def load(path): return json.loads(path.read_text(encoding="utf-8"))


def main():
    from integration.source_manifest import manifest
    files=manifest()["files"]
    assert load(DOCS/"runtime-source-manifest.json")["files"]==files
    for relative in files:
        if relative.endswith(".py"):ast.parse((ROOT/"agent"/relative).read_text(encoding="utf-8-sig"))
    for name in ["autonomous.py","session_memory.py"]:
        ast.parse((ROOT/"backend/server/app/services"/name).read_text(encoding="utf-8-sig"))
    recorded=load(DOCS/"contracts/manifest.json")["files"]
    for name,digest in recorded.items():
        path=DOCS/"contracts"/name
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
        data=load(path)
        if name.endswith(".schema.json"):Draft202012Validator.check_schema(data)
        def refs(value):
            if isinstance(value,dict):
                if "$ref" in value:
                    assert value["$ref"].startswith("#/"), value["$ref"]
                    target=data
                    for segment in value["$ref"][2:].split("/"): target=target[segment.replace("~1","/").replace("~0","~")]
                for child in value.values(): refs(child)
            elif isinstance(value,list):
                for child in value:refs(child)
        refs(data)
    links=0
    for path in DOCS.glob("*.md"):
        for link in re.findall(r"\]\(([^)]+)\)",path.read_text(encoding="utf-8")):
            if link.startswith(("http:","https:","#")):continue
            target=(path.parent/link.split("#")[0]).resolve()
            assert target.exists() or target==(REPORTS/"delivery-summary.json").resolve(),(path.name,link)
            links+=1
    tests={}
    for name in ("ai-tests.xml","backend-tests.xml"):
        suites=ET.parse(REPORTS/name).getroot().findall("testsuite")
        value={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ("tests","failures","errors","skipped")}
        assert value["failures"]==value["errors"]==0,(name,value)
        value["passed"]=value["tests"]-value["skipped"]
        tests[name]=value
    changes=subprocess.run(["git","diff","--name-only","--","backend/server/alembic","backend/server/app/models.py",
        "backend/server/app/execution_models.py","backend/server/app/services/draft_execution.py"],cwd=ROOT,capture_output=True,check=True)
    assert not changes.stdout.strip(),"Business schema/migration/execution owner files changed"
    evaluation=load(REPORTS/"real-first-summary.json")
    replay=load(REPORTS/"final-plan-replay.json")
    assert replay["actual_new_model_calls"]==0 and replay["passed"]==replay["cases"]
    value={"source":"local_delivery_validation","runtime_files":len(files),"contract_files":len(recorded),
        "document_links_checked":links,"tests":tests,"evaluation":evaluation,
        "saved_plan_replay":{"passed":replay["passed"],"cases":replay["cases"],"model_calls":0},
        "business_schema_or_execution_files_changed":False,"frontend_modified":False,
        "deployed":False,"app_joint_acceptance":False,"postgres_verified":False}
    (REPORTS/"delivery-summary.json").write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in value.items() if k!="evaluation"},ensure_ascii=False))


if __name__=="__main__":main()
