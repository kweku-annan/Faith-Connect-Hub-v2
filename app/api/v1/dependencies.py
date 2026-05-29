from fastapi import Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError
from app.db.session import get_db
from app.core.security import decode_token
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.models.user import RoleName

bearer_scheme = HTTPBearer()

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        db: AsyncSession = Depends(get_db)
):
    """Decode JWT and return the current authenticated user."""
    from sqlalchemy import select
    from app.models.user import User

    try:
        payload = decode_token(credentials.credentials)
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if user_id is None or token_type != "access":
            raise UnauthorizedException()
    except JWTError:
        raise UnauthorizedException(detail="Invalid or expired token")

    result = await db.execute(
        select(User)
        .where(User.id == user_id, User.is_deleted == False, User.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise UnauthorizedException(detail="User account not found or deactivated")

    return user

def require_roles(*roles: RoleName):
    """Dependency factory - enforces that current user has at least one of the given roles"""
    async def _check(current_user=Depends(get_current_user)):
        user_role_name = [r.role for r in current_user.roles]
        if not any(role in user_role_name for role in roles):
            raise ForbiddenException()
        return current_user
    return _check

