"""Per-request DB session and bearer-token identity."""

from collections.abc import Generator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AuthSession, User
from app.security import digest_token, is_expired

bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


@dataclass(frozen=True)
class Identity:
    user: User
    session_id: UUID


def get_identity(
    auth: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Identity:
    error = HTTPException(status_code=401, detail="Invalid or expired login", headers={"WWW-Authenticate": "Bearer"})
    if auth is None or auth.scheme.lower() != "bearer" or not auth.credentials:
        raise error
    token_hash = digest_token(auth.credentials)
    result = db.execute(
        select(AuthSession, User)
        .join(User, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == token_hash)
    ).one_or_none()
    if result is None:
        raise error
    session, user = result
    if session.revoked_at is not None or is_expired(session.expires_at) or not user.is_active:
        raise error
    return Identity(user=user, session_id=session.id)
