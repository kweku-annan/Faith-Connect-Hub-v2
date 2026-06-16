from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional
from app.schemas.member import MemberSummary


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class GroupBase(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Group name must not be blank")
        return v.strip().title()


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------

class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Group name must not be blank")
        return v.strip().title() if v else v


# ---------------------------------------------------------------------------
# Leader assignment
# ---------------------------------------------------------------------------

class AssignLeaderRequest(BaseModel):
    user_id: UUID
    is_primary: bool = False


class RemoveLeaderRequest(BaseModel):
    user_id: UUID


# ---------------------------------------------------------------------------
# Member assignment
# ---------------------------------------------------------------------------

class AssignMemberRequest(BaseModel):
    member_id: UUID


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class LeaderSummary(BaseModel):
    """Lightweight leader info embedded in group responses."""
    user_id: UUID
    email: str
    full_name: str
    is_primary: bool

    model_config = {"from_attributes": True}


class GroupResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    is_active: bool
    member_count: int = 0        # computed field — populated in service
    leaders: list[LeaderSummary] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GroupDetailResponse(GroupResponse):
    """Full group response including member list — used for single group view."""
    members: list[MemberSummary] = []


class GroupSummary(BaseModel):
    """Minimal group info — used when embedding in other responses."""
    id: UUID
    name: str
    is_active: bool

    model_config = {"from_attributes": True}