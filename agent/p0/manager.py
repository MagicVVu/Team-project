import asyncio
import re

from decimal import Decimal
from .domain import DomainError, UNITS, convert, new_id, normalize_command, normalize_unit
from .engines import DecisionEngine, EngineError
from .schemas import AgentResult, Command, Intent, Message, Scope
from .tools import InventoryReader


class Manager:
    def __init__(self, engine: DecisionEngine, reader: InventoryReader):
        self.engine, self.reader = engine, reader

    async def handle(self, message: Message, scope: Scope) -> AgentResult:
        common = {"trace_id": new_id("trace"), "original_text": message.text}
        parsed = None
        batches = []
        try:
            # Deterministic guard, including when a model tries to obey injected text.
            if re.search(r"忽略.*(?:指令|规则|系统)|跳过确认|不[用要需]确认|直接(?:执行|扣减|落库)|(?:system|assistant)\s*:|删库", message.text, re.I):
                return AgentResult(**common, status="unsupported", intent=Intent.UNSUPPORTED, reply="库存变更需要先生成草稿并由你确认。")
            async with asyncio.timeout(10):
                parsed = await self.engine.extract(message.text)
            if parsed.intent == Intent.UNSUPPORTED or parsed.multiple_items:
                return AgentResult(**common, status="unsupported", intent=parsed.intent,
                                   reply="请一次提交一个物品的一种操作。当前支持新增、消耗、查询和加入采购清单。")
            if parsed.uncertainties:
                return AgentResult(**common, status="needs_clarification", intent=parsed.intent, reply="请明确模糊的数量或日期，也可在手动表单中补充。",
                                   missing_fields=parsed.uncertainties, manual_entry=True)
            missing = []
            writes = {Intent.ADD, Intent.CONSUME, Intent.PLAN_ADD}
            if parsed.intent in writes:
                # Ground the model's proposed fields in the input. Missing numbers/units
                # must not become invented defaults even when JSON is well formed.
                if re.search(r"和|以及|、", message.text):
                    return AgentResult(**common, status="unsupported", intent=parsed.intent, reply="请一次提交一个物品的一种操作。")
                if parsed.name and parsed.name.strip().casefold() not in message.text.casefold():
                    missing.append("name")
                number_words = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
                quantities = [Decimal(number_words[x]) if x in number_words else Decimal(x)
                              for x in re.findall(r"-?\d+(?:\.\d+)?|[零一二两三四五六七八九十]", message.text)]
                if parsed.quantity is not None and parsed.quantity not in quantities:
                    missing.append("quantity")
                if parsed.unit and not any(alias in message.text for alias, value in UNITS.items() if value == normalize_unit(parsed.unit)):
                    missing.append("unit")
                for field in ["purchased_at", "label_expiry"]:
                    value = getattr(parsed, field)
                    if value and value.isoformat() not in message.text:
                        missing.append(field)
            if parsed.intent in writes or parsed.intent == Intent.QUERY_LOCATION:
                if not parsed.name or not parsed.name.strip():
                    missing.append("name")
            if parsed.intent in writes:
                if parsed.quantity is None or parsed.quantity <= 0:
                    missing.append("quantity")
                if not parsed.unit:
                    missing.append("unit")
            if missing:
                missing = list(dict.fromkeys(missing))
                return AgentResult(**common, status="needs_clarification", intent=parsed.intent, reply="请补充或核对：" + "、".join(missing),
                                   missing_fields=missing, manual_entry=True)
            if parsed.intent in {Intent.QUERY_INVENTORY, Intent.QUERY_LOCATION, Intent.CONSUME}:
                batches = await self.reader.search(scope, parsed.name)
                # Defence in depth: tool results are never allowed to expand the household scope.
                if any(b.household_id != scope.household_id for b in batches):
                    raise DomainError("HOUSEHOLD_FORBIDDEN", "库存工具返回了其他家庭的数据。", 403)
            else:
                batches = []
            if parsed.intent in {Intent.QUERY_INVENTORY, Intent.QUERY_LOCATION}:
                summary = "；".join(f"{b.name}：{b.quantity}{b.unit}，{b.location or '待定位'}（批次 {b.id}）" for b in batches)
                return AgentResult(**common, status="answered", intent=parsed.intent, facts=batches, reply=summary or "没有找到匹配的在库物品。")
            if parsed.intent == Intent.CONSUME:
                active = [b for b in batches if b.status == "ACTIVE" and b.quantity > 0]
                if len(active) != 1:
                    return AgentResult(**common, status="needs_clarification", intent=parsed.intent, candidates=active,
                                       missing_fields=["batch_id"], manual_entry=True,
                                       reply="请选择要消耗的批次。" if active else "没有可消耗批次，请核对名称或库存。")
                batch = active[0]
                quantity = convert(parsed.quantity, parsed.unit, batch.unit)
                if quantity > batch.quantity:
                    return AgentResult(**common, status="needs_clarification", intent=parsed.intent, candidates=active,
                                       missing_fields=["quantity"], error_code="INSUFFICIENT_STOCK", manual_entry=True, reply="扣减量超过库存，请核对数量。")
                command = Command(action="CONSUME", name=batch.name, quantity=quantity, unit=batch.unit,
                                  batch_id=batch.id, expected_version=batch.version)
            else:
                command = Command(action=parsed.intent.value, name=parsed.name, quantity=parsed.quantity,
                                  unit=normalize_unit(parsed.unit), location=parsed.location,
                                  purchased_at=parsed.purchased_at, label_expiry=parsed.label_expiry)
            command = normalize_command(command)
            return AgentResult(**common, status="needs_confirmation", intent=parsed.intent, draft=command,
                               reply="草稿已生成，尚未写入库存。请检查或编辑后确认。")
        except DomainError as error:
            return AgentResult(**common, status="needs_clarification" if error.status == 422 else "error",
                               intent=parsed.intent if parsed else None, error_code=error.code, reply=error.message, manual_entry=True, retryable=error.status == 503,
                               candidates=[b for b in batches if b.household_id == scope.household_id and b.status == "ACTIVE"] if error.status == 422 else [],
                               missing_fields=["unit"] if error.code == "INVALID_UNIT" else [])
        except (EngineError, TimeoutError) as error:
            return AgentResult(**common, status="error", error_code=error.code if isinstance(error, EngineError) else "MODEL_TIMEOUT",
                               reply="AI 暂时无法处理，输入已保留。可以重试或使用手动表单。", retryable=True, manual_entry=True)
