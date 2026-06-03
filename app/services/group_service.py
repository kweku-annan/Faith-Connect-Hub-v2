import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.group import Group, GroupLeader, GroupMembership
from app.models.member import Member
from app.models.user import User, RoleName
from app.schemas.group import (
    GroupCreate,
    GroupUpdate,
    GroupResponse,
    GroupDetailResponse,
    LeaderSummary,
    AssignLeaderRequest,
    AddMemberRequest,
    RemoveLeaderRequest,
)
from app.schemas.member import MemberSummary
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    ForbiddenException
)


# -----------------------------------------------------
# Helpers
# -----------------------------------------------------

def _can_create_group(user: User) -> bool:
    roles = [r.role for r in user.roles]
    return any(r in roles for r in [RoleName.super_admin, RoleName.admin])

def _can_assign_members(user: User) -> bool:
    roles = [r.role for r in user.roles]
    return any(r in roles for r in [RoleName.super_admin, RoleName.admin, RoleName.pastor])

def _can_view_all(user: User) -> bool:
    roles = [r.role for r in user.roles]
    return any(r in roles for r in [RoleName.super_admin, RoleName.admin, RoleName.pastor])

async def _get_group_full(db: AsyncSession, group_id: uuid.UUID) -> Group:
    """Fetch group with leaders and their user+member info loaded"""
    result = await db.execute(
        select(Group).options(
            selectinload(Group.leaders)
            .selectinload(GroupLeader.user)
            .selectinload(User.member),
            selectinload(Group.memberships)
            .selectinload(GroupMembership.member),
        )
        .where(Group.id == group_id, Group.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def _build_group_response(
        db: AsyncSession, group: Group, include_members: bool = False
) -> GroupResponse | GroupDetailResponse:
    """
    Build a GroupResponse or GroupDetailResponse from a Group ORM object.
    Computes member_count and assembles leader/member summaries.
    """
    # Count active (non-deleted) memberships
    count_result = await db.execute(
        select(func.count())
        .select_from(GroupMembership)
        .where(
            GroupMembership.group_id == group.id,
            GroupMembership.is_deleted == False
        )
    )
    member_count = count_result.scalar_one()

    # Build leader summaries from active (non-deleted) group leaders
    leaders = [
        LeaderSummary(
            user_id=gl.user_id,
            email=gl.user.email,
            full_name=f"{gl.user.member.first_name} {gl.user.member.last_name}",
            is_primary=gl.is_primary,
        )
        for gl in group.leaders
        if not gl.is_deleted
    ]

    base_data = dict(
        id=group.id,
        name=group.name,
        description=group.description,
        is_active=group.is_active,
        member_count=member_count,
        leaders=leaders,
        created_at=group.created_at,
        updated_at=group.updated_at
    )

    if include_members:
        members = [
            MemberSummary.model_validate(gm.member)
            for gm in group.memberships
            if not gm.is_deleted
        ]
        return GroupDetailResponse(**base_data, members=members)

    return GroupResponse(**base_data)


# ------------------------------------------------------------------------
# Create
# ------------------------------------------------------------------------

async def create_group(
        db: AsyncSession,
        data: GroupCreate,
        created_by: User,
) -> GroupResponse:
    """
    Create a new fellowship group.
    Only super_admin and admin can create groups
    """
    if not _can_create_group(created_by):
        raise ForbiddenException("Only admins can create groups")

    # Enforce unique name
    existing = await db.execute(
        select(Group).where(
            Group.name == data.name,
            Group.is_deleted == False,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictException(f"A group with this name '{data.name}' already exists.")

    group = Group(
        name=data.name,
        description=data.description,
        created_by_id=created_by.id,
    )
    db.add(group)
    await db.flush()

    group = await _get_group_full(db, group.id)
    return await _build_group_response(db, group)


# ----------------------------------------------------------
# Read
# ----------------------------------------------------------

async def get_group(
        db: AsyncSession,
        group_id: uuid.UUID,
        requesting_user: User,
) -> GroupDetailResponse:
    """
    Get a single group with full details including members and leaders.
    Leaders can only view their own group.
    """
    group = await _get_group_full(db, group_id)
    if not group:
        raise NotFoundException("Group not found")

    # Leaders restricted to their own group
    if not _can_view_all(requesting_user):
        leader_result = await db.execute(
            select(GroupLeader).where(
                GroupLeader.user_id == requesting_user.id,
                GroupLeader.group_id == group_id,
                GroupLeader.is_deleted == False,
            )
        )
        if not leader_result.scalar_one_or_none():
            raise ForbiddenException("You do not have access to this group.")

    return await _build_group_response(db, group, include_members=True)









