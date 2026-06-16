from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import date, datetime
from typing import Optional
from app.utils.validators import validate_ghana_phone


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class VisitorBase(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    location: Optional[str] = None
    invited_by_member_id: Optional[UUID] = None
    notes: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        return validate_ghana_phone(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def names_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name fields must not be blank")
        return v.strip().title()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class VisitorCreate(VisitorBase):
    visit_date: date = None

    @field_validator("visit_date", mode="before")
    @classmethod
    def default_visit_date(cls, v):
        return v or date.today()


# ---------------------------------------------------------------------------
# Update — all fields optional
# ---------------------------------------------------------------------------

class VisitorUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    invited_by_member_id: Optional[UUID] = None
    notes: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        return validate_ghana_phone(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def names_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Name fields must not be blank")
        return v.strip().title() if v else v


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class InvitedByMemberSummary(BaseModel):
    """Lightweight member info embedded in visitor responses."""
    id: UUID
    first_name: str
    last_name: str
    phone: Optional[str]

    model_config = {"from_attributes": True}


class VisitorResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    phone: Optional[str]
    location: Optional[str]
    visit_date: date
    notes: Optional[str]
    invited_by: Optional[InvitedByMemberSummary] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VisitorSummary(BaseModel):
    """Lightweight visitor info — used when embedding in attendance responses."""
    id: UUID
    first_name: str
    last_name: str
    phone: Optional[str]

    model_config = {"from_attributes": True}