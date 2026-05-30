from fastapi import APIRouter, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import RoleName, User
from app.schemas.token import Token, AccessToken
from app.schemas.user import LoginRequest, InviteRequest, RegisterRequest, UserResponse
from app.services import user_service
from app.api.v1.dependencies import get_current_user, require_roles

router = APIRouter()


@router.post("/login", response_model=Token, summary="login with email and password")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate with email and password.
    Returns an access token (short-lived) and a refresh token (long-lived)
    """
    user, access_token, refresh_token = await user_service.login(db, data)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post(
    "/invite",
    summary="Invite a member to create a user account",
    status_code=201,
    dependencies=[Depends(require_roles(RoleName.super_admin, RoleName.admin))],
)
async def invite_user(
        data: InviteRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Generate a signed invite token for a member who needs system access.

    - The member must already exist in the members table
    - The invite token expires in 48 hours.
    - super_admin role cannot be assigned via invite.

    **Requires** `super_admin` or `admin` role.
    """
    invite_token = await user_service.invite_user(db, data, current_user)
    return {
        "message": "Invite created successfully. Share this token with the invitee.",
        "invite_token": invite_token,
        "expires_in_hours": 48
    }


@router.post("/register", response_model=UserResponse, status_code=201, summary="Register a new user")
async def register(
        data: RegisterRequest,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Complete account setup using a valid invite token

    The invite token is the one received from `/auth/invite`.
    Password must be at least 8 characters, contain one uppercase letter and one number.
    """
    user = await user_service.register_user(db, data, current_user)
    return user


@router.get("/me", response_model=UserResponse, summary="Get current user's profile")
async def get_me(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Return the currently authenticated user's profile including their roles"""
    return await user_service.get_me(db, current_user.id)

