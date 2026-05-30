from pydantic import BaseModel, EmailStr, field_validator, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional
from app.models.user import RoleName


# -----------------------------------------------------------------------
# Login
# -----------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# -----------------------------------------------------------------------
# Invite
# -----------------------------------------------------------------------
class InviteRequest(BaseModel):
    """
    Sent by super_admin or admin to invite a new leader/paster.
    The invitee must already exist as a member in the members table
    """
    email: EmailStr
    member_id: UUID
    roles: list[RoleName]

    @field_validator("roles")
    @classmethod
    def roles_must_not_be_empty(cls, v: list[RoleName]) -> list[RoleName]:
        if not v:
            raise ValueError("At least one role must be assigned")
        return v

    @field_validator("roles")
    @classmethod
    def super_admin_cannot_be_invited(cls, v: list[RoleName]) -> list[RoleName]:
        """Validate how this works in prod"""
        if RoleName.super_admin in v:
            raise ValueError("Super admin role cannot be assigned via invite")
        return v


# --------------------------------------------------------------------
# Registration (completing an invite)
# --------------------------------------------------------------------

class RegisterRequest(BaseModel):
    """
    Submitted by the invitee when they click on their invite link.
    The invite_token come from the link; they choose their password here.
    """
    invite_token: str
    password: str
    confirm_password: str

    @model_validator(mode="after")
    def passwords_must_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must have at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must have at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must have at least one number")
        return v

# ----------------------------------------------------------------------------
# Role schemas
# ----------------------------------------------------------------------------

class UserRoleResponse(BaseModel):
    id: UUID
    role: RoleName
    assigned_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# User responses
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    """Returned after login, registration, or GET /auth/me"""
    id: UUID
    member_id: UUID
    email: EmailStr
    is_active: bool
    roles: list[UserRoleResponse]
    last_login: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class UserSummary(BaseModel):
    """Lightweight user info - used when embedding user in other responses."""
    id: UUID
    email: EmailStr
    roles: list[RoleName]

    model_config = {"from_attributes": True}


# ----------------------------------------------------------------------
# Admin: update a user
# ----------------------------------------------------------------------

class UserUpdateRequest(BaseModel):
    """super_admin or admin can update a user's active status or roles"""
    is_active: Optional[bool] = None
    roles: Optional[list[RoleName]] = None





