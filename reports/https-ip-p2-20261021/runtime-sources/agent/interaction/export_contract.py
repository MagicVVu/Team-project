import json
from pathlib import Path
from unittest.mock import patch
from .app import create_app
from .schemas import ContinuationContext,Message
from .session import Session
from .tasks import Task,Draft


def export():
    target=Path(__file__).resolve().parents[2]/"docs/versions/V1-P5"
    target.mkdir(parents=True,exist_ok=True)
    with patch.dict("os.environ",{"AI_SERVICE_TOKEN":"contract-export-only","P3_ENGINE":"rules"}):
        schema=create_app(reader=object()).openapi()
    documents={"ai-openapi.json":schema,"reviewed-message.schema.json":Message.model_json_schema(),
        "continuation.schema.json":ContinuationContext.model_json_schema(),"input-session.schema.json":Session.model_json_schema(),
        "public-task.schema.json":Task.model_json_schema(),"public-draft.schema.json":Draft.model_json_schema()}
    for name,data in documents.items():
        (target/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(target)


if __name__=="__main__": export()
