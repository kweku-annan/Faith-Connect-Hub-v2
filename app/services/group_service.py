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
    AssignLeaderRequest,
    AssignMemberRequest,
    RemoveLeaderRequest,
)
from app.schemas.group import GroupResponse, GroupDetailResponse, LeaderSummary
from app.schemas.member import MemberSummary
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
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

async def list_groups(
        db: AsyncSession,
        requesting_user: User,
        is_active: bool | None = None,
        search: str | None = None,
        offset: int  = 0,
        limit: int = 20,
) -> tuple[list[GroupResponse], int]:
    """
    List all groups,
    Leaders see only their own group.
    Pastors/admins/super_admin see all groups.
    Returns (groups, total_count).
    """
    if not _can_view_all(requesting_user):
        # Leaders: find their one group and return it directly
        leader_result = await db.execute(
            select(GroupLeader.group_id).where(
                GroupLeader.user_id == requesting_user.id,
                GroupLeader.is_deleted == False, # noqa E712
            )
        )
        leader_group_id = leader_result.scalar_one_or_none()
        if not leader_group_id:
            return  [], 0

        group = await _get_group_full(db, leader_group_id)
        if not group:
            return [], 0
        response = await _build_group_response(db, group)
        return [response], 1

    # Admins/pastors: full list with filters
    query = (
        select(Group)
        .options(
            selectinload(Group.leaders)
            .selectinload(GroupLeader.user)
            .selectinload(User.member),
        )
        .where(Group.is_deleted == False) # noqa: E712
    )

    if is_active is not None:
        query = query.where(Group.is_active == is_active)

    if search:
        query = query.where(
            func.lower(Group.name).like(f"%{search.lower()}%")
        )

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    result = await db.execute(
        query.order_by(Group.name).offset(offset).limit(limit)
    )
    groups = result.scalars().all()

    responses = [
        await _build_group_response(db, g) for g in groups
    ]
    return responses, total


# -----------------------------------------------------------------------------------------
# Update
# -----------------------------------------------------------------------------------------

async def update_group(
        db: AsyncSession,
        group_id: uuid.UUID,
        data: GroupUpdate,
        updated_by: User,
) -> GroupResponse:
    """Update group name, description, or active status. Admin/super_admin only"""
    if not _can_create_group(updated_by):
        raise ForbiddenException("Only admins can update groups")

    group = await _get_group_full(db, group_id)
    if not group:
        raise NotFoundException("Group not found")

    # Name uniqueness check if name is being changed
    if data.name and data.name != group.name:
        existing = await db.execute(
            select(Group).where(
                Group.name == data.name,
                Group.is_deleted == False,
                Group.id != group_id
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictException(f"A group with this name '{data.name}' already exists.")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)

    db.add(group)
    await db.flush()

    group = await _get_group_full(db, group_id)
    return await _build_group_response(db, group)


# -----------------------------------------------------------------
# Soft delete
# -----------------------------------------------------------------

async def delete_group(
        db: AsyncSession,
        group_id: uuid.UUID,
        deleted_by: User,
) -> None:
    """
    Soft-delete a group. Only super_admin and admin can do this.
    Blocked if the group still ahs active members.
    """
    if not _can_create_group(deleted_by):
        raise ForbiddenException("Only admins can delete groups")

    group = await _get_group_full(db, group_id)
    if not group:
        raise NotFoundException("Group not found")

    # Block deletion if group still has active members.
    active_members = await db.execute(
        select(func.count())
        .select_from(GroupMembership)
        .where(
            GroupMembership.group_id == group_id,
            GroupMembership.is_deleted == False,
        )
    )
    if active_members.scalar_one() > 0:
        raise BadRequestException(
            "Cannot delete group with active members. Please remove all members before deleting."
        )

    group.is_deleted = True
    db.add(group)
    await db.flush()


# ---------------------------------------------------------------------------
# Assign leader
# ---------------------------------------------------------------------------

async def assign_leader(
        db: AsyncSession,
        group_id: uuid.UUID,
        data: AssignLeaderRequest,
        assigned_by: User,
) -> GroupResponse:
    """
    Assign a user as a leader of a group.

    Rules enforced:
    - Only admins can assign leaders
    - The user must already be a member of this group
    - A user can only lead one group
    - If is_primary=True, any existing primary leader is demoted first
    """
    if not _can_create_group(assigned_by):
        raise ForbiddenException("Only admins can assign leaders")

    group = await _get_group_full(db, group_id)
    if not group:
        raise NotFoundException("Group not found")

    # Confirm the user exists
    user_result = await db.execute(
        select(User).where(
            User.id == data.user_id,
            User.is_deleted == False,  # noqa: E712
            User.is_active == True  # noqa: E712
        )
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise NotFoundException("User not found or inactive")

    # The user must be a member of this group
    membership_result = await db.execute(
        select(GroupMembership).where(
            GroupMembership.member_id == user.member_id,
            GroupMembership.group_id == group_id,
            GroupMembership.is_deleted == False  # noqa: E712
        )
    )
    if not membership_result.scalar_one_or_none():
        raise BadRequestException(
            "The user must be a member of this group before being assigned as leader"
        )

    # Check this user doesn't already lead another group
    existing_leadership = await db.execute(
        select(GroupLeader).where(
            GroupLeader.user_id == data.user_id,
            GroupLeader.is_deleted == False  # noqa: E712
        )
    )
    existing = existing_leadership.scalar_one_or_none()
    if existing:
        if existing.group_id == group_id:
            raise ConflictException("This user is already a leader of this group")
        raise ConflictException("This user already leads another group")

    # Demote existing primary leader if assigning a new one
    if data.is_primary:
        current_primary_result = await db.execute(
            select(GroupLeader).where(
                GroupLeader.group_id == group_id,
                GroupLeader.is_primary == True,  # noqa: E712
                GroupLeader.is_deleted == False  # noqa: E712
            )
        )
        current_primary = current_primary_result.scalar_one_or_none()
        if current_primary:
            current_primary.is_primary = False
            db.add(current_primary)

    new_leader = GroupLeader(
        group_id=group_id,
        user_id=data.user_id,
        is_primary=data.is_primary,
        assigned_by_id=assigned_by.id,
    )
    db.add(new_leader)
    await db.flush()

    group = await _get_group_full(db, group_id)
    return await _build_group_response(db, group)


# ---------------------------------------------------------------------------
# Remove leader
# ---------------------------------------------------------------------------

async def remove_leader(
        db: AsyncSession,
        group_id: uuid.UUID,
        data: RemoveLeaderRequest,
        removed_by: User,
) -> GroupResponse:
    """
    Remove a user's leadership from a group (soft delete).
    They remain a member of the group.
    Blocked if they are the only leader left.
    """
    if not _can_create_group(removed_by):
        raise ForbiddenException("Only admins can remove leaders")

    group = await _get_group_full(db, group_id)
    if not group:
        raise NotFoundException("Group not found")

    leader_result = await db.execute(
        select(GroupLeader).where(
            GroupLeader.group_id == group_id,
            GroupLeader.user_id == data.user_id,
            GroupLeader.is_deleted == False  # noqa: E712
        )
    )
    leader = leader_result.scalar_one_or_none()
    if not leader:
        raise NotFoundException("This user is not a leader of this group")

    # Block if they are the only active leader
    active_leaders_count = await db.execute(
        select(func.count())
        .select_from(GroupLeader)
        .where(
            GroupLeader.group_id == group_id,
            GroupLeader.is_deleted == False  # noqa: E712
        )
    )
    if active_leaders_count.scalar_one() <= 1:
        raise BadRequestException(
            "Cannot remove the only leader of a group. Assign another leader first."
        )

    leader.is_deleted = True
    db.add(leader)
    await db.flush()

    group = await _get_group_full(db, group_id)
    return await _build_group_response(db, group)


# ---------------------------------------------------------------------------
# Assign member to group
# ---------------------------------------------------------------------------

async def assign_member(
        db: AsyncSession,
        group_id: uuid.UUID,
        data: AssignMemberRequest,
        assigned_by: User,
) -> GroupResponse:
    """
    Assign an existing church member to a group.
    Only super_admin, admin, and pastor can do this.
    The member must not already belong to another group.
    """
    if not _can_assign_members(assigned_by):
        raise ForbiddenException("Only admins and pastors can assign members to groups")

    group = await _get_group_full(db, group_id)
    if not group:
        raise NotFoundException("Group not found")

    if not group.is_active:
        raise BadRequestException("Cannot assign members to an inactive group")

    # Confirm member exists
    member_result = await db.execute(
        select(Member).where(
            Member.id == data.member_id,
            Member.is_deleted == False  # noqa: E712
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise NotFoundException("Member not found")

    # Check member isn't already in a group
    existing_membership = await db.execute(
        select(GroupMembership).where(
            GroupMembership.member_id == data.member_id,
            GroupMembership.is_deleted == False  # noqa: E712
        )
    )
    existing = existing_membership.scalar_one_or_none()
    if existing:
        if existing.group_id == group_id:
            raise ConflictException("This member is already in this group")
        raise ConflictException(
            "This member already belongs to another group. Use the transfer endpoint instead."
        )

    new_membership = GroupMembership(
        group_id=group_id,
        member_id=data.member_id,
        assigned_by_id=assigned_by.id,
    )
    db.add(new_membership)
    await db.flush()

    group = await _get_group_full(db, group_id)
    return await _build_group_response(db, group)





