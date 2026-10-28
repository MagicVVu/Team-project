"""Explicit same-household classification, atomic with the new inventory batch.

Names only suggest candidates. A name match never constitutes permission to merge.
No quantities or original batch names are changed by classification.
"""
import unicodedata
from uuid import uuid5

from fastapi import HTTPException
from sqlalchemy import select

from app.models import InventoryItem
from app.product_models import Product, ProductBatch


def normalized_name(name):
    return unicodedata.normalize('NFKC', name).strip().casefold()


def name_match(left, right):
    """Exact names (even one character), or a contiguous shared pair of codepoints."""
    left, right = normalized_name(left), normalized_name(right)
    if not left or not right:
        return None
    if left == right:
        return {'match_type': 'exact', 'shared_text': left}
    pairs = {left[i:i+2] for i in range(len(left)-1)}
    for i in range(len(right)-1):
        pair = right[i:i+2]
        if pair in pairs:
            return {'match_type': 'substring', 'shared_text': pair}
    return None


def candidates(db, household_id, name, limit=200, offset=0):
    rows = db.execute(select(InventoryItem, Product).outerjoin(
        ProductBatch, ProductBatch.inventory_item_id == InventoryItem.id).outerjoin(
        Product, (Product.id == ProductBatch.product_id) & (Product.household_id == household_id))
        .where(InventoryItem.household_id == household_id).order_by(InventoryItem.id)).all()
    matches = []
    for item, product in rows:
        match = name_match(name, item.name)
        if match:
            matches.append({'inventory_item_id': str(item.id), 'name': item.name,
                'inventory_version': item.version, 'product_id': str(product.id) if product else None,
                'product_version': product.version if product else None,
                'product_name': product.name if product else None, 'unit': item.unit,
                'quantity': str(item.quantity), 'status': item.status, **match})
    matches.sort(key=lambda row: (row['match_type'] != 'exact', len(row['name']),
                                  row['name'], row['inventory_item_id']))
    return {'protocol_version': 'inventory-product-matches-1', 'items': matches[offset:offset+limit],
            'total': len(matches), 'limit': limit, 'offset': offset,
            'next_offset': offset+limit if offset+limit < len(matches) else None}


def category(value):
    return {'食品': 'food', 'food': 'food', '药品': 'medicine', 'medicine': 'medicine',
            '日用品': 'household', 'household': 'household'}.get(value, 'unknown')


def checked_product_name(name):
    if not name.strip() or len(name) > 80:
        raise HTTPException(422, {'code': 'PRODUCT_NAME_TOO_LONG',
                                  'message': '商品名称需为 1 至 80 字；请明确核对名称，不自动截断。'})
    return name


def shortest_member(members):
    return min(members, key=lambda row: (len(row.name), normalized_name(row.name), row.name, str(row.id)))


def singleton(db, item, actor_user_id, source='inventory_singleton', representative=None, product_id=None):
    """Call after inserting a batch; caller owns the transaction and its receipt."""
    prior = db.get(ProductBatch, item.id)
    if prior is not None:
        return db.get(Product, prior.product_id)
    representative = representative or item
    product = Product(id=product_id or uuid5(item.id, 'inventory-product'), household_id=item.household_id,
        name=checked_product_name(representative.name), base_unit=representative.unit, category=category(representative.category),
        specification=None, tags_json=[], source=source, actor_user_id=actor_user_id, version=1)
    db.add(product)
    db.flush()
    db.add(ProductBatch(inventory_item_id=item.id, product_id=product.id,
                        source=source, actor_user_id=actor_user_id))
    db.flush()
    return product


def refresh_linked_name(db, item, actor_user_id, create_if_missing=True):
    """A trusted purchase source can carry identity, including its shortest-name rule."""
    link = db.get(ProductBatch, item.id)
    if link is None:
        return singleton(db, item, actor_user_id, 'purchase_inventory_singleton') if create_if_missing else None
    product = db.scalar(select(Product).where(Product.id == link.product_id,
        Product.household_id == item.household_id).with_for_update()
        .execution_options(populate_existing=True))
    if product is None:
        raise HTTPException(404, {'code': 'GROUPING_PRODUCT_NOT_FOUND'})
    members = db.scalars(select(InventoryItem).join(ProductBatch,
        ProductBatch.inventory_item_id == InventoryItem.id).where(
        ProductBatch.product_id == product.id, InventoryItem.household_id == item.household_id)).all()
    product.name = checked_product_name(shortest_member(members).name)
    product.version += 1
    db.flush()
    return product


def classify_new(db, item, choice, actor_user_id):
    if choice is None or choice.mode == 'separate':
        return singleton(db, item, actor_user_id)
    candidate = db.scalar(select(InventoryItem).where(
        InventoryItem.id == choice.candidate_inventory_item_id,
        InventoryItem.household_id == item.household_id).with_for_update()
        .execution_options(populate_existing=True))
    if candidate is None or candidate.id == item.id:
        raise HTTPException(404, {'code': 'GROUPING_CANDIDATE_NOT_FOUND'})
    if candidate.version != choice.expected_inventory_version:
        raise HTTPException(409, {'code': 'GROUPING_CANDIDATE_CHANGED'})
    if name_match(item.name, candidate.name) is None:
        raise HTTPException(409, {'code': 'GROUPING_NAME_NO_LONGER_MATCHES'})
    link = db.scalar(select(ProductBatch).where(ProductBatch.inventory_item_id == candidate.id)
                     .execution_options(populate_existing=True))
    if link is None:
        if choice.expected_product_version is not None:
            raise HTTPException(409, {'code': 'GROUPING_PRODUCT_CHANGED'})
        product = singleton(db, candidate, actor_user_id, 'confirmed_inventory_grouping',
                            representative=shortest_member([candidate, item]),
                            product_id=uuid5(item.id, 'inventory-group-product'))
        candidate.version += 1
    else:
        product = db.scalar(select(Product).where(Product.id == link.product_id,
            Product.household_id == item.household_id).with_for_update()
            .execution_options(populate_existing=True))
        if product is None:
            raise HTTPException(404, {'code': 'GROUPING_PRODUCT_NOT_FOUND'})
        if choice.expected_product_version != product.version:
            raise HTTPException(409, {'code': 'GROUPING_PRODUCT_CHANGED'})
        product.version += 1
    members = db.scalars(select(InventoryItem).join(ProductBatch,
        ProductBatch.inventory_item_id == InventoryItem.id).where(
        ProductBatch.product_id == product.id, InventoryItem.household_id == item.household_id)).all()
    # Stable tie order; original inventory names are never overwritten.
    shortest = shortest_member([*members, item])
    product.name = checked_product_name(shortest.name)
    db.add(ProductBatch(inventory_item_id=item.id, product_id=product.id,
        source='confirmed_inventory_grouping', actor_user_id=actor_user_id))
    db.flush()
    return product
