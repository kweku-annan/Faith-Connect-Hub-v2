from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from app.db.session import get_db
from app.schemas.attendance import (
    AttendanceBulkSubmit,
    AttendanceRecordUpdate,
    AttendanceRecordResponse,
    SessionAttendanceResponse,
    MemberAttendanceHistoryResponse,
)
from app.services import attendance_service
from app.api.v1.dependencies import get_current_user
from app.models.user import User
from app.models.meeting import MeetingType

router = APIRouter()


@router.post(
    "/",
    response_model=SessionAttendanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit attendance for a session",
)
async def bulk_submit_attendance(
    data: AttendanceBulkSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark attendance for an entire session in one request.

    This is the primary attendance-marking flow. Provide a `session_id`
    and a list of entries — each entry must have exactly one of
    `member_id` or `visitor_id`, plus a `status`.

    Submitting twice for the same session **updates** existing records
    rather than creating duplicates (upsert behaviour). This allows
    leaders to correct mistakes without admin intervention.

    Returns the full attendance sheet with summary counts.

    **Leader scope:** Leaders can only submit attendance for their own
    group's sessions and can only include their group's members.

    **Requires:** any authenticated role.
    """
    return await attendance_service.bulk_submit_attendance(db, data, current_user)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionAttendanceResponse,
    summary="Get the attendance sheet for a session",
)
async def get_session_attendance(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the full attendance sheet for a session, including
    summary counts (present, absent, excused, late).

    - **Leaders** can view their own group's sessions and all Sunday services.
    - **Pastors / Admins / Super Admins** can view any session.

    **Requires:** any authenticated role.
    """
    return await attendance_service.get_session_attendance(
        db, session_id, current_user
    )


@router.patch(
    "/records/{record_id}",
    response_model=AttendanceRecordResponse,
    summary="Correct a single attendance record",
)
async def update_attendance_record(
    record_id: UUID,
    data: AttendanceRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update the status or note on a single attendance record.
    Use this to correct one entry without resubmitting the entire session.

    - **Leaders** can only update records for members in their own group.
    - **Pastors / Admins / Super Admins** can update any record.

    **Requires:** any authenticated role.
    """
    return await attendance_service.update_attendance_record(
        db, record_id, data, current_user
    )


@router.get(
    "/members/{member_id}",
    response_model=MemberAttendanceHistoryResponse,
    summary="Get a member's attendance history",
)
async def get_member_attendance_history(
    member_id: UUID,
    meeting_type: Optional[MeetingType] = Query(
        None, description="Filter by meeting type"
    ),
    from_date: Optional[str] = Query(
        None, description="Start date (YYYY-MM-DD)"
    ),
    to_date: Optional[str] = Query(
        None, description="End date (YYYY-MM-DD)"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a member's full attendance history with an attendance rate.

    Filters:
    - `meeting_type` — restrict to Sunday services or fellowship meetings only.
    - `from_date` / `to_date` — restrict to a date range.

    The `attendance_rate` is computed across **all** matching sessions
    (not just the current page) so it reflects the full picture.

    - **Leaders** can only view members in their own group.
    - **Pastors / Admins / Super Admins** can view any member.

    **Requires:** any authenticated role.
    """
    from app.utils.pagination import PaginationParams
    params = PaginationParams(page=page, page_size=page_size)

    return await attendance_service.get_member_attendance_history(
        db,
        member_id=member_id,
        requesting_user=current_user,
        meeting_type=meeting_type,
        from_date=from_date,
        to_date=to_date,
        offset=params.offset,
        limit=params.page_size,
    )