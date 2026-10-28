"""Generic household discussion can be natural; business facts use read slots.

This is a conservative surface filter, not a general semantic truth checker.
It deliberately excludes inventory, receipt, risk and personal-memory claims.
"""
import re


def household_prose(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 800:
        return None
    if re.search(r"忽略.*规则|跳过确认|system|\{\{|```|<[^>]+>", text, re.I): return None
    # A generic suggestion about sorting expired items is not a claim that a
    # particular household item HAS expired. Keep those distinct.
    checked = re.sub(r"(?:明显)?过期的(?:物品|东西)?", "待核对物品", text)
    if re.search(r"库存|余量|还剩|剩余量|登记数量|到期|保质|过期|耗尽|风险|安全食用|放心吃|食用安全|不会变质|还能吃|能吃|回执|草稿|待购|采购清单", checked): return None
    if re.search(r"(?:今天|昨天|明天|后天|前天).{0,12}(?:开封|到期|消费|丢弃|入库)", checked): return None
    if re.search(r"(?:已经|已|刚刚|替你|帮你|为你|我把).{0,30}(?:执行|移动|消耗|丢弃|开封|登记|写入|扣减|取消|加入)|挪好了|记好了|操作成功|办妥|执行完|执行了|移到了|取消了|扣掉了|已完成|已处理", text): return None
    if re.search(r"(?:你之前|你上次|你刚才|记得你|你说过|你喜欢|你习惯)", text): return None
    # Generic organizing language ('one drawer', 'a small area') does not assert
    # inventory quantity. Do not reject it as if it said 'three cartons remain'.
    quantities = re.sub(r"[一两二三四五六七八九十1-9]个(?:[\u4e00-\u9fff]{0,8})?(?:区域|抽屉|柜子|收纳盒|篮子|目标|地方|问题|建议|角落|步骤|方案|思路|标签|计时器|清单|高频区)", "整理单元", text)
    quantities = re.sub(r"一个[“「][^”」]{1,30}[”」](?:的)?(?:位置|区域|目标)", "整理单元", quantities)
    if re.search(r"[\d一二两三四五六七八九十百千万半]+\s*(?:盒|瓶|包|袋|个|克|千克|公斤|毫升|升|吨|台|天|年|月|日)", quantities): return None
    # Location suggestions are fine; assertions about where an object IS are not.
    if re.search(r"放在|位于|就在|在.{0,12}(?:冰箱|厨房|冷藏室|柜子)", text) and not re.search(r"可以|建议|不妨|通常|如果|试着", text): return None
    numbers = re.sub(r"(?m)^\s*[1-4][.、]", "", text)
    if re.search(r"可以|建议|不妨|试着|先|定时|定个|设个|计时|休息", text):
        numbers = re.sub(r"\d{1,2}(?:\s*(?:-|–|—|~|～|至|到)\s*\d{1,2})?\s*(?:分钟|小时|秒)", "", numbers)
    if re.search(r"\d", numbers): return None
    return text.strip()


def fallback(user_text):
    """Stay on the user's topic when a proposed discussion answer is rejected."""
    if re.search(r"找不到|难找|总找", user_text):
        return "找东西找不到，确实容易烦。可以给常用物品定个固定位置，用完归位，再给收纳盒贴标签。你最常找不到哪类东西？"
    if re.search(r"累|烦|省心|轻松", user_text):
        return "听起来整理得有些累了。可以先休息一下，再从最顺手的小区域开始，收完就停，不用急着一次做好。你想先从哪里开始？"
    if "你好" in user_text:
        return "你好，慢慢整理就好。可以先挑一个小区域，我陪你一起理清思路。"
    if re.search(r"整理|收拾|收纳", user_text):
        return "可以先清出常用的台面，再把同类物品放到一起，用完归位。先从最容易收拾的一处开始会轻松一些。"
    return "可以接着聊。要核对具体物品、操作状态或之前的细节时，请指出你想继续的那件事。"
