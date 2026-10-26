"""Explicit household identity and conservative aggregation, without name matching."""
from decimal import Decimal
from fastapi import HTTPException
from app.product_models import ProductBatch
from app.services import ledger
from app.services.ai_inventory import UNIT_CANONICAL

FACTORS = {'ml': ('volume', Decimal(1)), 'L': ('volume', Decimal(1000)),
           'g': ('mass', Decimal(1)), 'kg': ('mass', Decimal(1000)), '吨': ('mass', Decimal(1000000))}


def convert(quantity, source, target):
    source, target = UNIT_CANONICAL.get(source), UNIT_CANONICAL.get(target)
    if source is None or target is None:
        return None
    if source == target:
        return quantity
    if source not in FACTORS or target not in FACTORS or FACTORS[source][0] != FACTORS[target][0]:
        return None
    result = quantity * FACTORS[source][1] / FACTORS[target][1]
    if result > Decimal('1000000000') or result.normalize().as_tuple().exponent < -6:
        return None
    return result


def value(product):
    return {'product_id': str(product.id), 'name': product.name, 'specification': product.specification,
        'base_unit': product.base_unit, 'category': product.category, 'tags': product.tags_json,
        'version': product.version, 'source': product.source,
        'actor_user_id': str(product.actor_user_id), 'updated_at': str(product.created_at),
        'identity_status': 'household_attested', 'tag_source': 'household_attested',
        'platform_rule_review_status': 'unknown', 'risk_rule_version': None}


def aggregate(products, links, rows, profiles, projected, day):
    by_id = {r.id: r for r in rows}
    out = []
    for product in products:
        selected = sorted([by_id[l.inventory_item_id] for l in links if l.product_id == product.id
                           and l.inventory_item_id in by_id], key=lambda r: str(r.id))
        total, eligible, complete, batches = Decimal(0), Decimal(0), True, []
        for row in selected:
            converted = convert(row.quantity, row.unit, product.base_unit)
            complete &= converted is not None
            if converted is not None:
                total += converted
            expired = row.expires_on is not None and row.expires_on < day
            status_eligible = row.status == 'ACTIVE' and not expired
            if status_eligible and converted is not None:
                eligible += converted
            batches.append({'batch_id': str(row.id), 'version': row.version, 'quantity': str(row.quantity),
                'unit': row.unit, 'base_quantity': str(converted) if converted is not None else None,
                'location': row.storage_location, 'label_expiry': str(row.expires_on) if row.expires_on else None,
                'opened_at': str(row.opened_at) if row.opened_at else None, 'status': row.status,
                'expired': expired, 'expiry_known': row.expires_on is not None,
                'facts_version': profiles[row.id].version if row.id in profiles else 0,
                'stock_verification': projected.get(str(row.id), {}).get('stock_verification'),
                'mapping_status': 'household_attested'})
        out.append({**value(product), 'item_key': 'product:'+str(product.id), 'batches': batches,
            'quantity_complete': bool(complete), 'total_quantity': str(total) if complete else None,
            'nonexpired_active_quantity': str(eligible) if complete else None,
            'usable_quantity': None, 'consumption_coverage_days': None,
            'availability_status': 'risk_and_recording_review_required',
            'preferences_aggregation': 'batch_preferences_not_aggregated',
            'version_token': ledger.digest([value(product), batches])})
    return out
