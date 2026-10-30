"""Automatic household product classification; original object names remain intact."""
import unicodedata
from uuid import uuid5

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Household, InventoryItem
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
        .where(InventoryItem.household_id == household_id, InventoryItem.status == 'ACTIVE').order_by(InventoryItem.id)).all()
    matches = []
    for item, product in rows:
        match = name_match(name, item.name) or (name_match(name, product.name) if product else None)
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
    if not name.strip() or len(name) > 200:
        raise HTTPException(422, {'code': 'PRODUCT_NAME_TOO_LONG',
                                  'message': '商品名称需为 1 至 200 字；请明确核对名称，不自动截断。'})
    return name


def shortest_member(members):
    return min(members, key=lambda row: (len(row.name), normalized_name(row.name), row.name, str(row.id)))


def singleton(db, item, actor_user_id, source='inventory_singleton', representative=None, product_id=None):
    """Call after inserting a batch; caller owns the transaction and its receipt."""
    prior = db.get(ProductBatch, item.id)
    if prior is not None:
        return db.get(Product, prior.product_id)
    representative = representative or item
    identity = product_id or uuid5(item.id, 'inventory-product')
    if product_id is None and db.get(Product, identity) is not None:
        # A renamed singleton may leave its former product available to other
        # objects/history. Give the new identity its own stable identifier.
        identity = uuid5(item.id, 'inventory-product:' + normalized_name(representative.name))
    product = Product(id=identity, household_id=item.household_id,
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


def lock_household(db, household_id):
    # Serialize all product classification/intake in a household, including the
    # empty catalogue case where no existing product row could be locked.
    db.scalar(select(Household).where(Household.id == household_id).with_for_update())


def classify_new(db, item, choice, actor_user_id):
    """Exact first, then a shared contiguous pair; never cross households.

    Explicit user choices take precedence; absent choices retain automatic
    classification for AI drafts and older queued requests.
    """
    lock_household(db, item.household_id)
    prior = db.get(ProductBatch, item.id)
    if prior is not None:
        return db.get(Product, prior.product_id)
    if choice is not None:
        if choice.mode == 'separate':
            return singleton(db, item, actor_user_id, 'user_separate_grouping')
        candidate = db.scalar(select(InventoryItem).where(
            InventoryItem.id == choice.candidate_inventory_item_id,
            InventoryItem.household_id == item.household_id).with_for_update())
        if candidate is None or candidate.id == item.id:
            raise HTTPException(404, {'code': 'GROUPING_CANDIDATE_NOT_FOUND'})
        if candidate.version != choice.expected_inventory_version:
            raise HTTPException(409, {'code': 'GROUPING_CANDIDATE_CHANGED'})
        link = db.get(ProductBatch, candidate.id)
        product = db.get(Product, link.product_id) if link else None
        if not (name_match(item.name, candidate.name) or (product and name_match(item.name, product.name))):
            raise HTTPException(409, {'code': 'GROUPING_NAME_NO_LONGER_MATCHES'})
        if product is not None:
            if product.household_id != item.household_id:
                raise HTTPException(404, {'code': 'GROUPING_PRODUCT_NOT_FOUND'})
            if product.version != choice.expected_product_version:
                raise HTTPException(409, {'code': 'GROUPING_PRODUCT_CHANGED'})
            product.version += 1
        else:
            if choice.expected_product_version is not None:
                raise HTTPException(409, {'code': 'GROUPING_PRODUCT_CHANGED'})
            product = singleton(db, candidate, actor_user_id, 'user_confirmed_grouping')
            candidate.version += 1
        db.add(ProductBatch(inventory_item_id=item.id, product_id=product.id,
            source='user_confirmed_grouping', actor_user_id=actor_user_id))
        db.flush()
        return product
    products = db.scalars(select(Product).where(Product.household_id == item.household_id)).all()
    matching = [(product, name_match(item.name, product.name)) for product in products]
    matching = [(product, match) for product, match in matching if match]
    matching.sort(key=lambda pair: (pair[1]['match_type'] != 'exact', len(pair[0].name),
        normalized_name(pair[0].name), str(pair[0].id)))
    if not matching:
        return singleton(db, item, actor_user_id, 'automatic_name_grouping')
    product = matching[0][0]
    product.version += 1
    db.add(ProductBatch(inventory_item_id=item.id, product_id=product.id,
        source='automatic_name_grouping', actor_user_id=actor_user_id))
    db.flush()
    return product


def reclassify_edited(db, item, actor_user_id):
    """Regroup only the renamed object; keep its former product and peers intact."""
    link = db.get(ProductBatch, item.id)
    previous_product_id = link.product_id if link else None
    if link is not None:
        db.delete(link)
        db.flush()
    product = classify_new(db, item, None, actor_user_id)
    if previous_product_id is not None and previous_product_id != product.id:
        previous = db.get(Product, previous_product_id)
        previous.version += 1
    db.flush()
    return product
