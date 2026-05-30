import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from jose import JWTError, jwt

from app.models.user import User, UserRole, RoleName
from app.models.member import Member
from app.schemas.user import InviteRequest, RegisterRequest, LoginRequest
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    UnauthorizedException,
    ForbiddenException
)
from app.config import settings


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------
INVITE_TOKEN_EXPIRE_HOURS = 48
INVITE_TOKEN_TYPE = "invite"

def _create_invite_token(email: str, member_id: str, roles: list[str]) -> str:
    """
    A short-lived signed JWT used as the invite link token.
    Carries the email, member_id, and intended roles so we don't need a separate DB table for pending invites.
    """
    expire = datetime.utcnow() + timedelta(hours=INVITE_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": email,
        "member_id": str(member_id),
        "roles": roles,
        "type": INVITE_TOKEN_TYPE,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

def _decode_invite_token(token: str) -> dict:
    """Decode invite token and validate its type and expiration. Raises BadRequestException otherwise."""
    try:
        payload = decode_token(token)
        if payload.get("type") != INVITE_TOKEN_TYPE:
            raise BadRequestException(detail="Invalid invite token")
        return payload
    except JWTError:
        raise BadRequestException(detail="Invalid token is invalid or has expired")


async def _get_user_with_roles(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Helper to load a user with their roles in one query."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id, User.is_deleted == False)  # noqa: E712
    )
    return result.scalar_one_or_none()


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Fetch a user by email and eagerly load their roles."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.email == email, User.is_deleted == False)  # noqa: 712
    )
    return result.scalar_one_or_none()


# --------------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------------

async def login(db: AsyncSession, data: LoginRequest) -> tuple[User, str, str]:
    """
    Authenticate a user with email and password.
    Returns (user, access_token, refresh_token).
    Raises UnauthorizedException on bad credentials or inactive account.
    """
    user = await _get_user_by_email(db, data.email)

    # Use a constant-time check even when user is None to prevent timing attacks
    # that could reveal whether an email is registered
    dummy_hash = "$2b$12$KIXQ4odummyVh9eZt0pass7E5uJ8m1G6f5s9v1w2x3y4z5a6b7c8d9e"
    password_ok = verify_password(data.password, user.password_hash if user else dummy_hash)

    if not user or not password_ok:
        raise UnauthorizedException(detail="Incorrect email or password")
    if not user.is_active:
        raise UnauthorizedException(detail="User account is deactivated. Contact an adminstrator")

    # Update last login timestamp
    user.last_login = datetime.utcnow()
    db.add(user)

    token_data = {"sub": str(user.id)}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return user, access_token, refresh_token


# ----------------------------------------------------------------------
# Invite
# ----------------------------------------------------------------------

async def invite_user(db: AsyncSession, data: InviteRequest, invited_by: User) -> str:
    """
    Create a signed invite token for a prospective user.
    Returns the invite token (caller is responsible for sending list)

    Rules enforced:
    - The member must exist and not be soft-deleted
    - The member must not already have a user account
    - The email must not already be registered
    - Only admin/super_admin can invite (enforced at endpoint level,
    but double-checked here for safety)
    - super_admin role cannot be assigned via invite
    """
    invited_by_roles = [r.role for r in invited_by.roles]
    if not any(r in invited_by_roles for r in [RoleName.super_admin, RoleName.admin]):
        raise ForbiddenException("Only admins can invite users")

    # Confirm member exists
    member_result = await db.execute(
        select(Member).where(
            Member.id == data.member_id,
            Member.is_deleted == False
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise NotFoundException("Member not found.")

    # Member must not already have a user account
    existing_user_for_member = await db.execute(
        select(User).where(
            User.member_id == data.member_id,
            User.is_deleted == False  # noqa: E712
        )
    )
    if existing_user_for_member.scalar_one_or_none():
        raise ConflictException("This member already has a user account.")

    # Email must not already be registered
    existing_user_by_email = await _get_user_by_email(db, data.email)
    if existing_user_by_email:
        raise ConflictException("A user with this email already exists.")

    # Member email should match invite email
    if member.email and member.email.lower() != str(data.email).lower():
        raise BadRequestException(
            "Invite email does not match the email on the member's record"
        )

    invite_token = _create_invite_token(
        email=str(data.email),
        member_id=str(data.member_id),
        roles=[r.value for r in data.roles]
    )

    return invite_token

# -------------------------------------------------------------------
# Register (complete an invite)
# -------------------------------------------------------------------
async def register_user(db: AsyncSession, data: RegisterRequest, invited_by: User) -> User | None:
    """
    Complete registration using a valid invite token.
    Creates the User record and assigns the roles encoded in the token.
    Returns the newly created user.
    """
    payload = _decode_invite_token(data.invite_token)

    email: str = payload["sub"]
    member_id: uuid.UUID = uuid.UUID(payload["member_id"])
    roles: list[str] = payload["roles"]

    # Re-check nothing has changed since the invite was sent
    existing = await _get_user_by_email(db, email)
    if existing:
        raise ConflictException("This invite has already been used")

    member_result = await db.execute(
        select(Member).where(
            Member.id == member_id,
            Member.is_deleted == False  # noqa E712
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise NotFoundException("The member linked to this invite no longer exists")

    # Create the user
    new_user = User(
        member_id=member_id,
        email=email,
        password_hash=hash_password(data.password),
        is_active=True,
        invited_by_id=invited_by.id,
    )
    db.add(new_user)
    await db.flush()  # get new_user.id before inserting roles

    # Assign roles from the invite token
    for role_value in roles:
        db.add(UserRole(
            user_id=new_user.id,
            role=RoleName(role_value),
            assigned_by_id=invited_by.id
        ))

    await db.flush()

    # Return user with roles loaded
    return await _get_user_with_roles(db, new_user.id)

# -------------------------------------------------------------
# Refresh token
# -------------------------------------------------------------

async def refresh_access_token(db: AsyncSession, refresh_token: str) -> str:
    """
    Validate a refresh token and return a new access token.
    Raises UnauthorizedException if the token is invalid or expired.
    """
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid token type")
        user_id: str = payload.get("sub")
    except JWTError:
        raise UnauthorizedException("Refresh token is invalid or has expired")

    user = await _get_user_with_roles(db, uuid.UUID(user_id))
    if not user or not user.is_active:
        raise UnauthorizedException("User account not found or deactivated")

    return create_access_token({"sub": str(user.id)})

# -----------------------------------------------------------------------------
# Get current user (used by /auth/me)
# -----------------------------------------------------------------------------

async def get_me(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Return the current user with roles. Raises NotFoundException if not found."""
    user = await _get_user_with_roles(db, user_id)
    if not user:
        raise NotFoundException("User not found.")
    return user

