"""Shared, deterministic text evidence for P0/P1 and their callers.

Only literal fields are extracted. Relative ADD dates remain clarification
requests; dates are removed before numbers are read as quantities.
"""
import re
from decimal import Decimal, InvalidOperation

NUMBER_PATTERN = r"-?\d+(?:\.\d+)?|[零一二两三四五六七八九十]+"
UNIT_PATTERN = r"毫升|千克|公斤|ml|mL|kg|升|克|L|g|盒|瓶|包|袋|个|卷|片|吨|台"
AMOUNT_PATTERN = rf"({NUMBER_PATTERN})\s*({UNIT_PATTERN})"
DATE_PATTERN = r"\d{4}-\d{1,2}-\d{1,2}"
RELATIVE_PATTERN = r"今天|昨天|明天|前天|上周|上个月|前几天|最近"
DATE_LABELS = {
    "purchased_at": r"购入日期|购买日期|购入时间|购买时间|买入日期",
    "label_expiry": r"标签到期日期|到期日期|有效期至|保质期至|有效期|到期日",
}
ACTION_PATTERNS = {
    "PLAN_ADD": r"(?:采购|购物)清单(?:加入|添加|加)?|加入采购(?:清单)?|加入购物清单|计划买|要买",
    "ADD": r"买了|新增|添加|入库|补货",
    "CONSUME": rf"(?:喝(?:了|掉|完)?|吃(?:了|掉|完)?|用了|用掉|用完|消耗|减去|减少|减(?=\s*(?:{NUMBER_PATTERN})))(?:了)?",
    "OPEN": r"(?:开封|打开)(?:了)?",
    "MOVE": r"移动到|移到|移至|挪到|搬到|移动",
    "DISCARD": r"扔掉|丢弃|报废|倒掉",
}
CHINESE = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
           "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def number(value):
    if value in CHINESE:
        return Decimal(CHINESE[value])
    if value.count("十") == 1 and len(value) <= 3:
        left, right = value.split("十", 1)
        if (not left or left in CHINESE) and (not right or right in CHINESE):
            return Decimal(CHINESE.get(left, 1) * 10 + CHINESE.get(right, 0))
    try:
        result = Decimal(value)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def actions(text):
    # Remove a complete procurement phrase first: its “添加” is not a
    # second ADD action. Other verbs elsewhere still count as separate actions.
    plan = re.search(ACTION_PATTERNS["PLAN_ADD"], text)
    remainder = re.sub(ACTION_PATTERNS["PLAN_ADD"], "", text)
    found = {key for key, pattern in ACTION_PATTERNS.items()
             if key != "PLAN_ADD" and re.search(pattern, remainder)}
    return found | ({"PLAN_ADD"} if plan else set())


def quantity_evidence(text):
    clean = re.sub(DATE_PATTERN, "", text)
    return [number(match[0]) for match in re.finditer(NUMBER_PATTERN, clean)]


def multiple_items(name):
    # “和润牛奶” and “和味饼干” start with 和; a conjunction has a
    # nonempty item on both sides. Never use a raw “和 in text” guard.
    return bool(name and re.search(r"以及|、|(?<=\w)\s*(?:和|[,，])\s*(?=\w)", name))


def date_fields(text):
    values = {}
    for field, label in DATE_LABELS.items():
        match = re.search(rf"(?:{label})\s*[:：]?\s*({DATE_PATTERN}|{RELATIVE_PATTERN})", text)
        if match:
            values[field] = match[1]
    prefix = re.search(rf"({DATE_PATTERN})\s*(?:买了|新增|添加|入库)", text)
    if prefix and "purchased_at" not in values:
        values["purchased_at"] = prefix[1]
    return values


def fields(text, intent):
    dates = date_fields(text) if intent == "ADD" else {}
    value = text.strip()
    for label in DATE_LABELS.values():
        value = re.sub(rf"(?:{label})\s*[:：]?\s*(?:{DATE_PATTERN}|{RELATIVE_PATTERN})", "", value)
    value = re.sub(DATE_PATTERN, "", value)
    date_match = re.search(rf"{DATE_PATTERN}|{RELATIVE_PATTERN}", text)
    value = re.sub(RELATIVE_PATTERN, "", value)
    target = re.search(r"(?:移动到|移到|移至|挪到|搬到)\s*([^，。,；;！？!?]+)", value)
    location = re.search(r"(?:放在|放到|放)\s*([^，。,；;！？!?]+)", value) if intent == "ADD" else None
    if target:
        value = value[:target.start()]
    elif location:
        value = value[:location.start()]
    amounts = list(re.finditer(AMOUNT_PATTERN, value))
    quantity = number(amounts[0][1]) if amounts else None
    unit = amounts[0][2] if amounts else None
    metadata_unit = re.search(rf"单位\s*[:：]?\s*({UNIT_PATTERN})", value)
    unit_conflict = bool(metadata_unit and unit and unit != metadata_unit[1])
    if metadata_unit:
        unit = unit or metadata_unit[1]
        value = value[:metadata_unit.start()] + value[metadata_unit.end():]
    # Procurement must be stripped before its component verb 添加.
    # Match verbs while quantity evidence still exists (减 uses a lookahead).
    for pattern in ACTION_PATTERNS.values():
        value = re.sub(pattern, "", value)
    value = re.sub(AMOUNT_PATTERN, "", value)
    value = re.sub(r"^(?:请|帮我(?:记一下|记录一下)?|麻烦|记一下|记录一下|把|将)+", "", value)
    value = re.sub(r"(?:谢谢你?|谢谢大家)[，。！？!?\s]*$", "", value)
    # Strip vague phrases before bare-number matching: the 一 in 一些 is
    # not an explicit quantity of one.
    value = re.sub(r"一些|一点|大概|几盒|半盒|快用完", "", value)
    if quantity is None:
        bare = re.search(rf"^\s*({NUMBER_PATTERN})|({NUMBER_PATTERN})\s*$", value)
        if bare:
            quantity = number(bare[1] or bare[2])
            value = value[:bare.start()] + value[bare.end():]
    value = re.sub(r"^(?:查一下|查询|查看|找一下|看看|查|找)", "", value)
    if intent == "QUERY_LOCATION":
        value = re.sub(r"放在哪里|放哪里|放在哪(?:里)?|放哪|在哪里|在哪(?:里)?|哪里|位置", "", value)
    elif intent == "QUERY_INVENTORY":
        value = re.sub(r"库存(?:有多少)?|还有多少|还剩多少|剩余多少|剩多少|有多少|多少|有什么|还有|剩余|剩", "", value)
        value = re.sub(r"家里|所有|全部|列表", "", value)
    value = re.sub(r"剩下的(?:都)?|剩余的(?:都)?|全部|全都|整批|其中|只|一部分|部分|一些|一点|大概|几盒|半盒|快用完", "", value)
    value = re.sub(r"(?:了|的|呢|吗)+$", "", value.strip(" ，。,；;！？!?？"))
    value = value.strip(" ，。,；;！？!?？")
    if intent == "QUERY_LOCATION" and value in {"东西", "物品"}:
        value = ""
    uncertain = ["quantity"] if re.search(r"一些|一点|大概|几盒|半盒|快用完", text) else []
    if unit_conflict:
        uncertain.append("unit")
    if intent == "ADD":
        if re.search(RELATIVE_PATTERN, text):
            uncertain.append("purchased_at")
        if not dates and re.search(DATE_PATTERN + r"|保质期|到期", text):
            uncertain.append("purchased_at")
    multi = multiple_items(value) or len(amounts) > 1
    location_value = location[1].strip() if location else None
    target_value = target[1].strip() if target else None
    if len(value) > 80:
        value = ""
        uncertain.append("name")
    if location_value and len(location_value) > 120:
        location_value = None
        uncertain.append("location")
    if target_value and len(target_value) > 120:
        target_value = None
        uncertain.append("to_location")
    return dict(name=value or None, quantity=quantity, unit=unit,
                location=location_value,
                purchased_at=dates.get("purchased_at"), label_expiry=dates.get("label_expiry"),
                opened_at=date_match[0] if intent == "OPEN" and date_match else None,
                to_location=target_value,
                multiple_items=multi,
                uncertainties=uncertain)
