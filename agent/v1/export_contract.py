"""Local-only contract export, excluded from runtime synchronization."""
import json
import os
from pathlib import Path
from unittest.mock import patch
from .app import create_app
from .schemas import PlanningSnapshot, CommitReceipt, LocalContext, SelectionEnvelope, FeedbackRequest
from .tasks import Task, Draft

def export():
    target=Path(__file__).resolve().parents[2]/"docs/versions/V1-P6"
    target.mkdir(parents=True,exist_ok=True)
    with patch.dict(os.environ,{"AI_SERVICE_TOKEN":"contract-export-only","P3_ENGINE":"rules"}):
        app=create_app(reader=object())
        schema=app.openapi()
    documents={"ai-openapi.json":schema,"planning-context.schema.json":PlanningSnapshot.model_json_schema(),
        "operation-receipt.schema.json":CommitReceipt.model_json_schema(),
        "local-continuation.schema.json":LocalContext.model_json_schema(),
        "batch-selection.schema.json":SelectionEnvelope.model_json_schema(),
        "public-task.schema.json":Task.model_json_schema(),"public-draft.schema.json":Draft.model_json_schema()}
    security={"service_bearer":{"type":"http","scheme":"bearer"}}
    # These routes are proposals for a future backend read module, not deployed routes.
    backend={"openapi":"3.1.0","info":{"title":"Proposed V1 backend read tools","version":"v1-read-1"},
        "x-deployment-status":"reserved_not_deployed","components":{"securitySchemes":security},
        "paths":{}}
    for path,model,summary in [
        ("/internal/v1/planning/context",PlanningSnapshot,"完整同快照规划事实"),
        ("/internal/v1/operations/{operation_id}",CommitReceipt,"只读业务提交凭证")]:
        model_schema=model.model_json_schema()
        definitions=model_schema.pop("$defs",{})
        model_schema=json.loads(json.dumps(model_schema).replace("#/$defs/","#/components/schemas/"))
        backend["components"].setdefault("schemas",{}).update(json.loads(json.dumps(definitions).replace("#/$defs/","#/components/schemas/")))
        parameters=[{"name":n,"in":"header","required":True,"schema":{"type":"string"}} for n in ("X-User-Id","X-Household-Id")]
        if "{operation_id}" in path:
            parameters.append({"name":"operation_id","in":"path","required":True,"schema":{"type":"string","maxLength":100}})
        else:
            parameters.extend([{"name":n,"in":"query","required":False,"schema":{"type":"string"}} for n in ("name","item_key")])
        backend["paths"][path]={"get":{"summary":summary,"security":[{"service_bearer":[]}],"parameters":parameters,
            "responses":{"200":{"description":"成功；后端验证身份和家庭授权","content":{"application/json":{"schema":{"type":"object",
                "required":["data"],"properties":{"data":model_schema}}}}},
                "401":{"description":"内部服务认证失败"},"404":{"description":"模块未就绪或资源/家庭不可访问"},
                "409":{"description":"事实冲突或无法保证完整快照"}}}}
    documents["backend-read-openapi.json"]=backend
    for name,value in documents.items():
        (target/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(target)

if __name__=="__main__": export()
