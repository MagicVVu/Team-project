"""Authenticated household create/list/members and single-use invite/join."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.models import Household, HouseholdInvitation, HouseholdMember, ShoppingList, User
from app.schemas import (
    HouseholdCreateRequest, HouseholdResponse, InvitationResponse, JoinRequest, MemberResponse,
)
from app.security import digest_token, is_expired, make_token, now_utc

router = APIRouter(prefix="/api/v1/households", tags=["Households"])


@router.patch("/{household_id}", response_model=HouseholdResponse)
def update_household(household_id: UUID, payload: HouseholdCreateRequest,
                     identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    member = membership_or_404(db, household_id, identity.user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owners and admins may rename the household")
    household = db.get(Household, household_id)
    household.name = payload.name
    db.commit()
    return HouseholdResponse(id=household.id, name=household.name, my_role=member.role, created_at=household.created_at)


def membership_or_404(db: Session, household_id: UUID, user_id: UUID) -> HouseholdMember:
    member = db.get(HouseholdMember, (household_id, user_id))
    if member is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return member


@router.post("", response_model=HouseholdResponse, status_code=status.HTTP_201_CREATED)
def create_household(
    payload: HouseholdCreateRequest,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> HouseholdResponse:
    household = Household(name=payload.name, created_by_user_id=identity.user.id)
    db.add(household)
    db.flush()
    db.add(HouseholdMember(household_id=household.id, user_id=identity.user.id, role="owner"))
    db.add(ShoppingList(
        household_id=household.id, name="家庭共享购物清单", created_by_user_id=identity.user.id
    ))
    db.commit()
    db.refresh(household)
    return HouseholdResponse(id=household.id, name=household.name, my_role="owner", created_at=household.created_at)


@router.get("", response_model=list[HouseholdResponse])
def list_households(identity: Identity = Depends(get_identity), db: Session = Depends(get_db)) -> list[HouseholdResponse]:
    data = db.execute(
        select(Household, HouseholdMember.role)
        .join(HouseholdMember, HouseholdMember.household_id == Household.id)
        .where(HouseholdMember.user_id == identity.user.id)
        .order_by(Household.created_at.asc())
    ).all()
    return [HouseholdResponse(
        id=household.id, name=household.name, my_role=role, created_at=household.created_at
    ) for household, role in data]


@router.get("/{household_id}/members", response_model=list[MemberResponse])
def list_members(
    household_id: UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> list[MemberResponse]:
    membership_or_404(db, household_id, identity.user.id)
    data = db.execute(
        select(HouseholdMember, User)
        .join(User, User.id == HouseholdMember.user_id)
        .where(HouseholdMember.household_id == household_id)
        .order_by(HouseholdMember.joined_at.asc())
    ).all()
    return [MemberResponse(
        user_id=user.id, display_name=user.display_name,
        role=member.role, joined_at=member.joined_at,
    ) for member, user in data]


@router.post("/{household_id}/invitations", response_model=InvitationResponse, status_code=201)
def issue_invitation(
    household_id: UUID,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> InvitationResponse:
    member = membership_or_404(db, household_id, identity.user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owners and admins may invite")
    secret, secret_hash = make_token()
    expires = now_utc() + timedelta(minutes=30)
    db.add(HouseholdInvitation(
        household_id=household_id, created_by_user_id=identity.user.id,
        code_hash=secret_hash, expires_at=expires,
    ))
    db.commit()
    return InvitationResponse(invite_code=secret, expires_at=expires)


@router.post("/join", response_model=HouseholdResponse)
def join_household(
    payload: JoinRequest,
    identity: Identity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> HouseholdResponse:
    # Database row locking ensures two simultaneous join attempts cannot spend one code.
    invitation = db.scalar(
        select(HouseholdInvitation)
        .where(HouseholdInvitation.code_hash == digest_token(payload.invite_code))
        .with_for_update()
    )
    if invitation is None or invitation.used_at is not None or is_expired(invitation.expires_at):
        raise HTTPException(status_code=400, detail="Invite code is invalid, used, or expired")
    if db.get(HouseholdMember, (invitation.household_id, identity.user.id)) is not None:
        raise HTTPException(status_code=409, detail="Already a household member")
    household = db.get(Household, invitation.household_id)
    if household is None:
        raise HTTPException(status_code=400, detail="Household no longer exists")
    db.add(HouseholdMember(household_id=household.id, user_id=identity.user.id, role="member"))
    invitation.used_by_user_id = identity.user.id
    invitation.used_at = now_utc()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Already a household member") from None
    return HouseholdResponse(id=household.id, name=household.name, my_role="member", created_at=household.created_at)
