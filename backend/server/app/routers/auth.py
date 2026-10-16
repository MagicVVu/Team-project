"""Development-only, UNVERIFIED phone-password authentication API.

Not safe for public sign-ups until phone proof-of-possession and abuse protections
are added. Never infer ownership of a phone from these account records.
"""

import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.models import AuthSession, User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.security import hash_password, make_token, now_utc, token_expiry, verify_password

router = APIRouter(prefix="/api/v1", tags=["Authentication"])


def user_data(user: User) -> UserResponse:
    return UserResponse(
        id=user.id, phone=user.phone,
        phone_verified=user.phone_verified_at is not None,
        display_name=user.display_name, created_at=user.created_at,
    )


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserResponse:
    if os.getenv("AUTH_ALLOW_UNVERIFIED_SIGNUP", "false").strip().lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=403, detail="Unverified phone registration is disabled")
    # The number has NOT been SMS-verified. Do not give it account recovery privileges.
    if db.scalar(select(User.id).where(User.phone == payload.phone)) is not None:
        raise HTTPException(status_code=409, detail="Phone already registered")
    user = User(
        phone=payload.phone,
        email=None,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        phone_verified_at=None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Phone already registered") from None
    db.refresh(user)
    return user_data(user)


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.phone == payload.phone, User.is_active.is_(True)))
    if user is None or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="Invalid phone or password")
    token, token_hash = make_token()
    db.add(AuthSession(user_id=user.id, token_hash=token_hash, expires_at=token_expiry()))
    db.commit()
    return TokenResponse(access_token=token)


@router.get("/users/me", response_model=UserResponse)
def current_user(identity: Identity = Depends(get_identity)) -> UserResponse:
    return user_data(identity.user)


@router.post("/auth/logout")
def logout(identity: Identity = Depends(get_identity), db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(
        update(AuthSession)
        .where(AuthSession.id == identity.session_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now_utc())
    )
    db.commit()
    return {"status": "logged_out"}
