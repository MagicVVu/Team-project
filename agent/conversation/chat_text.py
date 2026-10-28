"""P8 presentation rules. No inferred facts, extra extraction or inventory writes."""
import re

FIELDS = {"name":"物品名称", "quantity":"数量", "unit":"单位", "location":"存放位置",
          "to_location":"目标位置", "purchased_at":"购入日期", "label_expiry":"有效期",
          "opened_at":"开封日期", "batch_id":"库存批次"}
QUICK = {
    "CHAT_GREETING": (r"(?:你好|您好|嗨|哈喽|hello|hi)[！!。.]?", "你好，我是家庭库存助手。可以帮你查数量和位置，或整理库存操作草稿。试试“牛奶还有多少”。"),
    "CHAT_HELP": (r"(?:帮助|怎么用|你能做什么|你会什么|使用说明|help)[？?。]?", "可以查库存、位置，或整理新增、消耗、移动、开封、丢弃和采购草稿。缺信息时我会继续询问，实际操作需要你确认；能否执行以当前服务能力为准。"),
    "CHAT_THANKS": (r"(?:谢谢|谢谢你|多谢|感谢|thanks)[！!。.]?", "不客气。可以继续补充当前任务，或说“开始新任务”。"),
}
MESSAGES = {
    "REFERENCE_REQUIRED":"请先选择一个库存批次，或写明物品名称，我再查询它的位置。",
    "REFERENCE_EXPIRED":"上次选择已过期，请重新查询或选择批次。",
    "REFERENCE_TERMINAL":"这批库存已经结束，请重新选择有效批次。",
    "VERSION_CONFLICT":"这批库存刚刚发生变化，请核对最新候选后重新选择。",
    "PLANNING_CONTEXT_UNAVAILABLE":"当前还没有接通统计和预测所需的资料，暂时无法提供可靠结果。你仍可以查询库存数量和位置。",
    "MODEL_TIMEOUT":"理解这句话超时了，原文已保留。不会自动再次调用模型，请先核实原任务状态。",
    "MODEL_UNAVAILABLE":"暂时无法理解这句话，原文已保留。你可以稍后核实原任务，或手动填写。",
    "AGENT_TIMEOUT":"本次处理超时，原文和已填字段已保留。请先恢复任务并核实结果。",
    "HOUSEHOLD_FORBIDDEN":"当前账号无法访问这项家庭资料，请重新选择有权限的家庭。",
    "DRAFT_EDIT_REQUIRES_FORM":"这项内容需要在待确认草稿中修改，请先核对草稿。尚未执行。",
}


def quick_response(text):
    for code, (pattern, reply) in QUICK.items():
        if re.fullmatch(pattern, text.strip(), re.IGNORECASE):
            return code, reply
    return None


def present(result):
    """Only rephrase known state. Never convert a preview into a success receipt."""
    if result.error_code in MESSAGES:
        return MESSAGES[result.error_code]
    if result.status == "needs_clarification":
        fields = result.missing_fields or getattr(result.clarification, "allowed_fields", [])
        if "batch_id" in fields and result.candidates:
            return f"找到了{len(result.candidates)}个候选批次，请选择要处理的那一批。可以点击候选；支持续接的页面也可以回复“第二个”。尚未执行。"
        if fields:
            return "还需要" + "、".join(FIELDS.get(f, f) for f in fields) + "。请补充后继续，尚未执行。"
    return result.reply
