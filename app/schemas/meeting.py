from pydantic import BaseModel, field_validator, model_validator
from uuid import UUID
from datetime import date, datetime, time, timezone
from typing import Optional
from app.models.meeting import MeetingType


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class MeetingSessionBase(BaseModel):
    meeting_type: MeetingType
    meeting_date: date
    meeting_time: time
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

class MeetingSessionCreate(MeetingSessionBase):
    group_id: Optional[UUID] = None

    @model_validator(mode="after")
    def validate_group_id_against_type(self) -> "MeetingSessionCreate":
        """
        Fellowship meetings must have a group_id.
        Sunday services must NOT have a group_id (they are church-wide).
        """
        if self.meeting_type == MeetingType.fellowship_meeting and not self.group_id:
            raise ValueError("Fellowship meetings must be linked to a group")
        if self.meeting_type == MeetingType.general and self.group_id:
            raise ValueError(
                "Sunday service sessions are church-wide and must not be linked to a group"
            )
        return self

    @model_validator(mode="after")
    def meeting_datetime_must_not_be_in_past(self) -> "MeetingSessionCreate":
        meeting_dt = datetime.combine(self.meeting_date, self.meeting_time)
        if meeting_dt < datetime.now(timezone.utc):
            raise ValueError("Meeting date and time cannot be in the past")
        return self


# ---------------------------------------------------------------------------
# Update — limited fields only
# ---------------------------------------------------------------------------

class MeetingSessionUpdate(BaseModel):
    notes: Optional[str] = None
    meeting_date: date
    meeting_time: time

    @model_validator(mode="after")
    def meeting_datetime_must_not_be_in_past(self) -> "MeetingSessionUpdate":
        if self.meeting_date and self.meeting_time:
            meeting_dt = datetime.combine(self.meeting_date, self.meeting_time)
            if meeting_dt < datetime.now(timezone.utc):
                raise ValueError("Meeting date and time cannot be in the past")
        return self


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class MeetingSessionSummary(BaseModel):
    """Lightweight session info — embedded in attendance responses."""
    id: UUID
    meeting_type: MeetingType
    meeting_date: date
    group_id: Optional[UUID]

    model_config = {"from_attributes": True}


class MeetingSessionResponse(BaseModel):
    id: UUID
    meeting_type: MeetingType
    meeting_date: date
    meeting_time: time
    group_id: Optional[UUID]
    group_name: Optional[str] = None     # resolved from group relationship
    notes: Optional[str]
    attendance_count: int = 0            # computed in service
    created_at: datetime

    model_config = {"from_attributes": True}