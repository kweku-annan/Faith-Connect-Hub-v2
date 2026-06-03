from pydantic import BaseModel, EmailStr, field_validator
from uuid import UUID
from datetime import date, datetime
from typing import Optional, Any, Self
from app.models.member import Gender, MemberStatus
from app.utils.validators import validate_ghana_phone


# ------------------------------------------------------------
# Base
# ------------------------------------------------------------

class MemberBase(BaseModel):
    first_name: str
    last_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    gender: Gender
    date_of_birth: Optional[date] = None
    address: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate(cls, v: str | None) -> str | None:
        return validate_ghana_phone(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def names_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("First name and last name cannot be blank")
        return v.strip().title()


# ------------------------------------------------------------
# Create
# ------------------------------------------------------------

class MemberCreate(MemberBase):
    date_joined: date = None

    @field_validator("date_joined", mode="before")
    @classmethod
    def default_date_joined(cls, v):
        return v or date.today()


# ------------------------------------------------------------
# Update - all fields optional
# ------------------------------------------------------------

class MemberUpdate(MemberBase):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    gender: Optional[Gender] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    status: Optional[MemberStatus] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        return validate_ghana_phone(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def names_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("First name and last name cannot be blank")
        return v.strip().title() if v else v


# ------------------------------------------------------------
# Transfer - move a member to a different group
# ------------------------------------------------------------

class MemberTransfer(BaseModel):
    target_group_id: UUID


# ------------------------------------------------------------
# Response
# ------------------------------------------------------------

class GroupSummary(BaseModel):
    """Lightweight group info embedded in member responses."""
    id: UUID
    name: str

    model_config = {"from_attribute": True}


class MemberResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    email: Optional[EmailStr]
    phone: Optional[str]
    gender: Gender
    date_of_birth: Optional[date]
    address: Optional[str]
    date_joined: date
    status: MemberStatus
    group: Optional[GroupSummary] = None  # resolved from group_membership
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemberSummary(BaseModel):
    """Lightweight member info - used when embedding member in other responses."""
    id: UUID
    first_name: str
    last_name: str
    phone: Optional[str]
    status: MemberStatus

    model_config = {"from_attributes": True}

