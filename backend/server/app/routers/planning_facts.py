"""Authenticated observations consumed by the existing AI read contract."""
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.planning_fact_schemas import PlanningFactsPatch, PlanningFactsResponse
from app.services import planning_facts as service

router = APIRouter(prefix="/api/v1/households/{household_id}/inventory-items/{item_id}", tags=["Planning facts"])


@router.get("/planning-facts", response_model=PlanningFactsResponse)
def read_facts(household_id: UUID, item_id: UUID, response: Response,
               identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return service.read(db, identity, household_id, item_id)


@router.patch("/planning-facts", response_model=PlanningFactsResponse)
def update_facts(household_id: UUID, item_id: UUID, body: PlanningFactsPatch, response: Response,
                 identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    try:
        value = service.patch(db, identity, household_id, item_id, body)
        db.commit()
        return value
    except IntegrityError:
        db.rollback()
        # Different items can race for a global operation ID. Re-enter all scope
        # and fingerprint checks; never return another user's receipt.
        try:
            value = service.patch(db, identity, household_id, item_id, body)
            db.commit()
            return value
        except IntegrityError:
            db.rollback()
            service.fail("PLANNING_FACTS_CONFLICT")
    except Exception:
        db.rollback()
        raise
