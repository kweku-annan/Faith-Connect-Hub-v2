from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.schemas.group import (
    GroupCreate,
    GroupResponse,
    GroupUpdate,
    GroupDetailResponse,
    AssignLeaderRequest,
    RemoveLeaderRequest,
    AssignMemberRequest
)
from app.services import group_service
from app.api.v1.dependencies import get_current_user, require_roles
from app.models.user import RoleName, User
from app.utils.pagination import PaginationParams, PaginatedResponse

router = APIRouter()


@router.post(
    "/",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new group",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))]
)
async def create_group(
        data: GroupCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Create a new fellowship group,

    Requires: `super_admin` or `admin` role
    """
    return await group_service.create_group(db, data, current_user)


@router.get(
    "/",
    response_model=PaginatedResponse[GroupResponse],
    summary="List all groups",
)
async def list_groups(
        is_active: bool | None = Query(None, description="Filter by active status"),
        search: str | None = Query(None, description="Search by group name"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Retrieve all groups
    - Leaders: see only their own group
    - Pastors/Admins/Super Admins see all groups with optional filters.
    """
    params = PaginationParams(page=page, page_size=page_size)
    groups, total = await group_service.list_groups(
        db,
        requesting_user=current_user,
        is_active=is_active,
        search=search,
        offset=params.offset,
        limit=params.page_size,
    )
    return PaginatedResponse.create(items=groups, total=total, params=params)


@router.get(
    "/{group_id}",
    response_model=GroupDetailResponse,
    summary="Get a group with full details",
)
async def get_group(
        group_id: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Retrieve a group's full profile including its leaders and member list.

    - Leaders can only view their own group.
    - Pastors/Admins/Super Admins can view any group.
    """
    return await group_service.get_group(db, group_id, current_user)


@router.patch(
    "/{group_id}",
    response_model=GroupResponse,
    summary="Update a group's details",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))]
)
async def update_group(
        group_id: UUID,
        data: GroupUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Update a group's name, description, or active status.

    Requires: `super_admin` or `admin` role.
    """
    return await group_service.update_group(db, group_id, data, current_user)


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a group",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))],
)
async def delete_group(
        group_id: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Soft-delete a group. Blocked if the group still has active members.

    Requires: `super_admin` or `admin` role.
    """
    await group_service.delete_group(db, group_id, current_user)


@router.post(
    "/{group_id}/leaders",
    response_model=GroupResponse,
    summary="Create a new leader",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))]
)
async def assign_leader(
        group_id: UUID,
        data: AssignLeaderRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Assign a user as a leader of this group.

    - The user must already be a member of this group.
    - Setting `is_primary=true` demotes the current primary leader.

    Requires: `super_admin` or `admin` role.
    """
    return await group_service.assign_leader(db, group_id, data, current_user)


@router.delete(
    "/{group_id}/leaders",
    response_model=GroupResponse,
    summary="Remove a leader from a group",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))]
)
async def remove_leader(
        group_id: UUID,
        data: RemoveLeaderRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Remove a user's leadership role from this group.
    They remain a member of the group.
    Blocked if they are the only leader.
    """
    return await group_service.remove_leader(db, group_id, data, current_user)


@router.post(
    "/{group_id}/members",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a member to this group",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin, RoleName.pastor))],
)
async def assign_member(
        group_id: UUID,
        data: AssignMemberRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Assign an existing church member to this group.
    To move a member between groups, use `POST /members/{id}/transfer`.

    Requires: `super_admin` `pastor` or `admin` role.
    """
    return await group_service.assign_member(db, group_id, data, current_user)

