from pydantic import BaseModel


class Token(BaseModel):
    """Returned on successful login or token refresh"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    """Returned on token refresh - only a new access token is issued"""
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Shape of the decoded JWT payload"""
    sub: str    # user UUID
    type: str   # "access" or "refresh"

