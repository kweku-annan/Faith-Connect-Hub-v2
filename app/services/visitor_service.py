import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.visitor import Visitor
from app.models.member import Member
from app.models.user import User, RoleName
from app.schemas.visitor import VisitorCreate, VisitorUpdate
from app.core.exceptions import (
    ForbiddenException,
    NotFoundException,
)


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _can_manage_visitors(user: User) -> bool:
    """All authenticated roles can log visitors"""
    return True

def _can_delete_visitor(user: User) -> bool:
    """Only super_admin and admin can delete visitor records"""
    roles = [r.role for r in user.roles]
    return any(r in roles for r in [RoleName.super_admin, RoleName.admin])


async def _get_visitor_with_inviter(
        db: AsyncSession,
        visitor_id: uuid.UUID,
) -> Visitor | None:
    """Fetch a visitor and eagerly load the member who invited them."""
    result = await db.execute(
        select(Visitor)
        .options(selectinload(Visitor.invited_by))
        .where(Visitor.id == visitor_id, Visitor.is_deleted == False)
    )
    return  result.scalar_one_or_none()


# ----------------------------------------------------------
# Create
# ----------------------------------------------------------

async def create_visitor(
        db: AsyncSession,
        data: VisitorCreate,
        created_by: User,
) -> Visitor:
    """
    Log a new visitor record.
    Any authenticated user can record a visitor.
    If invited_by_id is provided, confirm that member exists.
    """
    if data.invited_by_member_id:
        member_result = await db.execute(
            select(Member).where(
                Member.id == data.invited_by_member_id,
                Member.is_deleted == False  # noqa: E712
            )
        )
        if not member_result.scalar_one_or_none():
            raise NotFoundException("The member who invited this visitor was not found.")

    visitor = Visitor(
        **data.model_dump(exclude_none=False),
        created_by_id=created_by.id,
    )
    db.add(visitor)
    await db.flush()

    return await _get_visitor_with_inviter(db, visitor.id)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_visitor(
        db: AsyncSession,
        visitor_id: uuid.UUID,
) -> Visitor:
    """Fetch a single visitor by ID."""
    visitor = await _get_visitor_with_inviter(db, visitor_id)
    if not visitor:
        raise NotFoundException("Visitor not found")
    return visitor


async def list_visitors(
        db: AsyncSession,
        search: str | None = None,
        invited_by_member_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
) -> tuple[list[Visitor], int]:
    """
    List visitors with optional filters.
    Search matches on first name, last name, or phone.
    Returns (visitors, total_count).
    """
    query = (
        select(Visitor)
        .options(selectinload(Visitor.invited_by))
        .where(Visitor.is_deleted == False)  # noqa: E712
    )
    if invited_by_member_id:
        query = query.where(Visitor.invited_by_member_id == invited_by_member_id)

    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            func.lower(Visitor.first_name).like(term) |
            func.lower(Visitor.last_name).like(term) |
            func.lower(Visitor.phone).like(term)
        )

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    result = await db.execute(
        query.order_by(Visitor.visit_date.desc(), Visitor.last_name)
        .offset(offset)
        .limit(limit)
    )
    visitors = result.scalars().all()

    return list(visitors), total



# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


async def update_visitor(
        db: AsyncSession,
        visitor_id: uuid.UUID,
        data: VisitorUpdate,
        updated_by: User,
) -> Visitor:
    """
    Update a visitor's details.
    Any authenticated user can update visitor records.
    """
    visitor = await _get_visitor_with_inviter(db, visitor_id)
    if not visitor:
        raise NotFoundException("Visitor not found")

    # Confirm new inviting member exists if being changed
    if data.invited_by_member_id:
        member_result = await db.execute(
            select(Member).where(
                Member.id == data.invited_by_member_id,
                Member.is_deleted == False  # noqa: E712
            )
        )
        if not member_result.scalar_one_or_none():
            raise NotFoundException("The member who invited this visitor was not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(visitor, field, value)

    db.add(visitor)
    await db.flush()

    return await _get_visitor_with_inviter(db, visitor.id)



# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------

async def delete_visitor(
        db: AsyncSession,
        visitor_id: uuid.UUID,
        deleted_by: User,
) -> None:
    """Soft-delete a visitor record. Only admins can do this."""
    if not _can_delete_visitor(deleted_by):
        raise ForbiddenException("Only admins can delete visitor records")

    visitor = await _get_visitor_with_inviter(db, visitor_id)
    if not visitor:
        raise NotFoundException("Visitor not found")

    visitor.is_deleted = True
    db.add(visitor)
    await db.flush()

