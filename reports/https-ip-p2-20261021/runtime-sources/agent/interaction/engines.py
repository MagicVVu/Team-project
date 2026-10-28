from p0.deepseek import DeepSeekEngine as BaseDeepSeekEngine
from p3.engines import SYSTEM_PROMPT as P3_PROMPT,parse_json_output,RuleEngine

PROMPT_VERSION="p5-extract-1"
SYSTEM_PROMPT=P3_PROMPT+"""
P5 接收的是用户已核对的文字，不是音频。下面是固定动作语义补充：
“添加/新增/入库/买了”都为 ADD，即使是命令语气或缺数量。例：添加牛奶 -> ADD,name=牛奶,quantity=null,unit=null。
“添加2盒和润牛奶” -> ADD,name=和润牛奶,quantity=2,unit=盒,multiple_items=false。
和润、和味、不二家等是连续完整品牌名称，不是多个物品；只有确实多个物品才设 multiple_items=true。
只有“加入采购清单/购物清单/计划买/要买”是明确人工 PLAN_ADD；普通“添加”不等于采购。
SUGGEST_PURCHASE 中明确说“补货草稿/生成草稿”时 draft_mode=true；只是问补货建议时为false。
“牛奶补货草稿” -> SUGGEST_PURCHASE,name=牛奶,draft_mode=true,window_days=28，不能漏掉草稿标志。
不要从已删除的转写、语气词或商品常识补字段，不能猜测数量单位和日期。
"""


class DeepSeekEngine(BaseDeepSeekEngine):
    def __init__(self,budget=None):
        super().__init__(budget,system_prompt=SYSTEM_PROMPT,output_parser=parse_json_output)
