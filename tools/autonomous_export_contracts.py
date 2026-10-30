"""Local-only OpenAPI export; no database connection or credential exposure."""
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/"docs/versions/V1-P8.6/contracts"
sys.path.insert(0,str(ROOT/"agent"))


def write(name,value):
    (TARGET/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def main():
    from conversation.autonomous.app import create_app
    from conversation.autonomous.schemas import RunRequest,RunResponse,Decision
    from conversation.p85.schemas import P85ResolveRequest,P85Resolved
    from conversation.memory_schemas import MemoryContext
    TARGET.mkdir(parents=True,exist_ok=True)
    with patch.dict(os.environ,{"AI_SERVICE_TOKEN":"export-placeholder-not-real","P3_ENGINE":"rules"}):
        ai=create_app(reader=object()).openapi()
    ai.update({"x-deployment-status":"local_source_contract_not_deployed","x-conversation-dialogue-protocol":"inventory-autonomous-1"})
    write("ai-openapi.json",ai)
    for name,model in {"run-request":RunRequest,"run-response":RunResponse,"decision":Decision,
        "context":MemoryContext,"revalidation-request":P85ResolveRequest,"revalidation-response":P85Resolved}.items():
        write(name+".schema.json",model.model_json_schema())
    sys.path.insert(0,str(ROOT/"backend/server"))
    from sqlalchemy import create_engine
    with patch.dict(os.environ,{"DB_PASSWORD":"unused-local-export"}),patch("sqlalchemy.create_engine",return_value=create_engine("sqlite://")):
        from app.main import app
        from app.memory_schemas import Message,Response,Page,Recovery
    api=app.openapi()
    api.update({"x-deployment-status":"local_source_contract_not_deployed",
        "x-conversation-memory-protocol":"conversation-memory-1","x-conversation-dialogue-protocol":"inventory-autonomous-1"})
    write("backend-openapi.json",api)
    for name,model in {"public-message":Message,"public-response":Response,"conversation-page":Page,"recovery":Recovery}.items():
        write(name+".schema.json",model.model_json_schema())
    names=["ai-openapi.json","backend-openapi.json",*[n+".schema.json" for n in
        ("run-request","run-response","decision","context","revalidation-request","revalidation-response",
         "public-message","public-response","conversation-page","recovery")]]
    write("manifest.json",{"stage":"V1-P8.6","ai_version":"0.8.6",
        "protocol":"inventory-autonomous-1","deployment":"local_only",
        "files":{n:hashlib.sha256((TARGET/n).read_bytes()).hexdigest() for n in names}})
    from integration.source_manifest import manifest
    (TARGET.parent/"runtime-source-manifest.json").write_text(json.dumps(manifest(),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"contracts":len(names),"database_connected":False,"deployed":False}))


if __name__=="__main__": main()
