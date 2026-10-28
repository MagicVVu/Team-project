from decimal import Decimal
from uuid import uuid4

from .schemas import Command

UNITS = {"毫升": "ml", "ml": "ml", "mL": "ml", "升": "L", "l": "L", "L": "L",
         "克": "g", "g": "g", "千克": "kg", "公斤": "kg", "kg": "kg",
         "盒": "盒", "瓶": "瓶", "包": "包", "袋": "袋", "个": "个", "卷": "卷", "片": "片",
         "吨": "吨", "台": "台"}
SCALES = {"ml": ("volume", Decimal(1)), "L": ("volume", Decimal(1000)),
          "g": ("mass", Decimal(1)), "kg": ("mass", Decimal(1000)),
          "吨": ("mass", Decimal(1000000))}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def normalize_unit(unit: str) -> str:
    if unit not in UNITS:
        raise DomainError("INVALID_UNIT", "请选择盒、瓶、包、袋、个、卷、片、台、吨、ml、L、g 或 kg。")
    return UNITS[unit]


def convert(quantity: Decimal, source: str, target: str) -> Decimal:
    source, target = normalize_unit(source), normalize_unit(target)
    if source == target:
        return quantity
    if source in SCALES and target in SCALES and SCALES[source][0] == SCALES[target][0]:
        return quantity * SCALES[source][1] / SCALES[target][1]
    raise DomainError("INVALID_UNIT", "单位不兼容，不能猜测一盒或一瓶的容量。")


def normalize_command(command: Command) -> Command:
    command = command.model_copy(update={"name": command.name.strip(), "unit": normalize_unit(command.unit)})
    if not command.name or command.quantity > Decimal("1000000000"):
        raise DomainError("VALIDATION_ERROR", "名称不能为空，数量不能超过 10 亿。")
    if command.quantity.as_tuple().exponent < -6:
        raise DomainError("VALIDATION_ERROR", "数量最多保留六位小数。")
    if command.action == "CONSUME" and (not command.batch_id or command.expected_version is None):
        raise DomainError("VALIDATION_ERROR", "消耗必须选择批次并携带版本。")
    if command.action != "CONSUME" and (command.batch_id is not None or command.expected_version is not None):
        raise DomainError("VALIDATION_ERROR", "新增和采购不能指定库存批次或版本。")
    if command.purchased_at and command.label_expiry and command.label_expiry < command.purchased_at:
        raise DomainError("VALIDATION_ERROR", "标签日期早于购入日期，请核对。")
    return command
