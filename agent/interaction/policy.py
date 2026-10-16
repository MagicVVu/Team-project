"""Conservative literal guards, never reconstruction of missing audio."""
import re
from p0.text import ACTION_PATTERNS

VERBS = "|".join(ACTION_PATTERNS.values())


def review_reason(text):
    if re.fullmatch(r"\s*(?:算了|取消|不用了|别做了)[。！!\s]*", extraction_text(text)):
        return "CANCELLED_INPUT"
    if (re.search(rf"(?:不要|不用|无需|不需要|不想|不打算|不必|没必要|别|并没有|没有|没)[^，。！？!?]{{0,24}}(?:{VERBS})", text)
        or re.search(rf"不(?:给我|帮我)?(?:{VERBS})",text)
        or re.search(r"(?:不要|别做了)[。！!\s]*$",text)):
        return "NEGATED_OPERATION"
    if re.search(r"说错了|口误|不对|改口|不是.+(?:而是|是)|还是|不确定|好像|可能|也许|大约|估计|应该是|大概|差不多", text):
        return "AMBIGUOUS_OR_CORRECTED_SPEECH"
    if re.search(r"他说|她说|别人说|有人说|假如|假设|如果", text):
        return "QUOTED_OR_HYPOTHETICAL_OPERATION"
    for quoted in re.findall(r'[“「"]([^”」"]+)[”」"]', text):
        if re.search(VERBS, quoted):
            return "QUOTED_OR_HYPOTHETICAL_OPERATION"
    return None


def extraction_text(text):
    # Only boundary fillers; do not delete negations, dates, corrections or
    # internal commas that signal multiple items/actions.
    return re.sub(r"^(?:(?:嗯|呃|额|啊)[，,、。\s]+)+", "", text.strip())


class ExtractionAdapter:
    def __init__(self, engine):
        self.engine = engine

    async def extract(self, text):
        return await self.engine.extract(extraction_text(text))
