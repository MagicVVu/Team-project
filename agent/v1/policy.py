"""Literal new V1 semantics. No model-generated quantities, IDs or locations."""
import re
from p0.text import AMOUNT_PATTERN, actions, multiple_items

def local_request(text):
    value = re.sub(r"^(?:请|帮我|麻烦|查一下|查询|查看|看看)+", "", text.strip()).strip(" ，。！？!?")
    if re.fullmatch(r"(?:家里)?(?:今天|今日)?(?:有什么|有哪些|需要)?(?:关注|关注事项|库存关注|需要关注什么|有什么需要关注|库存概览|库存摘要)(?:的|事项)?", value):
        return "overview", None
    if re.fullmatch(r"(?:哪些|什么)(?:东西|物品)(?:还)?(?:没定位|没有定位|未定位)|(?:查看)?待定位(?:的)?(?:物品|东西)?", value):
        return "unlocated", None
    match = re.fullmatch(r"(.{1,120}?)(?:里|里面)?(?:有(?:什么|哪些)(?:物品|东西)?|都放了什么|的物品有哪些)", value)
    if match:
        return "location", match[1].strip()
    # Questions, uncertain tense and quantity-bearing input retain existing path.
    if re.search(r"什么时候|何时|还能|多久|几天|吗|呢|快|将|准备|预计|打算|明天|昨天|今天|[?？]", text):
        return None
    match = re.fullmatch(r"(?:把|将)?(?:这批|这盒|这个)?(.{0,80}?)(?:已经|已|全都|全部|都)*(?:用完|喝完|吃完)(?:了)?", value)
    if match and not re.search(AMOUNT_PATTERN, value):
        name = match[1].strip()
        name = re.sub(r"(?:已经|全都|全部|已|都)$", "", name)
        if (not name or not multiple_items(name)) and not (actions(value) - {"CONSUME"}):
            return "finish", name or None
    return None

FACT_LABELS = {
    "category":"登记类别", "label_expiry":"包装标签日期", "label_date_type":"标签日期类型",
    "label_context_valid":"标签对当前物品状态的适用情况", "storage_condition":"实际登记保存条件",
    "label_storage_condition":"包装要求的保存条件", "is_opened":"开封状态", "opened_at":"开封日期",
    "applicable_reviewed_rule":"适用的人工审核规则", "label_date_rule":"标签日期规则",
    "storage_rule":"保存条件规则", "after_open_rule":"商品包装的开封要求", "rule_resolution":"规则冲突处理",
    "purchased_at_or_label_expiry":"购入与标签日期",
}
