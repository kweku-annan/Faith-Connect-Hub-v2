import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.meeting import MeetingSession, MeetingType
from app.models.group import Group, GroupLeader
from app.models.attendance import AttendanceRecord
from app.models.user import User, RoleName
from app.schemas.meeting import (
    MeetingSessionCreate,
    MeetingSessionUpdate,
    MeetingSessionResponse,
)
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_elevated(user: User) -> bool:
    """True for super_admin, admin, pastor."""
    roles = [r.role for r in user.roles]
    return any(r in roles for r in [
        RoleName.super_admin, RoleName.admin, RoleName.pastor
    ])


async def _get_leader_group_id(
    db: AsyncSession, user: User
) -> uuid.UUID | None:
    """Return the group_id the user leads, or None."""
    result = await db.execute(
        select(GroupLeader.group_id).where(
            GroupLeader.user_id == user.id,
            GroupLeader.is_deleted == False  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _get_session_with_group(
        db: AsyncSession, session_id: uuid.UUID
) -> MeetingSession | None:
    """Fetch a session and eagerly load its group."""
    result = await db.execute(
        select(MeetingSession)
        .options(selectinload(MeetingSession.group))
        .where(
            MeetingSession.id == session_id,
            MeetingSession.is_deleted == False  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def _build_session_response(
        db: AsyncSession, session: MeetingSession
) -> MeetingSessionResponse:
    """Build a MeetingSessionResponse, computing the attendance count."""
    count_result = await db.execute(
        select(func.count())
        .select_from(AttendanceRecord)
        .where(AttendanceRecord.session_id == session.id)
    )
    attendance_count = count_result.scalar_one()

    return MeetingSessionResponse(
        id=session.id,
        meeting_type=session.meeting_type,
        meeting_date=session.meeting_date,
        meeting_time=session.meeting_time,
        group_id=session.group_id,
        group_name=session.group.name if session.group else None,
        notes=session.notes,
        attendance_count=attendance_count,
        created_at=session.created_at,
    )


async def _assert_leader_owns_session(
        db: AsyncSession, user: User, session: MeetingSession
) -> None:
    """
    Raise ForbiddenException if a leader tries to access a session
    that doesn't belong to their group.
    """
    leader_group_id = await _get_leader_group_id(db, user)
    if not leader_group_id:
        raise ForbiddenException("You are not assigned to any group")
    if session.group_id != leader_group_id:
        raise ForbiddenException("You do not have access to this session")


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_session(
        db: AsyncSession,
        data: MeetingSessionCreate,
        created_by: User,
) -> MeetingSessionResponse:
    """
    Create a new meeting session.

    Rules:
      - Sunday Service | Church-wide meetings: no group_id, Pastors, admins, and super_admins can create.
      - Fellowship meeting: must have a group_id. Leaders can only create sessions for their own group.
      Pastors, admins, and super_admins can create for any group.
      - No duplicate sessions (same group + date + type).
    """
    # For fellowship meetings, validate group access.
    if data.meeting_type == MeetingType.fellowship_meeting:
        group_result = await db.execute(
            select(Group).where(
                Group.id == data.group_id,
                Group.is_deleted == False,
                Group.is_active == True
            )
        )
        group = group_result.scalar_one_or_none()
        if not group:
            raise NotFoundException("Group not found or is inactive")

        # Leaders can only create sessions for their own group
        if not _is_elevated(created_by):
            leader_group_id = await _get_leader_group_id(db, created_by)
            if leader_group_id != data.group_id:
                raise ForbiddenException("You can only create sessions for your own group")

    else:
        # Only Pastors, admins, and super_admins can create church-wide sessions.
        if not _is_elevated(created_by):
            raise ForbiddenException("You do not have permission to create this type of session")


    # Duplicate check - same group + date + type
    duplicate = await db.execute(
        select(MeetingSession).where(
            MeetingSession.group_id == data.group_id,
            MeetingSession.meeting_date == data.meeting_date,
            MeetingSession.meeting_type == data.meeting_type,
            MeetingSession.is_deleted == False  # noqa: E712
        )
    )
    if duplicate.scalar_one_or_none():
        raise ConflictException("A session with this group, date, and type already exists")

    session = MeetingSession(
        group_id=data.group_id,
        meeting_type=data.meeting_type,
        meeting_date=data.meeting_date,
        notes=data.notes,
        created_by_id=created_by.id,
    )
    db.add(session)
    await db.flush()

    session = await _get_session_with_group(db, session.id)
    return await _build_session_response(db, session)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_session(
        db: AsyncSession,
        session_id: uuid.UUID,
        requesting_user: User,
) -> MeetingSessionResponse:
    """
    Fetch a single session by ID.
    Leaders can only view sessions for their own group or church-wide Sunday services.
    """
    session = await _get_session_with_group(db, session_id)
    if not session:
        raise NotFoundException("Session not found")

    if not _is_elevated(requesting_user):
        # Sunday service sessions are visible to all
        if session.meeting_type == MeetingType.general:
            return await _build_session_response(db, session)
        await _assert_leader_owns_session(db, requesting_user, session)

    return await _build_session_response(db, session)


async def list_sessions(
        db: AsyncSession,
        requesting_user: User,
        group_id: uuid.UUID | None = None,
        meeting_type: MeetingType | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        offset: int = 0,
        limit: int = 20,
) -> tuple[list[MeetingSessionResponse], int]:
    """
    List meeting sessions with optional filters.
    Leaders are scoped to their group's sessions + all Sunday | General services.
    Returns (sessions, total_count).
    """
    query = (
        select(MeetingSession)
        .options(selectinload(MeetingSession.group))
        .where(MeetingSession.is_deleted == False)  # noqa: E712
    )

    if not _is_elevated(requesting_user):
        # Leaders see their group's fellowship meetings + all Sunday services
        leader_group_id = await _get_leader_group_id(db, requesting_user)
        query = query.where(
            (MeetingSession.meeting_type == MeetingType.general) |
            (MeetingSession.group_id == leader_group_id)
        )
    elif group_id:
        query = query.where(MeetingSession.group_id == group_id)

    if meeting_type:
        query = query.where(MeetingSession.meeting_type == meeting_type)

    if from_date:
        query = query.where(MeetingSession.meeting_date >= from_date)

    if to_date:
        query = query.where(MeetingSession.meeting_date <= to_date)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    result = await db.execute(
        query.order_by(MeetingSession.meeting_date.desc())
        .offset(offset)
        .limit(limit)
    )
    sessions = result.scalars().all()

    responses = [
        await _build_session_response(db, s) for s in sessions
    ]
    return responses, total


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_session(
        db: AsyncSession,
        session_id: uuid.UUID,
        data: MeetingSessionUpdate,
        updated_by: User,
) -> MeetingSessionResponse:
    """
    Update a session's notes or date.
    Leaders can only update their own group's sessions.
    Meeting type and group cannot be changed after creation.
    """
    session = await _get_session_with_group(db, session_id)
    if not session:
        raise NotFoundException("Session not found")

    if not _is_elevated(updated_by):
        await _assert_leader_owns_session(db, updated_by, session)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)

    db.add(session)
    await db.flush()

    session = await _get_session_with_group(db, session_id)
    return await _build_session_response(db, session)



# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------

async def delete_session(
        db: AsyncSession,
        session_id: uuid.UUID,
        deleted_by: User,
) -> None:
    """
    Soft-delete a meeting session. Admin/super_admin only.
    Blocked if attendance has already been marked for this session.
    TODO: Update for leaders to be able to update their own group sessions.
    """
    if not any(
            r.role in [RoleName.super_admin, RoleName.admin]
            for r in deleted_by.roles
    ):
        raise ForbiddenException("Only admins can delete sessions")

    session = await _get_session_with_group(db, session_id)
    if not session:
        raise NotFoundException("Session not found")

    # Block deletion if attendance records exist
    attendance_count = await db.execute(
        select(func.count())
        .select_from(AttendanceRecord)
        .where(AttendanceRecord.session_id == session_id)
    )
    if attendance_count.scalar_one() > 0:
        raise BadRequestException(
            "Cannot delete a session that already has attendance records. "
            "Clear the attendance first."
        )

    session.is_deleted = True
    db.add(session)
    await db.flush()










