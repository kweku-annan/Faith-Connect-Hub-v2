import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.models.attendance import AttendanceRecord, AttendanceStatus
from app.models.meeting import MeetingSession, MeetingType
from app.models.group import GroupLeader, GroupMembership
from app.models.member import Member
from app.models.visitor import Visitor
from app.models.user import User, RoleName
from app.schemas.attendance import (
    AttendanceBulkSubmit,
    AttendanceRecordUpdate,
    AttendanceRecordResponse,
    SessionAttendanceResponse,
    MemberAttendanceHistoryResponse,
    MemberAttendanceSummary,
    VisitorAttendanceSummary,
)
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _is_elevated(user: User) -> bool:
    roles = [r.role for r in user.roles]
    return any(r in roles for r in [
        RoleName.super_admin, RoleName.admin, RoleName.pastor
    ])


async def _get_leader_group_id(db: AsyncSession, user: User) -> uuid.UUID | None:
    result = await db.execute(
        select(GroupLeader.group_id).where(
            GroupLeader.user_id == user.id,
            GroupLeader.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _get_session(db: AsyncSession, session_id: uuid.UUID) -> MeetingSession | None:
    result = await db.execute(
        select(MeetingSession)
        .options(selectinload(MeetingSession.group))
        .where(
            MeetingSession.id == session_id,
            MeetingSession.is_deleted == False   # noq: E712
        )
    )
    return result.scalar_one_or_none()


async def _assert_can_mark_session(
        db: AsyncSession, user: User, session: MeetingSession
) -> None:
    """
    Ensure the user has permission to mark attendance for this session.
    - Elevated roles (admin, pastor, super_admin) can mark any session.
    - Leaders can only mark their own group's sessions.
    - Sunday service: leaders can mark attendance (their group's members).
    """
    if _is_elevated(user):
        return

    leader_group_id = await _get_leader_group_id(db, user)
    if not leader_group_id:
        raise ForbiddenException("You are not assigned to any group")

    # For fellowship meetings, must be the leader of that specific group
    if (
            session.meeting_type == MeetingType.fellowship_meeting
            and session.group_id != leader_group_id
    ):
        raise ForbiddenException(
            "You can only mark attendance for your own group's sessions"
        )


async def _assert_member_in_session_scope(
        db: AsyncSession,
        user: User,
        member_id: uuid.UUID,
        session: MeetingSession,
) -> None:
    """
    For leaders: confirm the member belongs to their group before
    allowing them to mark that member's attendance.
    """
    if _is_elevated(user):
        return

    leader_group_id = await _get_leader_group_id(db, user)
    membership_result = await db.execute(
        select(GroupMembership).where(
            GroupMembership.member_id == member_id,
            GroupMembership.group_id == leader_group_id,
            GroupMembership.is_deleted == False  # noqa: E712
        )
    )
    if not membership_result.scalar_one_or_none():
        raise ForbiddenException(
            "You can only mark attendance for members in your group"
        )


async def _load_session_records(
        db: AsyncSession, session_id: uuid.UUID
) -> list[AttendanceRecord]:
    """Load all attendance records for a session with member/visitor info."""
    result = await db.execute(
        select(AttendanceRecord)
        .options(
            selectinload(AttendanceRecord.member),
            selectinload(AttendanceRecord.visitor),
        )
        .where(AttendanceRecord.session_id == session_id)
        .order_by(AttendanceRecord.marked_at)
    )
    return list(result.scalars().all())


def _build_record_response(record: AttendanceRecord) -> AttendanceRecordResponse:
    return AttendanceRecordResponse(
        id=record.id,
        session_id=record.session_id,
        member=MemberAttendanceSummary(
            id=record.member.id,
            first_name=record.member.first_name,
            last_name=record.member.last_name,
        ) if record.member else None,
        visitor=VisitorAttendanceSummary(
            id=record.visitor.id,
            first_name=record.visitor.first_name,
            last_name=record.visitor.last_name,
        ) if record.visitor else None,
        status=record.status,
        note=record.note,
        marked_at=record.marked_at,
    )


def _build_session_attendance_response(
        session: MeetingSession,
        records: list[AttendanceRecord],
) -> SessionAttendanceResponse:
    """Compute summary counts and assemble the full session attendance response."""
    record_responses = [_build_record_response(r) for r in records]

    present = sum(1 for r in records if r.status == AttendanceStatus.present)
    absent = sum(1 for r in records if r.status == AttendanceStatus.absent)
    excused = sum(1 for r in records if r.status == AttendanceStatus.excused)
    late = sum(1 for r in records if r.status == AttendanceStatus.late)

    return SessionAttendanceResponse(
        session_id=session.id,
        meeting_type=session.meeting_type,
        meeting_date=str(session.meeting_date),
        group_id=session.group_id,
        group_name=session.group.name if session.group else None,
        total_records=len(records),
        present_count=present,
        absent_count=absent,
        excused_count=excused,
        late_count=late,
        records=record_responses,
    )


# ---------------------------------------------------------------------------
# Bulk submit (primary attendance-marking flow)
# ---------------------------------------------------------------------------

async def bulk_submit_attendance(
        db: AsyncSession,
        data: AttendanceBulkSubmit,
        marked_by: User,
) -> SessionAttendanceResponse:
    """
    Submit attendance for an entire session.

    This is the main attendance flow. The caller provides a session_id
    and a list of entries (member or visitor + status).

    Behaviour:
    - Existing records for this session are UPSERTED — if a record already
      exists for a member/visitor in this session, it is updated in place.
      New entries are inserted. This allows leaders to re-submit corrections
      without first deleting the session's records.
    - Leaders are validated against their group membership before each entry.
    - Visitors are not scoped — any visitor can be marked in any session.
    """
    session = await _get_session(db, data.session_id)
    if not session:
        raise NotFoundException("Session not found")

    await _assert_can_mark_session(db, marked_by, session)

    for entry in data.entries:
        if entry.member_id:
            # Confirm member exists
            member_result = await db.execute(
                select(Member).where(
                    Member.id == entry.member_id,
                    Member.is_deleted == False  # noqa: E712
                )
            )
            if not member_result.scalar_one_or_none():
                raise NotFoundException(
                    f"Member {entry.member_id} not found"
                )
            # Leaders: confirm member is in their group
            await _assert_member_in_session_scope(
                db, marked_by, entry.member_id, session
            )

            # Upsert: check for existing record
            existing_result = await db.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.session_id == data.session_id,
                    AttendanceRecord.member_id == entry.member_id,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                existing.status = entry.status
                existing.note = entry.note
                existing.marked_by_id = marked_by.id
                db.add(existing)
            else:
                db.add(AttendanceRecord(
                    session_id=data.session_id,
                    member_id=entry.member_id,
                    visitor_id=None,
                    status=entry.status,
                    note=entry.note,
                    marked_by_id=marked_by.id,
                ))

        elif entry.visitor_id:
            # Confirm visitor exists
            visitor_result = await db.execute(
                select(Visitor).where(
                    Visitor.id == entry.visitor_id,
                    Visitor.is_deleted == False  # noqa: E712
                )
            )
            if not visitor_result.scalar_one_or_none():
                raise NotFoundException(
                    f"Visitor {entry.visitor_id} not found"
                )

            # Upsert for visitors
            existing_result = await db.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.session_id == data.session_id,
                    AttendanceRecord.visitor_id == entry.visitor_id,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                existing.status = entry.status
                existing.note = entry.note
                existing.marked_by_id = marked_by.id
                db.add(existing)
            else:
                db.add(AttendanceRecord(
                    session_id=data.session_id,
                    member_id=None,
                    visitor_id=entry.visitor_id,
                    status=entry.status,
                    note=entry.note,
                    marked_by_id=marked_by.id,
                ))

    await db.flush()

    records = await _load_session_records(db, data.session_id)
    return _build_session_attendance_response(session, records)


# ---------------------------------------------------------------------------
# Get session attendance
# ---------------------------------------------------------------------------

async def get_session_attendance(
        db: AsyncSession,
        session_id: uuid.UUID,
        requesting_user: User,
) -> SessionAttendanceResponse:
    """
    Retrieve the full attendance sheet for a session.
    Leaders can only view their own group's sessions.
    Sunday service sessions are visible to all.
    """
    session = await _get_session(db, session_id)
    if not session:
        raise NotFoundException("Session not found")

    if not _is_elevated(requesting_user):
        if session.meeting_type == MeetingType.fellowship_meeting:
            await _assert_can_mark_session(db, requesting_user, session)

    records = await _load_session_records(db, session_id)
    return _build_session_attendance_response(session, records)


# ---------------------------------------------------------------------------
# Update a single attendance record
# ---------------------------------------------------------------------------

async def update_attendance_record(
        db: AsyncSession,
        record_id: uuid.UUID,
        data: AttendanceRecordUpdate,
        updated_by: User,
) -> AttendanceRecordResponse:
    """
    Correct a single attendance record after a bulk submission.
    Leaders can only update records for members in their group.
    """
    result = await db.execute(
        select(AttendanceRecord)
        .options(
            selectinload(AttendanceRecord.member),
            selectinload(AttendanceRecord.visitor),
        )
        .where(AttendanceRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise NotFoundException("Attendance record not found")

    # Validate leader scope for member records
    if record.member_id and not _is_elevated(updated_by):
        session = await _get_session(db, record.session_id)
        await _assert_can_mark_session(db, updated_by, session)
        await _assert_member_in_session_scope(
            db, updated_by, record.member_id, session
        )

    record.status = data.status
    record.note = data.note
    record.marked_by_id = updated_by.id
    db.add(record)
    await db.flush()

    return _build_record_response(record)


# ---------------------------------------------------------------------------
# Member attendance history
# ---------------------------------------------------------------------------

async def get_member_attendance_history(
        db: AsyncSession,
        member_id: uuid.UUID,
        requesting_user: User,
        meeting_type: MeetingType | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        offset: int = 0,
        limit: int = 20,
) -> MemberAttendanceHistoryResponse:
    """
    Retrieve a member's attendance history across sessions.
    Leaders can only view members in their own group.
    Computes attendance rate across the filtered sessions.
    """
    # Confirm member exists
    member_result = await db.execute(
        select(Member).where(
            Member.id == member_id,
            Member.is_deleted == False  # noqa: E712
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise NotFoundException("Member not found")

    # Scope check for leaders
    if not _is_elevated(requesting_user):
        leader_group_id = await _get_leader_group_id(db, requesting_user)
        membership_result = await db.execute(
            select(GroupMembership).where(
                GroupMembership.member_id == member_id,
                GroupMembership.group_id == leader_group_id,
                GroupMembership.is_deleted == False  # noqa: E712
            )
        )
        if not membership_result.scalar_one_or_none():
            raise ForbiddenException("This member does not belong to your group")

    # Build attendance records query with optional filters
    query = (
        select(AttendanceRecord)
        .options(
            selectinload(AttendanceRecord.member),
            selectinload(AttendanceRecord.visitor),
        )
        .join(MeetingSession, AttendanceRecord.session_id == MeetingSession.id)
        .where(
            AttendanceRecord.member_id == member_id,
            MeetingSession.is_deleted == False  # noqa: E712
        )
    )

    if meeting_type:
        query = query.where(MeetingSession.meeting_type == meeting_type)

    if from_date:
        query = query.where(MeetingSession.meeting_date >= from_date)

    if to_date:
        query = query.where(MeetingSession.meeting_date <= to_date)

    # Total count for attendance rate (unfiltered by pagination)
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total_sessions = count_result.scalar_one()

    # Count present records for attendance rate
    present_result = await db.execute(
        select(func.count()).select_from(
            query.where(
                AttendanceRecord.status == AttendanceStatus.present
            ).subquery()
        )
    )
    present_count = present_result.scalar_one()

    # Paginated records
    paginated_result = await db.execute(
        query.order_by(MeetingSession.meeting_date.desc())
        .offset(offset)
        .limit(limit)
    )
    records = list(paginated_result.scalars().all())

    attendance_rate = (
        round((present_count / total_sessions) * 100, 1)
        if total_sessions > 0 else 0.0
    )

    return MemberAttendanceHistoryResponse(
        member_id=member_id,
        full_name=f"{member.first_name} {member.last_name}",
        total_sessions=total_sessions,
        present_count=present_count,
        attendance_rate=attendance_rate,
        records=[_build_record_response(r) for r in records],
    )



