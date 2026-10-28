"""Authenticated household create/list/members and single-use invite/join."""

from datetime import timedelta
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.models import (
    AIDraft, AITask, BusinessEvent, DraftDecision, DraftOperation, Household,
    HouseholdInvitation, HouseholdMember, ShoppingList, User,
)
from app.schemas import (
    HouseholdCreateRequest, HouseholdResponse, InvitationResponse, JoinRequest, MemberResponse,
)
from app.security import digest_token, is_expired, make_token, now_utc

router = APIRouter(prefix="/api/v1/households", tags=["Households"])


@router.patch("/{household_id}", response_model=HouseholdResponse)
def update_household(household_id: UUID, payload: HouseholdCreateRequest,
                     identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    lock_household(db, household_id)
    member = membership_or_404(db, household_id, identity.user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owners and admins may rename the household")
    household = db.get(Household, household_id)
    household.name = payload.name
    db.commit()
    return HouseholdResponse(id=household.id, name=household.name, my_role=member.role, created_at=household.created_at)


def membership_or_404(db: Session, household_id: UUID, user_id: UUID) -> HouseholdMember:
    # Keep authorization valid until this transaction completes, including writes.
    member = db.scalar(select(HouseholdMember).where(
        HouseholdMember.household_id == household_id, HouseholdMember.user_id == user_id,
    ).with_for_update(read=True).execution_options(populate_existing=True))
    if member is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return member


def lock_household(db: Session, household_id: UUID) -> Household:
    # Serialize membership changes without blocking foreign-key KEY SHARE locks.
    household = db.scalar(select(Household).where(Household.id == household_id)
        .with_for_update(key_share=True).execution_options(populate_existing=True))
    if household is None:
        raise HTTPException(404, "Household not found")
    return household


def management_context(db: Session, household_id: UUID, user_id: UUID):
    household = lock_household(db, household_id)
    members = {m.user_id: m for m in db.scalars(select(HouseholdMember).where(
        HouseholdMember.household_id == household_id,
    ).order_by(HouseholdMember.user_id).with_for_update()
        .execution_options(populate_existing=True)).all()}
    actor = members.get(user_id)
    if actor is None:
        raise HTTPException(404, "Household not found")
    return household, actor, members


def revoke_invitations(db: Session, household_id: UUID):
    # A removed/demoted inviter must not retain a working invitation capability.
    db.execute(delete(HouseholdInvitation).where(
        HouseholdInvitation.household_id == household_id,
        HouseholdInvitation.used_at.is_(None),
    ))


class MemberRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "member"]


class OwnershipTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_owner_user_id: UUID


class DissolveHouseholdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_name: str = Field(min_length=1, max_length=100)


@router.post("/{household_id}/leave", status_code=204, response_class=Response)
def leave_household(household_id: UUID, identity: Identity = Depends(get_identity),
                    db: Session = Depends(get_db)):
    _, actor, _ = management_context(db, household_id, identity.user.id)
    if actor.role == "owner":
        raise HTTPException(409, "Transfer ownership or dissolve the household before leaving")
    db.delete(actor)
    revoke_invitations(db, household_id)
    db.commit()
    return Response(status_code=204)


@router.delete("/{household_id}/members/{user_id}", status_code=204, response_class=Response)
def remove_member(household_id: UUID, user_id: UUID,
                  identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    _, actor, members = management_context(db, household_id, identity.user.id)
    if actor.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owners and admins may remove members")
    target = members.get(user_id)
    if target is None:
        raise HTTPException(404, "Member not found")
    if user_id == identity.user.id:
        raise HTTPException(409, "Use the leave endpoint to leave the household")
    if target.role == "owner" or (actor.role == "admin" and target.role != "member"):
        raise HTTPException(403, "Cannot remove this member")
    db.delete(target)
    revoke_invitations(db, household_id)
    db.commit()
    return Response(status_code=204)


@router.patch("/{household_id}/members/{user_id}", response_model=MemberResponse)
def set_member_role(household_id: UUID, user_id: UUID, payload: MemberRoleRequest,
                    identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    _, actor, members = management_context(db, household_id, identity.user.id)
    if actor.role != "owner":
        raise HTTPException(403, "Only the owner may change member roles")
    target = members.get(user_id)
    if target is None:
        raise HTTPException(404, "Member not found")
    if target.role == "owner":
        raise HTTPException(409, "Use the ownership transfer endpoint to change the owner")
    target.role = payload.role
    revoke_invitations(db, household_id)
    user = db.get(User, user_id)
    result = MemberResponse(user_id=user_id, display_name=user.display_name,
                            role=target.role, joined_at=target.joined_at)
    db.commit()
    return result


@router.post("/{household_id}/transfer-ownership", response_model=HouseholdResponse)
def transfer_ownership(household_id: UUID, payload: OwnershipTransferRequest,
                       identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    household, actor, members = management_context(db, household_id, identity.user.id)
    if actor.role != "owner":
        raise HTTPException(403, "Only the owner may transfer ownership")
    target = members.get(payload.new_owner_user_id)
    if target is None:
        raise HTTPException(404, "New owner must already be a household member")
    if target.user_id == actor.user_id:
        raise HTTPException(409, "Already the household owner")
    if not db.get(User, target.user_id).is_active:
        raise HTTPException(409, "New owner account is inactive")
    actor.role = "member"
    target.role = "owner"
    revoke_invitations(db, household_id)
    db.commit()
    return HouseholdResponse(id=household.id, name=household.name, my_role="member", created_at=household.created_at)


@router.delete("/{household_id}", status_code=204, response_class=Response)
def dissolve_household(household_id: UUID, payload: DissolveHouseholdRequest,
                        identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    household = lock_household(db, household_id)
    actor = db.get(HouseholdMember, (household_id, identity.user.id))
    if actor is None:
        raise HTTPException(404, "Household not found")
    if actor.role != "owner":
        raise HTTPException(403, "Only the owner may dissolve the household")
    if payload.confirmation_name != household.name:
        raise HTTPException(409, "Household name confirmation does not match")
    # Match execution's task -> draft -> membership lock order to avoid deadlocks.
    db.scalars(select(AITask).where(AITask.household_id == household_id)
        .order_by(AITask.id).with_for_update()).all()
    db.scalars(select(AIDraft).where(AIDraft.household_id == household_id)
        .order_by(AIDraft.id).with_for_update()).all()
    household, actor, _ = management_context(db, household_id, identity.user.id)
    # Explicitly remove the RESTRICT-linked execution ledger in dependency order;
    # remaining household-owned tables use database ON DELETE CASCADE/SET NULL.
    draft_ids = select(AIDraft.id).where(AIDraft.household_id == household_id)
    operation_ids = select(DraftOperation.id).where(DraftOperation.household_id == household_id)
    db.execute(delete(BusinessEvent).where(BusinessEvent.household_id == household_id))
    db.execute(delete(DraftDecision).where(
        DraftDecision.draft_id.in_(draft_ids) | DraftDecision.operation_id.in_(operation_ids)))
    db.execute(delete(DraftOperation).where(DraftOperation.household_id == household_id))
    # Bulk deletion delegates cascades to the DB instead of ORM relationship nulling.
    db.execute(delete(Household).where(Household.id == household_id))
    db.commit()
    return Response(status_code=204)


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
    lock_household(db, household_id)
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
    # Lock household before invitation, matching all membership mutations.
    household_id = db.scalar(select(HouseholdInvitation.household_id).where(
        HouseholdInvitation.code_hash == digest_token(payload.invite_code)))
    if household_id is None:
        raise HTTPException(400, "Invite code is invalid, used, or expired")
    lock_household(db, household_id)
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
