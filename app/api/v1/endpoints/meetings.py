from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from app.db.session import get_db
from app.schemas.meeting import (
    MeetingSessionCreate,
    MeetingSessionUpdate,
    MeetingSessionResponse,
)
from app.services import meeting_service
from app.api.v1.dependencies import get_current_user, require_roles
from app.models.user import RoleName, User
from app.models.meeting import MeetingType
from app.utils.pagination import PaginationParams, PaginatedResponse


router = APIRouter()


@router.post(
    "/",
    response_model=MeetingSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new meeting session",
)
async def create_session(
        data: MeetingSessionCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Create a new meeting session.

    - For `general_service | church-wide`: leave `group_id` empty — it's church-wide.
    - For `fellowship_meeting`: `group_id` is required.
    - Meeting date and time cannot be in the past.
    - Duplicate sessions (same type + group + date) are rejected.

    **Requires:** any authenticated role | except leaders.
    Leaders can only create fellowship sessions for their own group.
    """
    return await meeting_service.create_session(db, data, current_user)


@router.get(
    "/",
    response_model=PaginatedResponse[MeetingSessionResponse],
    summary="List meeting sessions",
)
async def list_sessions(
        group_id: Optional[UUID] = Query(None, description="Filter by group (admin/pastor only)"),
        meeting_type: Optional[MeetingType] = Query(None, description="Filter by meeting type"),
        from_date: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
        to_date: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Retrieve a paginated list of meeting sessions, most recent first.

    - **Leaders** see their own group's fellowship sessions + all Sunday services.
    - **Pastors / Admins / Super Admins** see all sessions with optional filters.

    **Requires:** any authenticated role.
    """
    params = PaginationParams(page=page, page_size=page_size)
    sessions, total = await meeting_service.list_sessions(
        db,
        requesting_user=current_user,
        group_id=group_id,
        meeting_type=meeting_type,
        from_date=from_date,
        to_date=to_date,
        offset=params.offset,
        limit=params.page_size,
    )
    return PaginatedResponse.create(items=sessions, total=total, params=params)


@router.get(
    "/{session_id}",
    response_model=MeetingSessionResponse,
    summary="Get a session by ID",
)
async def get_session(
        session_id: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Retrieve a single meeting session including its attendance count.

    - **Leaders** can view their own group's sessions and all Sunday services.
    - **Pastors / Admins / Super Admins** can view any session.

    **Requires:** any authenticated role.
    """
    return await meeting_service.get_session(db, session_id, current_user)


@router.patch(
    "/{session_id}",
    response_model=MeetingSessionResponse,
    summary="Update a session",
)
async def update_session(
        session_id: UUID,
        data: MeetingSessionUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Update a session's notes or date.
    Meeting type and group cannot be changed after creation.

    - **Leaders** can only update their own group's sessions.
    - **Pastors / Admins / Super Admins** can update any session.

    **Requires:** any authenticated role.
    """
    return await meeting_service.update_session(db, session_id, data, current_user)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))],
)
async def delete_session(
        session_id: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Soft-delete a meeting session.
    Blocked if attendance has already been marked for this session.

    **Requires:** `super_admin` or `admin` role.
    """
    await meeting_service.delete_session(db, session_id, current_user)



