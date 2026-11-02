"""Request and response schemas. Input is validated at the boundary; output never includes secrets."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security import MAX_PASSWORD_LENGTH

RoleName = Literal["owner", "admin", "member", "viewer"]


def _normalize_email(value: str) -> str:
    return value.strip().lower()


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return _normalize_email(value)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return _normalize_email(value)


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str


class AuthOut(BaseModel):
    user: UserOut
    csrf_token: str


class OrgCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=200)


class OrgUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=200)


class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    plan_code: str
    role: RoleName


class MemberOut(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: RoleName
    joined_at: datetime


class MemberRoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: RoleName


class InvitationCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: RoleName = "member"

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return _normalize_email(value)


class InvitationOut(BaseModel):
    id: str
    email: str
    role: RoleName
    created_at: datetime
    expires_at: datetime


class InvitationCreatedOut(InvitationOut):
    # Returned exactly once, at creation. Only a hash is stored server-side.
    token: str


class InvitationAcceptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=200)


class AuditEventOut(BaseModel):
    id: int
    action: str
    outcome: str
    actor_user_id: str | None
    target_type: str | None
    target_id: str | None
    metadata: dict
    trace_id: str | None
    created_at: datetime
