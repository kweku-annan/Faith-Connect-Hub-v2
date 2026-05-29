from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    users,
    groups,
    members,
    attendance,
    visitors,
    meetings
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(groups.router, prefix="/groups", tags=["Groups"])
api_router.include_router(members.router, prefix="/members", tags=["Members"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
api_router.include_router(visitors.router, prefix="/visitors", tags=["Visitors"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["Meetings"])
