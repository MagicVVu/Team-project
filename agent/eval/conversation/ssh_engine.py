"""Local evaluation transport; key stays on server, only synthetic text is sent.

No evaluation/fixture files are uploaded. Both existing ledgers are preserved;
the original local P0 ledger continues to account for every paid request.
"""
import asyncio
import json
from pathlib import Path
import subprocess
from p0.budget import Budget
from p0.engines import EngineError
from conversation.engines import SYSTEM_PROMPT
from v1.engines import parse_json_output

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[1]

SCRIPT = '''
import asyncio,json,os
from integration.runtime_config import environment
from conversation.engines import DeepSeekEngine
from p0.engines import EngineError
os.environ.update(environment())
async def main():
    engine=DeepSeekEngine()
    try:
        parsed=await engine.extract(TEXT_VALUE)
        print(json.dumps({'parsed':parsed.model_dump(mode='json'),'model':engine.last_model,'usage':engine.last_usage,'server_budget':engine.budget.summary()},ensure_ascii=True))
    except EngineError as error:
        print(json.dumps({'error_code':error.code,'usage':engine.last_usage,'server_budget':engine.budget.summary()}))
asyncio.run(main())
'''


class SSHDeepSeekEngine:
    def __init__(self):
        self.budget = Budget(ROOT/".cache/p0/budget.sqlite", ROOT/"eval/pricing.json")
        self.model, self.last_model = "deepseek-flash", None
        self.last_usage, self.server_budget = {}, None
        self.options = ["ssh", "-i", str(Path.home()/".ssh/magicvvu_ai_ed25519"),
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile="+(WORKSPACE/".runtime/p2-integration/known_hosts").as_posix(),
            "-o", "ConnectTimeout=5", "magicvvu_ai@8.134.172.165",
            "cd ~/workspace/agent && .venv-p2/bin/python -B -"]

    async def extract(self, text):
        self.last_model, self.last_usage = None, {}
        payload = {"model":self.model, "messages":[{"role":"system", "content":SYSTEM_PROMPT}, {"role":"user", "content":text}],
            "response_format":{"type":"json_object"}, "max_tokens":768, "thinking":{"type":"disabled"}, "stream":False}
        size = len(json.dumps(payload, ensure_ascii=False).encode())
        if size > 16000: raise EngineError("MODEL_INPUT_TOO_LARGE")
        call_id, _, pricing = self.budget.reserve(self.model, size+1024, 768)
        script = SCRIPT.replace("TEXT_VALUE", repr(text))
        try:
            proc = await asyncio.to_thread(subprocess.run, self.options, input=script.encode("utf-8"),
                capture_output=True, timeout=9.5, check=False)
            if proc.returncode != 0: raise EngineError("SSH_MODEL_UNAVAILABLE")
            value = json.loads(proc.stdout)
            self.last_usage, self.server_budget = value.get("usage", {}), value.get("server_budget")
            if self.last_usage: self.budget.settle(call_id, self.last_usage, pricing)
            if value.get("error_code"): raise EngineError(value["error_code"])
            self.last_model = value["model"]
            return parse_json_output(json.dumps(value["parsed"], ensure_ascii=False))
        except subprocess.TimeoutExpired:
            raise EngineError("MODEL_TIMEOUT") from None
        except (OSError, ValueError, KeyError, TypeError):
            raise EngineError("SSH_MODEL_UNAVAILABLE") from None
