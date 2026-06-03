from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from sqlalchemy.sql.functions import current_user

from app.db.session import get_db
from app.schemas.member import MemberCreate, MemberUpdate, MemberTransfer, MemberResponse
from app.schemas.common import PaginatedResponse
from app.services import member_service
from app.api.v1.dependencies import get_current_user, require_roles
from app.models.user import RoleName, User
from app.utils.pagination import PaginationParams, PaginatedResponse as PaginatedUtil

router = APIRouter()

@router.post("/", response_model=MemberResponse, status_code=status.HTTP_201_CREATED, summary="Create a new member")
async def create_member(data: MemberCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create a new member. Requires super_admin or admin role."""
    return await member_service.create_member(db, data, current_user)


@router.get("/", response_model=PaginatedUtil[MemberResponse], summary="List church members")
async def list_members(
        group_id: UUID | None = Query(None, description="Filter by group (admin/pastor only)"),
        status: str | None = Query(None, description="Filter by member status (active/inactive)"),
        search: str | None = Query(None, description="Search by name or email"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Retrieve a paginated list of members.
    - Leaders automatically see only their own group's members.
    - Pastors/Admins/Super Admins can filter by any group or see all.
    """
    params = PaginationParams(page=page, page_size=page_size)
    members, total = await member_service.list_members(
        db,
        requesting_user=current_user,
        group_id=group_id,
        status=status,
        search=search,
        offset=params.offset,
        limit=params.page_size
    )
    return PaginatedUtil.create(items=members, total=total, params=params)


@router.get("/{member_id}", response_model=MemberResponse, summary="Get a member by ID")
async def get_member(
        member_id: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Retrieve a single member's full profile.
    
        - Leaders can only access members in their own group.
        - Pastors/Admins/Super Admins can view any member.
    """
    return await member_service.get_member(db, member_id, current_user)


@router.patch("/{member_id}", response_model=MemberResponse, summary="Update a member's details")
async def update_member(
        member_id: UUID,
        data: MemberUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Practically update a member record. Only provided fields are changed.
    - Leaders can only update members in their own group
    - Pastors/Admins/Super Admins can update any member.
    """
    return await member_service.update_member(db, member_id, data, current_user)


@router.post(
    "/{member_id}/transfer",
    response_model=MemberResponse,
    summary="Transfer a member to a different group",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))],
)
async def transfer_member(
        member_id: UUID,
        data: MemberTransfer,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Move a member from their current group to another group.
    The old membership is preserved in history (soft delete)

    - Requires: super_admin or admin role. Leaders cannot transfer members.
    """
    return await member_service.transfer_member(db, member_id, data, current_user)


@router.delete(
    "/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a member",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))],
)
async def delete_member(
        member_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Soft-delete a member from the church register.
    The member's history (attendance, past group memberships) is preserved.
    Members with active user accounts must have their account deactivated first.
    """
    await member_service.delete_member(db, member_id, current_user)
