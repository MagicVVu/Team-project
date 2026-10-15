import json
import re

from p0.deepseek import DeepSeekEngine as BaseDeepSeekEngine
from p0.engines import EngineError
from p2.engines import SYSTEM_PROMPT as P2_PROMPT, RuleEngine as P2RuleEngine
from .schemas import Parsed

PROMPT_VERSION = "p3-extract-2"
SYSTEM_PROMPT = P2_PROMPT.replace(
    "支持风险查询 QUERY_RISK；不支持耗尽预测、自动采购推荐、下单、拆批或语音音频。",
    "支持风险查询、消费统计、耗尽预测和补货建议；不支持下单、拆批或语音音频。"
).replace(
    "DISCARD, QUERY_RISK, UNSUPPORTED。",
    "DISCARD, QUERY_RISK, QUERY_CONSUMPTION, QUERY_FORECAST, SUGGEST_PURCHASE, UNSUPPORTED。"
).replace("缺字段为 null；", "未提供的名称、数量、单位、日期、位置为 null；") + """
V1-P3 扩展意图 QUERY_CONSUMPTION（已记录的消耗统计）、QUERY_FORECAST（未来能用多久/耗尽日期）、
SUGGEST_PURCHASE（应补什么/补货建议/依据库存生成补货草稿）。这些意图覆盖之前不支持预测推荐的限制。
仅提取 name、window_days（明确过去N天，1..28，默认28）、draft_mode（明确要求生成一项补货草稿时true）。
禁止生成速率、剩余日、建议数量、偏好、库存、事件、商品ID及事实。旧意图字段继续遵守原规则。
明确采购数量的“买2盒牛奶”仍为 PLAN_ADD；“给牛奶生成补货草稿”是 SUGGEST_PURCHASE。
多动作/多物品草稿设multiple_actions/multiple_items，查询全家统计或补货建议可以不指定name。
未知品名name=null；品名必须为原文连续片段。不要把问句或时间窗口当品名。超过28天查询不支持。
新增字段始终输出：window_days 必须是整数，未指定时为28，绝不能输出null；draft_mode必须是布尔值，默认为false，绝不能输出null。
示例：牛奶什么时候用完 -> {"intent":"QUERY_FORECAST","name":"牛奶","window_days":28,"draft_mode":false}
过去两周牛奶消耗统计 -> {"intent":"QUERY_CONSUMPTION","name":"牛奶","window_days":14,"draft_mode":false}
这个还能用多久 -> {"intent":"QUERY_FORECAST","name":null,"window_days":28,"draft_mode":false}
给牛奶生成补货草稿 -> {"intent":"SUGGEST_PURCHASE","name":"牛奶","window_days":28,"draft_mode":true}
"""


def parse_json_output(content):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    try:
        return Parsed.model_validate(json.loads(content, object_pairs_hook=unique))
    except (ValueError, TypeError):
        raise EngineError("INVALID_MODEL_OUTPUT") from None


class DeepSeekEngine(BaseDeepSeekEngine):
    def __init__(self, budget=None):
        super().__init__(budget, system_prompt=SYSTEM_PROMPT, output_parser=parse_json_output)


PATTERNS = {
    "SUGGEST_PURCHASE": r"补货建议|补货草稿|需要补什么|该补什么|应该买什么|建议补多少|建议买多少|需要补多少|生成.*补货|补货推荐",
    "QUERY_FORECAST": r"还能用多久|能用几天|还能喝几天|什么时候用完|何时用完|耗尽|几天用完|剩余天数|预计.*用完",
    "QUERY_CONSUMPTION": r"消耗统计|记录.*消耗|消耗了多少|用了多少|喝了多少|消费记录|消耗记录",
}


class RuleEngine:
    async def extract(self, text):
        matches = [intent for intent, pattern in PATTERNS.items() if re.search(pattern, text)]
        if not matches:
            return Parsed.model_validate((await P2RuleEngine().extract(text)).model_dump())
        if len(matches) > 1 or re.search(r"然后|并且|顺便|同时|再帮我", text):
            return Parsed(intent="UNSUPPORTED", multiple_actions=True)
        window = re.search(r"(?:过去|最近)(\d+)天", text)
        days = int(window[1]) if window else 14 if re.search(r"过去两周|最近两周", text) else 28
        if not 1 <= days <= 28:
            return Parsed(intent="UNSUPPORTED")
        intent = matches[0]
        value = re.sub(r"(?:过去|最近)\d+天|过去两周|最近两周|过去四周|最近四周", "", text)
        # Preserve only a literal span from the user's text as the item name.
        for pattern in (r"请|帮我|给|为|查询|查看|看看|生成|一份|一个|按记录|按现在记录的速度|按库存|家里|全家|所有物品|所有商品|记录的|记录了多少|记录了|预计|补货推荐",):
            value = re.sub(pattern, "", value)
        value = re.sub(r"补货建议|补货草稿|需要补什么|该补什么|应该买什么|建议补多少|建议买多少|需要补多少|还能用多久|能用几天|还能喝几天|什么时候用完|何时用完|耗尽日期|耗尽预测|耗尽|几天用完|剩余天数|消耗统计|消耗了多少|用了多少|喝了多少|消费记录|消耗记录|消耗|用完|这批|这个|这盒|[的了呢吗，。？?\s]", "", value)
        return Parsed(intent=intent, name=value or None, window_days=days,
                      draft_mode=bool(re.search(r"草稿", text)),
                      multiple_items=bool(re.search(r"以及|、|和", value)))
