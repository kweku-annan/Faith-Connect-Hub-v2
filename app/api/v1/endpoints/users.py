from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import Optional

from app.db.session import get_db
from app.schemas.user import UserResponse, UserUpdateRequest, UserRoleResponse
from app.models.user import User, UserRole, RoleName
from app.api.v1.dependencies import get_current_user, require_roles
from app.core.exceptions import NotFoundException, ConflictException, BadRequestException
from app.utils.pagination import PaginationParams, PaginatedResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_with_roles(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles), selectinload(User.member))
        .where(User.id == user_id, User.is_deleted == False)  # noqa: E712
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# List users
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=PaginatedResponse[UserResponse],
    summary="List all system users",
    dependencies=[Depends(require_roles(
        RoleName.super_admin, RoleName.admin, RoleName.pastor
    ))],
)
async def list_users(
    role: Optional[RoleName] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by email"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve all users who have system access.

    - Optionally filter by `role`, `is_active`, or search by email.
    - Pastors can view the list but cannot modify users.

    **Requires:** `super_admin`, `admin`, or `pastor` role.
    """
    from sqlalchemy import func

    query = (
        select(User)
        .options(selectinload(User.roles), selectinload(User.member))
        .where(User.is_deleted == False)  # noqa: E712
    )

    if is_active is not None:
        query = query.where(User.is_active == is_active)

    if search:
        query = query.where(
            func.lower(User.email).like(f"%{search.lower()}%")
        )

    if role:
        query = query.join(UserRole).where(UserRole.role == role)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    params = PaginationParams(page=page, page_size=page_size)
    result = await db.execute(
        query.order_by(User.created_at.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    users = result.scalars().all()

    return PaginatedResponse.create(items=list(users), total=total, params=params)


# ---------------------------------------------------------------------------
# Get single user
# ---------------------------------------------------------------------------

@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user by ID",
    dependencies=[Depends(require_roles(
        RoleName.super_admin, RoleName.admin, RoleName.pastor
    ))],
)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a single user's profile and roles.

    **Requires:** `super_admin`, `admin`, or `pastor` role.
    """
    user = await _get_user_with_roles(db, user_id)
    if not user:
        raise NotFoundException("User not found")
    return user


# ---------------------------------------------------------------------------
# Activate / deactivate + role management
# ---------------------------------------------------------------------------

@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update a user's active status or roles",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))],
)
async def update_user(
    user_id: UUID,
    data: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update a user's `is_active` flag or reassign their roles.

    - Providing `roles` **replaces** the user's current roles entirely.
    - `super_admin` role cannot be assigned via this endpoint.
    - A user cannot deactivate their own account.

    **Requires:** `super_admin` or `admin` role.
    """
    if user_id == current_user.id and data.is_active is False:
        raise BadRequestException("You cannot deactivate your own account")

    user = await _get_user_with_roles(db, user_id)
    if not user:
        raise NotFoundException("User not found")

    # Update active status
    if data.is_active is not None:
        user.is_active = data.is_active
        db.add(user)

    # Replace roles if provided
    if data.roles is not None:
        if RoleName.super_admin in data.roles:
            raise BadRequestException(
                "super_admin role cannot be assigned via this endpoint"
            )

        # Admin cannot assign/remove roles for another admin or super_admin
        current_user_roles = [r.role for r in current_user.roles]
        target_user_roles = [r.role for r in user.roles]
        if (
            RoleName.admin not in current_user_roles
            and RoleName.super_admin not in current_user_roles
        ):
            raise BadRequestException("Insufficient permissions to change roles")

        if (
            RoleName.super_admin in target_user_roles
            and RoleName.super_admin not in current_user_roles
        ):
            raise BadRequestException(
                "Only super_admin can modify another super_admin's roles"
            )

        # Delete existing roles and insert new ones
        for existing_role in user.roles:
            await db.delete(existing_role)

        await db.flush()

        for role in data.roles:
            db.add(UserRole(
                user_id=user.id,
                role=role,
                assigned_by_id=current_user.id,
            ))

    await db.flush()
    return await _get_user_with_roles(db, user_id)


# ---------------------------------------------------------------------------
# Deactivate (convenience endpoint — explicit intent over PATCH)
# ---------------------------------------------------------------------------

@router.post(
    "/{user_id}/deactivate",
    response_model=UserResponse,
    summary="Deactivate a user account",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))],
)
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deactivate a user account. The user will no longer be able to log in
    but their data and audit trail are preserved.

    A user cannot deactivate their own account.

    **Requires:** `super_admin` or `admin` role.
    """
    if user_id == current_user.id:
        raise BadRequestException("You cannot deactivate your own account")

    user = await _get_user_with_roles(db, user_id)
    if not user:
        raise NotFoundException("User not found")

    if not user.is_active:
        raise BadRequestException("User account is already inactive")

    user.is_active = False
    db.add(user)
    await db.flush()

    return await _get_user_with_roles(db, user_id)


# ---------------------------------------------------------------------------
# Reactivate
# ---------------------------------------------------------------------------

@router.post(
    "/{user_id}/reactivate",
    response_model=UserResponse,
    summary="Reactivate a user account",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))],
)
async def reactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reactivate a previously deactivated user account.

    **Requires:** `super_admin` or `admin` role.
    """
    user = await _get_user_with_roles(db, user_id)
    if not user:
        raise NotFoundException("User not found")

    if user.is_active:
        raise BadRequestException("User account is already active")

    user.is_active = True
    db.add(user)
    await db.flush()

    return await _get_user_with_roles(db, user_id)


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently remove a user's system access",
    dependencies=[Depends(require_roles(RoleName.super_admin))],
)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Soft-delete a user account, permanently removing their system access.
    Their member record and all audit history are preserved.

    This action is irreversible via the API — only a super_admin can
    restore a soft-deleted user directly in the database.

    A super_admin cannot delete their own account.

    **Requires:** `super_admin` role.
    """
    if user_id == current_user.id:
        raise BadRequestException("You cannot delete your own account")

    user = await _get_user_with_roles(db, user_id)
    if not user:
        raise NotFoundException("User not found")

    user.is_deleted = True
    user.is_active = False
    db.add(user)
    await db.flush()