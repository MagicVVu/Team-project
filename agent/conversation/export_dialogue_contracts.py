"""Export P8.4 locally; never overwrite a released P8.3 contract."""
import json
import os
from pathlib import Path
from unittest.mock import patch
from .app import create_app
from . import dialogue_schemas as schemas
from .memory_schemas import MemoryContext


def export():
    root=Path(__file__).resolve().parents[2]/"docs/versions/V1-P8.4/contracts"
    root.mkdir(parents=True,exist_ok=True)
    with patch.dict(os.environ,{"AI_SERVICE_TOKEN":"export-placeholder","P3_ENGINE":"rules"}):
        api=create_app(reader=object()).openapi()
    api.update({"x-deployment-status":"local_source_contract_not_deployed","x-conversation-memory-protocol":"conversation-memory-1",
                "x-conversation-dialogue-protocol":schemas.PROTOCOL})
    values={"ai-openapi.json":api,"context.schema.json":MemoryContext.model_json_schema()}
    for name,model in {"understand-request":schemas.Request,"understand-response":schemas.Understood,
        "resolve-request":schemas.ResolveRequest,"resolve-response":schemas.Resolved,
        "respond-request":schemas.RespondRequest,"respond-response":schemas.Responded}.items():
        values[name+".schema.json"]=model.model_json_schema()
    for name,value in values.items(): (root/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__": export()
