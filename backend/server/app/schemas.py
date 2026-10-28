"""Strict API request/response models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.security import normalize_phone


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str
    password: str = Field(min_length=8, max_length=16)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def password_format(cls, password: str) -> str:
        import re
        if (not re.fullmatch(r"[A-Za-z0-9]{8,16}", password)
                or not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password)):
            raise ValueError("Password must be 8-16 ASCII letters and digits, including both")
        return password

    @field_validator("phone")
    @classmethod
    def phone_format(cls, phone: str) -> str:
        return normalize_phone(phone)

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("display_name cannot be blank")
        return name.strip()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str
    password: str = Field(max_length=128)

    @field_validator("phone")
    @classmethod
    def phone_format(cls, phone: str) -> str:
        return normalize_phone(phone)


class UserResponse(BaseModel):
    id: UUID
    phone: str | None
    phone_verified: bool
    display_name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 43200


class HouseholdCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def valid_name(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("Household name cannot be blank")
        return name.strip()


class HouseholdResponse(BaseModel):
    id: UUID
    name: str
    my_role: str
    created_at: datetime


class MemberResponse(BaseModel):
    user_id: UUID
    display_name: str
    role: str
    joined_at: datetime


class InvitationResponse(BaseModel):
    invite_code: str
    expires_at: datetime
    note: str = "Share this code privately. It is shown only once."


class JoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invite_code: str = Field(min_length=20, max_length=128)


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    display_name: str = Field(min_length=1, max_length=100)
