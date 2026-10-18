from p0.deepseek import DeepSeekEngine as BaseEngine
from v1.engines import SYSTEM_PROMPT as BASE_PROMPT, parse_json_output, RuleEngine as BaseRuleEngine
import re

QUALIFIED_MOVE = re.compile(r"把([^\s，,。；;？?！!]{1,100}?)的([^\s，,。；;？?！!]{1,80}?)移(?:动)?到([^\s，,。；;？?！!]{1,100})[。！？?!]?")


class RuleEngine(BaseRuleEngine):
    async def extract(self, text):
        parsed = await super().extract(text)
        match = QUALIFIED_MOVE.fullmatch(text)
        if match and parsed.intent == "MOVE" and not parsed.partial_batch and not parsed.multiple_actions:
            parsed = parsed.model_copy(update={"name": match[2], "to_location": match[3]})
        return parsed

PROMPT_VERSION = "p7-extract-1"
SYSTEM_PROMPT = BASE_PROMPT + """
“它/这一批/这个”等是指代，不是商品名；不能把聊天历史或猜测补成名称。
含指代但没有明确商品名时name=null，仍提取原文明确的动作及字段。
最近对象由业务调用方提供并由确定性代码校验，你不得生成批次ID或版本。
"""


class DeepSeekEngine(BaseEngine):
    def __init__(self, budget=None):
        super().__init__(budget, system_prompt=SYSTEM_PROMPT, output_parser=parse_json_output)
