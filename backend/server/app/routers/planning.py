"""Service-only GET reusing the existing planning service and authorization."""
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.planning_schemas import PlanningResponse
from app.routers.ai_inventory import _authorize
from app.services.planning_context import snapshot

router = APIRouter(tags=['Internal AI Planning'])


@router.get('/internal/v1/planning/context', response_model=PlanningResponse)
@router.get('/internal/v1/ai/planning-context', response_model=PlanningResponse, include_in_schema=False)
def planning_context(response: Response, name: str | None = Query(None, min_length=1, max_length=80),
                     item_key: UUID | None = Query(None),
                     household_id: UUID = Depends(_authorize), x_user_id: str = Header(),
                     db: Session = Depends(get_db)):
    if (name is not None and not name.strip()) or (name is not None and item_key is not None):
        raise HTTPException(422, 'Provide at most one nonblank selector')
    # Authorization used only SELECTs. Release its pooled connection before
    # opening the dedicated snapshot; recheck active membership inside it.
    db.rollback()
    result = snapshot(db, UUID(x_user_id), household_id, name.strip() if name else None,
                      str(item_key) if item_key else None, with_provenance=True)
    try:
        value = PlanningResponse.model_validate(result)
    except ValidationError:
        raise HTTPException(409, {'code': 'PLANNING_CONTRACT_INVALID',
            'message': 'Stored facts require reconciliation; no partial snapshot'}) from None
    response.headers['Cache-Control'] = 'no-store'
    return value
