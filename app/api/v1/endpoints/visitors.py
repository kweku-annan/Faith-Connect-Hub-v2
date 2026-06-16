from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.schemas.visitor import VisitorCreate, VisitorUpdate, VisitorResponse
from app.services import visitor_service
from app.api.v1.dependencies import get_current_user, require_roles
from app.models.user import RoleName, User
from app.utils.pagination import PaginationParams, PaginatedResponse

router = APIRouter()


@router.post(
    "/",
    response_model=VisitorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a new visitor",
)
async def create_visitor(
    data: VisitorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record a new visitor to the church.

    - `visit_date` defaults to today if not provided.
    - `invited_by_member_id` links the visitor to the church member who brought them.

    **Requires:** any authenticated role.
    """
    return await visitor_service.create_visitor(db, data, current_user)


@router.get(
    "/",
    response_model=PaginatedResponse[VisitorResponse],
    summary="List all visitors",
)
async def list_visitors(
    search: str | None = Query(None, description="Search by name or phone"),
    invited_by_member_id: UUID | None = Query(
        None, description="Filter by the member who invited the visitor"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a paginated list of visitors, ordered by most recent visit first.

    **Requires:** any authenticated role.
    """
    params = PaginationParams(page=page, page_size=page_size)
    visitors, total = await visitor_service.list_visitors(
        db,
        search=search,
        invited_by_member_id=invited_by_member_id,
        offset=params.offset,
        limit=params.page_size,
    )
    return PaginatedResponse.create(items=visitors, total=total, params=params)


@router.get(
    "/{visitor_id}",
    response_model=VisitorResponse,
    summary="Get a visitor by ID",
)
async def get_visitor(
    visitor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a single visitor's full record.

    **Requires:** any authenticated role.
    """
    return await visitor_service.get_visitor(db, visitor_id)


@router.patch(
    "/{visitor_id}",
    response_model=VisitorResponse,
    summary="Update a visitor record",
)
async def update_visitor(
    visitor_id: UUID,
    data: VisitorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Partially update a visitor's details. Only provided fields are changed.

    **Requires:** any authenticated role.
    """
    return await visitor_service.update_visitor(db, visitor_id, data, current_user)


@router.delete(
    "/{visitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a visitor record",
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))],
)
async def delete_visitor(
    visitor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Soft-delete a visitor record.

    **Requires:** `super_admin` or `admin` role.
    """
    await visitor_service.delete_visitor(db, visitor_id, current_user)