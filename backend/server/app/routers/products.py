from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.dependencies import Identity, get_db, get_identity
from app.models import InventoryItem
from app.product_models import Product, ProductBatch
from app.product_schemas import ProductCreate, ProductLink
from app.routers.households import membership_or_404
from app.services import ledger, products
from app.shopping_schemas import StockResponse
from app.execution_models import BusinessEvent

router = APIRouter(prefix='/api/v1/households/{household_id}', tags=['Product identity and inventory ledger'])


@router.get('/inventory-product-matches')
def inventory_product_matches(household_id: UUID, response: Response,
                              name: str = Query(min_length=1, max_length=200, pattern=r'\S'),
                              limit: int = Query(200, ge=1, le=200), offset: int = Query(0, ge=0),
                              identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    from app.services.product_grouping import candidates
    response.headers['Cache-Control'] = 'no-store'
    return candidates(db, household_id, name, limit, offset)


@router.get('/inventory-products')
def inventory_products(household_id: UUID, response: Response,
                       limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                       identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    """Product identities and ALL linked batches, never inferred from equal names."""
    membership_or_404(db, household_id, identity.user.id)
    total = db.scalar(select(func.count()).select_from(Product).where(Product.household_id == household_id))
    rows = db.scalars(select(Product).where(Product.household_id == household_id)
                      .order_by(Product.name, Product.id).limit(limit).offset(offset)).all()
    batches = db.execute(select(ProductBatch.product_id, InventoryItem).join(
        InventoryItem, InventoryItem.id == ProductBatch.inventory_item_id).where(
        ProductBatch.product_id.in_([p.id for p in rows]), InventoryItem.household_id == household_id)
        .order_by(InventoryItem.created_at, InventoryItem.id)).all() if rows else []
    grouped = {p.id: [] for p in rows}
    for product_id, batch in batches:
        grouped[product_id].append(StockResponse.model_validate(batch).model_dump(mode='json'))
    response.headers['Cache-Control'] = 'no-store'
    return {'protocol_version': 'inventory-products-1', 'items': [
        {**products.value(p), 'count': sum(row['status'] == 'ACTIVE' for row in grouped[p.id]), 'inventory_items': grouped[p.id]} for p in rows],
        'total': total, 'limit': limit, 'offset': offset}


@router.post('/products', status_code=201)
@ledger.retry_conflicts
def create_product(household_id: UUID, body: ProductCreate, identity: Identity = Depends(get_identity),
                   db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    fingerprint = ledger.digest(['product_create', body.model_dump(mode='json')])
    prior = ledger.replay(db, body.id, household_id, identity.user.id, fingerprint)
    if prior is not None:
        return prior
    if db.get(Product, body.id) is not None:
        raise HTTPException(409, {'code': 'PRODUCT_ID_CONFLICT'})
    row = Product(id=body.id, household_id=household_id, actor_user_id=identity.user.id,
        tags_json=body.tags, **body.model_dump(exclude={'id', 'tags'}))
    db.add(row)
    db.flush()
    result = products.value(row)
    ledger.save(db, body.id, household_id, identity.user.id, fingerprint, result)
    db.commit()
    return result


@router.put('/inventory-items/{item_id}/product')
@ledger.retry_conflicts
def link_product(household_id: UUID, item_id: UUID, body: ProductLink, identity: Identity = Depends(get_identity),
                 db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    item = db.scalar(select(InventoryItem).where(InventoryItem.id == item_id,
        InventoryItem.household_id == household_id).with_for_update().execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, {'code': 'INVENTORY_NOT_FOUND'})
    fingerprint = ledger.digest(['product_link', str(item_id), body.model_dump(mode='json')])
    prior = ledger.replay(db, body.operation_id, household_id, identity.user.id, fingerprint)
    if prior is not None:
        return prior
    if item.version != body.expected_inventory_version:
        raise HTTPException(409, {'code': 'INVENTORY_VERSION_CONFLICT'})
    if body.product_id:
        product = db.scalar(select(Product).where(Product.id == body.product_id,
            Product.household_id == household_id).with_for_update())
        if product is None:
            raise HTTPException(404, {'code': 'PRODUCT_NOT_FOUND'})
    old = db.get(ProductBatch, item_id)
    before = StockResponse.model_validate(item).model_dump(mode='json')
    before['product_id'] = str(old.product_id) if old else None
    if old:
        db.delete(old)
        db.flush()
    if body.product_id:
        db.add(ProductBatch(inventory_item_id=item_id, product_id=body.product_id,
            actor_user_id=identity.user.id, source=body.source))
    item.version += 1
    db.flush()
    result = {'batch_id': str(item.id), 'product_id': str(body.product_id) if body.product_id else None,
              'inventory_version': item.version, 'identity_status': 'household_attested' if body.product_id else 'unknown'}
    ledger.save(db, body.operation_id, household_id, identity.user.id, fingerprint, result)
    event = ledger.append(db, item, identity.user.id, 'ProductLinked', before, request_id=body.operation_id)
    event.after_json = {**event.after_json, 'product_id': result['product_id'], 'mapping_source': body.source}
    db.commit()
    return result


@router.get('/inventory-events')
def events(household_id: UUID, response: Response, batch_id: UUID | None = None,
           limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
           identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    query = select(BusinessEvent).where(BusinessEvent.household_id == household_id)
    if batch_id:
        query = query.where(BusinessEvent.inventory_item_id == batch_id)
    rows = db.scalars(query.order_by(BusinessEvent.occurred_at, BusinessEvent.id).limit(limit+1).offset(offset)).all()
    response.headers['Cache-Control'] = 'no-store'
    return {'protocol_version': 'inventory-ledger-1', 'coverage': 'durable_events_since_p9_plus_existing_draft_events',
        'historical_crud_backfilled': False, 'next_offset': offset+limit if len(rows)>limit else None,
        'events': [{'event_id': str(e.id), 'inventory_batch_id': str(e.inventory_item_id) if e.inventory_item_id else None,
            'product_id': str(e.product_id) if e.product_id else None, 'event_type': e.event_type,
            'quantity': str(e.quantity) if e.quantity is not None else None, 'quantity_delta': ledger.quantity_delta(e),
            'unit': e.unit, 'occurred_at': e.occurred_at, 'created_at': e.created_at,
            'actor_user_id': str(e.actor_user_id), 'request_id': str(e.request_id or e.operation_id),
            'source': 'draft_execution' if e.operation_id else 'authenticated_business_api',
            'related_event_id': str(e.related_event_id) if e.related_event_id else None,
            'version': e.after_json.get('version'), 'before': e.before_json, 'after': e.after_json}
            for e in rows[:limit]]}
