"""Strict multi-field literal supplements. All-or-nothing; unknown spans fail closed."""
import re
from p0.text import AMOUNT_PATTERN, NUMBER_PATTERN, number
from p1.domain import parse_date

RESET = re.compile(r"(?:开始新任务|换个问题|换个话题|新建任务)[。！!]?$")


class SupplementError(ValueError):
    def __init__(self, code): self.code = code


def multiple_fields(text, allowed, timezone, now):
    # A location delimiter may occur immediately after a literal amount.
    value = re.sub(r"(?<=[盒瓶包袋个台份件克升])(?=放(?:在|到)?)", "，", text)
    chunks = [s.strip() for s in re.split(r"[，,；;]", value)]
    if len(chunks) > 9 or any(not s for s in chunks):
        return None
    answers = {}
    for chunk in chunks:
        part = {}
        amount = re.fullmatch(AMOUNT_PATTERN, re.sub(r"^(?:数量)?改(?:成|为)\s*", "", chunk))
        date = re.fullmatch(r"(开封日期|开封|购入日期|购入|有效期|到期日期)(?:是|为)?\s*(今天|昨天|\d{4}-\d{2}-\d{2})", chunk)
        place = re.fullmatch(r"(?:放到|放在|放|位置(?:改成|改为|是|为)?|目标位置(?:改成|改为|是|为)?)([^，,；;]{1,100})", chunk)
        if amount and {"quantity", "unit"} <= allowed:
            quantity = number(amount[1])
            if quantity is not None and quantity > 0:
                part = {"quantity":str(quantity), "unit":amount[2]}
            else:
                raise SupplementError("INVALID_QUANTITY")
        elif date:
            field = {"开封日期":"opened_at", "开封":"opened_at", "购入日期":"purchased_at", "购入":"purchased_at",
                     "有效期":"label_expiry", "到期日期":"label_expiry"}[date[1]]
            if field not in allowed:
                raise SupplementError("AMBIGUOUS_SUPPLEMENT")
            try:
                parsed = parse_date(date[2], now, timezone)
                if field == "opened_at" and parsed > parse_date("今天", now, timezone):
                    raise SupplementError("INVALID_DATE")
            except ValueError:
                raise SupplementError("INVALID_DATE") from None
            part = {field:date[2]}
        elif place:
            fields = allowed & {"location", "to_location"}
            if len(fields) == 1:
                part = {next(iter(fields)):place[1].strip()}
        elif "quantity" in allowed and re.fullmatch(NUMBER_PATTERN, chunk):
            quantity = number(chunk)
            if quantity is not None and quantity > 0:
                part = {"quantity":str(quantity)}
        if not part or not set(part) <= allowed:
            if answers: raise SupplementError("AMBIGUOUS_SUPPLEMENT")
            return None
        if any(k in answers for k in part): raise SupplementError("AMBIGUOUS_SUPPLEMENT")
        answers.update(part)
    return answers or None
