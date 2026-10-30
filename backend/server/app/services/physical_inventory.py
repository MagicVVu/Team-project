"""Expand intake amounts into independently addressable physical objects."""
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.models import InventoryItem

MEASURE_UNITS = {'毫升', 'ml', 'mL', '升', 'l', 'L', '克', 'g', '千克', '公斤', 'kg', '吨'}
MAX_OBJECTS = 10000


def intake_date():
    # Legacy callers may omit the device date. Never use the server's UTC date.
    return datetime.now(timezone.utc).astimezone(ZoneInfo('Asia/Shanghai')).date()


def intake_shape(quantity, unit, specification=None):
    quantity = Decimal(str(quantity))
    if not quantity.is_finite() or quantity <= 0:
        raise HTTPException(422, {'code': 'OBJECT_COUNT_MUST_BE_POSITIVE'})
    if unit in MEASURE_UNITS:
        measured = format(quantity.normalize(), 'f') + unit
        specification = (specification + ' · ' + measured) if specification else measured
        if len(specification) > 200:
            raise HTTPException(422, {'code': 'SPECIFICATION_TOO_LONG'})
        return 1, '份', specification
    if quantity != quantity.to_integral_value() or quantity > MAX_OBJECTS:
        raise HTTPException(422, {'code': 'OBJECT_COUNT_INVALID',
            'message': '物品数必须为1至10000的整数；重量或容量请填写到规格。'})
    return int(quantity), unit, specification


def add_objects(db, *, first_id, quantity, unit, actor_user_id, choice=None, product_id=None, **values):
    """The caller commits the entire group and its durable receipt together."""
    from app.product_models import ProductBatch
    from app.services.product_grouping import classify_new, lock_household
    lock_household(db, values['household_id'])
    specification = values.pop('specification', None)
    count, physical_unit, specification = intake_shape(quantity, unit, specification)
    if values.get('purchased_on') is None:
        values['purchased_on'] = intake_date()
    rows = [InventoryItem(id=first_id if index == 0 else uuid5(first_id, f'object:{index}'),
        unit=physical_unit, specification=specification, status='ACTIVE', version=1,
        created_by_user_id=actor_user_id, **values) for index in range(count)]
    db.add_all(rows)
    db.flush()
    if product_id is None:
        product = classify_new(db, rows[0], choice, actor_user_id)
        product_id = product.id
    else:
        db.add(ProductBatch(inventory_item_id=rows[0].id, product_id=product_id,
                           source='physical_inventory_intake', actor_user_id=actor_user_id))
    db.add_all([ProductBatch(inventory_item_id=row.id, product_id=product_id,
        source='physical_inventory_intake', actor_user_id=actor_user_id) for row in rows[1:]])
    db.flush()
    return rows
