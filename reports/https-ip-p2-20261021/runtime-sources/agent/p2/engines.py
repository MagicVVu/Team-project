import json
import re

from p0.deepseek import DeepSeekEngine as BaseDeepSeekEngine
from p0.engines import EngineError
from p1.engines import SYSTEM_PROMPT as P1_PROMPT, RuleEngine as P1RuleEngine
from .schemas import Parsed

PROMPT_VERSION = "p2-extract-1"
SYSTEM_PROMPT = P1_PROMPT.replace(
    "不支持风险判断、耗尽预测、自动采购推荐、下单、拆批或语音音频。",
    "支持风险查询 QUERY_RISK；不支持耗尽预测、自动采购推荐、下单、拆批或语音音频。"
).replace(
    "QUERY_LOCATION, PLAN_ADD, OPEN, MOVE, DISCARD, UNSUPPORTED。",
    "QUERY_LOCATION, PLAN_ADD, OPEN, MOVE, DISCARD, QUERY_RISK, UNSUPPORTED。"
) + """
风险查询包括：哪些需要关注、哪些快过期、牛奶为什么提醒、牛奶还能吃吗、药品过期了吗、食品保存是否合规。
QUERY_RISK 只提取物品名（原文未指定时 name=null），不生成风险等级、天数、建议、规则或库存事实。
风险问题中的“已开封/放在冰箱/日期”等仅是用户提问，不能作为库存更新或已确认事实。
“牛奶昨天开封了”为 OPEN；“开封的牛奶还能喝吗”为 QUERY_RISK。
如果同时要求变更及风险评估（如“开封牛奶然后判断风险”），设 multiple_actions=true，分次处理。
"""

RISK_PATTERN = r"风险|需要关注|需关注|需要注意|快过期|临期|过期(?:了没有|了吗|没有|没|了|吗)|为什么(?:被)?(?:提醒|关注)|为何(?:被)?提醒|还能(?:吃|喝|用)|能不能(?:吃|喝|用)|安全吗|是否安全|保存.*(?:合规|符合|要求)|变质"


def risk_question(text):
    return bool(re.search(RISK_PATTERN, text))


def parse_json_output(content):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        return Parsed.model_validate(json.loads(content, object_pairs_hook=unique))
    except (ValueError, TypeError):
        raise EngineError("INVALID_MODEL_OUTPUT") from None


class DeepSeekEngine(BaseDeepSeekEngine):
    def __init__(self, budget=None):
        super().__init__(budget, system_prompt=SYSTEM_PROMPT, output_parser=parse_json_output)


class RuleEngine:
    async def extract(self, text):
        if not risk_question(text):
            return Parsed.model_validate((await P1RuleEngine().extract(text)).model_dump())
        if re.search(r"然后|并且|顺便|再帮我|同时", text):
            return Parsed(intent="UNSUPPORTED", multiple_actions=True)
        value = text
        value = re.sub(r"(?:放在|放到|保存在)[^，。？?]+", "", value)
        value = re.sub(r"\d{4}-\d{1,2}-\d{1,2}|今天|昨天|已经开封|已开封|开封的", "", value)
        value = re.sub(RISK_PATTERN, "", value)
        value = re.sub(r"请|帮我|看看|查看|检查|哪些|有什么|还有|家里|物品|这批|这盒|这个|是否|了|的|吗|呢|[，。？?\s]", "", value).strip()
        return Parsed(intent="QUERY_RISK", name=value or None,
                      multiple_items=bool(re.search(r"以及|、|和", value)))
