import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.member import Member
from app.models.group import Group, GroupLeader, GroupMembership
from app.models.user import User, RoleName
from app.schemas.member import MemberCreate, MemberUpdate, MemberTransfer
from app.core.exceptions import (
    NotFoundException,
    BadRequestException,
    ForbiddenException,
    ConflictException
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _can_manage_members(user: User) -> bool:
    """Leaders, pastors, admins and super_admin can add/update members"""
    roles = [r.role for r in user.roles]
    return any(r in roles for r in [
        RoleName.super_admin, RoleName.admin, RoleName.pastor, RoleName.leader
    ])

def _can_assign_groups(user: User) -> bool:
    """Only super_admin, admin and pastor can assign members to groups"""
    roles = [r.role for r in user.roles]
    return any(r in roles for r in [
        RoleName.super_admin, RoleName.admin, RoleName.pastor
    ])

def _can_transfer(user: User) -> bool:
    """Only super_admin and admin can transfer members between groups"""
    roles = [r.role for r in user.roles]
    return any(r in roles for r in [
        RoleName.super_admin, RoleName.admin
    ])


async def _get_member_with_group(db: AsyncSession, member_id: uuid.UUID) -> Member | None:
    """Fetch a member and eagerly load their current group membership"""
    result = await db.execute(
        select(Member)
        .options(
            selectinload(Member.group_membership).selectinload(GroupMembership.group)
        )
        .where(Member.id == member_id, Member.is_deleted == False)  # noqa: E712
    )
    return result.scalar_one_or_none()

# ----------------------------------------------------------------------------
# Create
# ----------------------------------------------------------------------------
async def create_member(
        db: AsyncSession,
        data: MemberCreate,
        added_by: User,
) -> Member:
    """
    Register a new member in the church register.
    Any leader, pastor, or admin can add members.
    Duplicate email check is enforced if email is provided.
    """
    if not _can_manage_members(added_by):
        raise ForbiddenException("You do not have permission to add members")

    # Check for duplicate email
    if data.email:
        existing = await db.execute(
            select(Member).where(
                Member.email == str(data.email),
                Member.is_deleted == False  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictException("A member with this email already exists")

    # Check for duplicate phone
    if data.phone:
        existing_phone = await db.execute(
            select(Member).where(
                Member.phone == data.phone,
                Member.is_deleted == False
            )
        )
        if existing_phone.scalar_one_or_none():
            raise ConflictException("A member with this phone number already exists")

    member = Member(
        **data.model_dump(exclude_none=False),
        added_by_id=added_by.id
    )
    db.add(member)
    await db.flush()
    return await _get_member_with_group(db, member.id)


# -----------------------------------------------------------------
# Read
# -----------------------------------------------------------------

async def get_member(db: AsyncSession, member_id: uuid.UUID, requesting_user: User) -> Member:
    """
    Fetch a single member by ID.
    Leaders can only view members in their own group.
    Pastors, admins, super_admin can view any member.
    """
    member = await _get_member_with_group(db, member_id)
    if not member:
        raise NotFoundException("Member not found")

    # Leaders are restricted to their own group's members
    roles = [r.role for r in requesting_user.roles]
    if RoleName.leader in roles and not any(
        r in roles for r in [RoleName.super_admin, RoleName.admin, RoleName.pastor]
    ):
        await _assert_leader_owns_member(db, requesting_user, member)

    return member

async def list_members(
        db: AsyncSession,
        requesting_user: User,
        group_id: uuid.UUID | None = None,
        status: str | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 20,
) -> tuple[list[Member], int]:
    """
    List members with optional filters.
    Leaders are automatically scoped to their own group.
    Returns (members, total_count).
    """
    roles = [r.role for r in requesting_user.roles]
    is_leader_only = (
        RoleName.leader in roles and not any(r in roles for r in [RoleName.super_admin, RoleName.admin, RoleName.pastor])
    )
    query = (
        select(Member)
        .options(
            selectinload(Member.group_membership).selectinload(GroupMembership.group)
        )
        .where(Member.is_deleted == False)  # noqa: E712
    )

    # Scope leaders to their own group automatically
    if is_leader_only:
        leader_group = await _get_leader_group_id(db, requesting_user)
        if leader_group:
            query = query.join(GroupMembership).where(
                GroupMembership.group_id == leader_group,
                GroupMembership.is_deleted == False
            )

    # Optional filters available to admins/pastors
    elif group_id:
        query = query.join(GroupMembership).where(
            GroupMembership.group_id == group_id,
            GroupMembership.is_deleted == False  # noqa: E712
        )

    if status:
        query = query.where(Member.status == status)

    if search:
        search_term = f"%{search.lower()}%"
        query = query.where(
            func.lower(Member.first_name).like(search_term) |
            func.lower(Member.last_name).like(search_term) |
            func.lower(Member.email).like(search_term)
        )

    # Total count (same filters, no pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Paginated results
    result = await db.execute(
        query.order_by(Member.last_name, Member.first_name)
        .offset(offset)
        .limit(limit)
    )
    members = result.scalars().all()

    return list(members), total


# --------------------------------------------------------------
# Update
# --------------------------------------------------------------
async def update_member(db: AsyncSession, member_id: uuid.UUID, data: MemberUpdate, updated_by: User) -> Member:
    """
    Update a member's details.
    Leaders can only update members in their own group.
    """
    if not _can_manage_members(updated_by):
        raise   ForbiddenException("You do not have permission to update members")

    member = await _get_member_with_group(db, member_id)
    if not member:
        raise NotFoundException("Member not found")

    roles = [r.role for r in updated_by.roles]
    if RoleName.leader in roles and not any(
        r in roles for r in [RoleName.super_admin, RoleName.admin, RoleName.pastor]
    ):
        await _assert_leader_owns_member(db, updated_by, member)

    # Check for duplicate email if email is being updated
    if data.email and str(data.email) != member.email:
        existing = await db.execute(
            select(Member).where(
                Member.email == str(data.email),
                Member.is_deleted == False,
                Member.id != member_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictException("A member with this email already exists")

    # Check phone uniqueness if being changed
    if data.phone and data.phone != member.phone:
        existing_phone = await db.execute(
            select(Member).where(
                Member.phone == data.phone,
                Member.is_deleted == False,
                Member.id != member_id,
            )
        )
        if existing_phone.scalar_one_or_none():
            raise ConflictException("A member with this phone number already exists")

    # Apply only the fields that were explicitly provided
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(member, field, value)

    db.add(member)
    await db.flush()

    return await _get_member_with_group(db, member.id)


# ----------------------------------------------------------
# Soft delete
# ----------------------------------------------------------

async def delete_member(db: AsyncSession, member_id: uuid.UUID, deleted_by: User) -> None:
    """
    Soft-delete a member. Only super_admin and admin can do this. Also, soft-deletes their group
    membership. Blocks deletion if the member has an active user account.
    """
    if not _can_transfer(deleted_by):
        raise ForbiddenException("You do not have permission to delete members")

    member = await _get_member_with_group(db, member_id)
    if not member:
        raise NotFoundException("Member not found")

    # Block if member has a user account - deactivate the account first
    user_check = await db.execute(
        select(User).where(
            User.member_id == member.id,
            User.is_deleted == False,
        )
    )
    if user_check.scalar_one_or_none():
        raise BadRequestException("Cannot delete member with an active user account. Deactivate their user account first.")

    # Soft-delete their group membership if any
    if member.group_membership and not member.group_membership.is_deleted:
        member.group_membership.is_deleted = True
        db.add(member.group_membership)

    member.is_deleted = True
    db.add(member)
    await db.flush()


# ------------------------------------------------------------
# Transfer
# ------------------------------------------------------------
async def transfer_member(db: AsyncSession, member_id: uuid.UUID, data: MemberTransfer, transferred_by: User) -> Member:
    """
    Transfer a member from their current group to a new group. Only super_admin and admin can transfer members.
    The old membership is soft-deleted (history preserved). A new membership is created in the target group.
    """
    if not _can_transfer(transferred_by):
        raise ForbiddenException("You do not have permission to transfer members")

    member = await _get_member_with_group(db, member_id)
    if not member:
        raise NotFoundException("Member not found")

    # Confirm target group exists.
    group_result = await db.execute(
        select(Group).where(
            Group.id == data.target_group_id,
            Group.is_deleted == False,
            Group.is_active == True
        )
    )
    target_group = group_result.scalar_one_or_none()
    if not target_group:
        raise NotFoundException("Target group not found or is inactive")

    # Check member isn't already in that group
    current = member.group_membership
    if current and not current.is_deleted and current.group_id == data.target_group_id:
        raise BadRequestException("Member is already in the target group")

    # Soft-delete current membership (preserves transfer history)
    if current and not current.is_deleted:
        current.is_deleted = True
        db.add(current)

    # Create new membership in target group
    new_membership = GroupMembership(
        group_id=data.target_group_id,
        member_id=member_id,
        assigned_by_id=transferred_by.id,
    )
    db.add(new_membership)
    await db.flush()

    return await _get_member_with_group(db, member_id)


# ----------------------------------------------------------
# Private guards
# ----------------------------------------------------------

async def _assert_leader_owns_member(db: AsyncSession, leader: User, member: Member) -> None:
    """
    Raise ForbiddenException if the leader's group does not contain this member.
    """
    leader_group_id = await _get_leader_group_id(db, leader)
    if not leader_group_id:
        raise ForbiddenException("You are not assigned to any group.")
    if (
        not member.group_membership or
        member.group_membership.is_deleted or
        member.group_membership.id != leader_group_id
    ):
        raise ForbiddenException("This member does not belong to your group.")


async def _get_leader_group_id(db: AsyncSession, user: User) -> uuid.UUID | None:
        """Return the group_id the user leads, or None if they lead no group."""
        result = await db.execute(
            select(GroupLeader.group_id).where(
                GroupLeader.user_id == user.id,
                GroupLeader.is_deleted == False,
            )
        )
        return result.scalar_one_or_none()
