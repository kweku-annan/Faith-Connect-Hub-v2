from pydantic import BaseModel, model_validator
from uuid import UUID
from datetime import datetime
from typing import Optional
from app.models.attendance import AttendanceStatus
from app.models.meeting import MeetingType


# ---------------------------------------------------------------------------
# Single attendance record — used inside bulk submit
# ---------------------------------------------------------------------------

class AttendanceEntry(BaseModel):
    """
    Represents one attendee's record within a bulk submission.
    Exactly one of member_id or visitor_id must be set.
    """
    member_id: Optional[UUID] = None
    visitor_id: Optional[UUID] = None
    status: AttendanceStatus
    note: Optional[str] = None

    @model_validator(mode="after")
    def must_have_exactly_one_attendee(self) -> "AttendanceEntry":
        has_member = self.member_id is not None
        has_visitor = self.visitor_id is not None
        if has_member == has_visitor:   # both set or neither set
            raise ValueError(
                "Each entry must have exactly one of member_id or visitor_id, not both or neither"
            )
        return self


# ---------------------------------------------------------------------------
# Bulk submit — the primary way attendance is marked
# ---------------------------------------------------------------------------

class AttendanceBulkSubmit(BaseModel):
    """
    Submit attendance for an entire session at once.
    This is the primary attendance-marking flow — a leader selects a session
    and submits the full list of attendees in one request.

    Existing records for this session are overwritten (upsert behaviour).
    """
    session_id: UUID
    entries: list[AttendanceEntry]

    @model_validator(mode="after")
    def entries_must_not_be_empty(self) -> "AttendanceBulkSubmit":
        if not self.entries:
            raise ValueError("At least one attendance entry must be provided")
        return self

    @model_validator(mode="after")
    def no_duplicate_entries(self) -> "AttendanceBulkSubmit":
        member_ids = [e.member_id for e in self.entries if e.member_id]
        visitor_ids = [e.visitor_id for e in self.entries if e.visitor_id]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("Duplicate member entries in the same submission")
        if len(visitor_ids) != len(set(visitor_ids)):
            raise ValueError("Duplicate visitor entries in the same submission")
        return self


# ---------------------------------------------------------------------------
# Single record update — for correcting one entry after bulk submit
# ---------------------------------------------------------------------------

class AttendanceRecordUpdate(BaseModel):
    status: AttendanceStatus
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class MemberAttendanceSummary(BaseModel):
    """Member info embedded in attendance responses."""
    id: UUID
    first_name: str
    last_name: str

    model_config = {"from_attributes": True}


class VisitorAttendanceSummary(BaseModel):
    """Visitor info embedded in attendance responses."""
    id: UUID
    first_name: str
    last_name: str

    model_config = {"from_attributes": True}


class AttendanceRecordResponse(BaseModel):
    """A single attendance record — returned in session attendance list."""
    id: UUID
    session_id: UUID
    member: Optional[MemberAttendanceSummary] = None
    visitor: Optional[VisitorAttendanceSummary] = None
    status: AttendanceStatus
    note: Optional[str]
    marked_at: datetime

    model_config = {"from_attributes": True}


class SessionAttendanceResponse(BaseModel):
    """
    Full attendance sheet for a session —
    returned after bulk submit or when viewing a session's attendance.
    """
    session_id: UUID
    meeting_type: MeetingType
    meeting_date: str
    group_id: Optional[UUID]
    group_name: Optional[str]
    total_records: int
    present_count: int
    absent_count: int
    excused_count: int
    late_count: int
    records: list[AttendanceRecordResponse]


class MemberAttendanceHistoryResponse(BaseModel):
    """
    Attendance history for a single member —
    returned when viewing a member's attendance across sessions.
    """
    member_id: UUID
    full_name: str
    total_sessions: int
    present_count: int
    attendance_rate: float          # percentage 0.0 - 100.0
    records: list[AttendanceRecordResponse]