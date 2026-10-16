import json
import re
from p0.deepseek import DeepSeekEngine as BaseEngine
from p0.engines import EngineError
from p3.schemas import Parsed
from interaction.engines import SYSTEM_PROMPT as P5_PROMPT, RuleEngine as BaseRuleEngine

PROMPT_VERSION = "v1-extract-1"
SYSTEM_PROMPT = P5_PROMPT + """
输出一个JSON对象，必须有intent。禁止Markdown、解释、代码围栏及额外字段。
window_days是整数，不指定时间时必须28；draft_mode是布尔值，不要求草稿时必须false。
不要把可选控制字段输出null；不输出库存、批次ID、速率、推荐量或真实事实。
"""

def parse_json_output(content):
    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values: raise ValueError("Duplicate key")
            values[key] = value
        return values
    def constant(value):
        raise ValueError("Nonfinite JSON")
    try:
        # An exact whole-document fence is formatting only. Never extract JSON
        # from an arbitrary paragraph or discard competing objects.
        value = content.strip()
        fence = re.fullmatch(r"```(?:json)?\s*\n([\s\S]*?)\n```", value)
        if fence: value = fence[1].strip()
        data = json.loads(value, object_pairs_hook=unique, parse_constant=constant)
        if not isinstance(data, dict) or not isinstance(data.get("intent"), str):
            raise ValueError("Missing intent")
        if "window_days" in data and (type(data["window_days"]) is not int):
            raise ValueError("Invalid window")
        for key in ("draft_mode", "multiple_items", "multiple_actions", "partial_batch"):
            if key in data and type(data[key]) is not bool: raise ValueError("Invalid flag")
        return Parsed.model_validate(data)
    except (ValueError, TypeError, AttributeError):
        raise EngineError("INVALID_MODEL_OUTPUT") from None

class DeepSeekEngine(BaseEngine):
    def __init__(self, budget=None):
        super().__init__(budget, system_prompt=SYSTEM_PROMPT, output_parser=parse_json_output)

class RuleEngine(BaseRuleEngine):
    async def extract(self, text):
        parsed = await super().extract(text)
        if parsed.intent == "ADD" and re.match(r"^新买了", text) and parsed.name and parsed.name.startswith("新"):
            candidate = parsed.name[1:]
            if candidate and candidate in text:
                parsed.name = candidate
        return parsed
