from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

# Naming convention keeps Alembic migrations clean and consistent.
# Honestly I don't know what this is. I will find out later
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Importing all models here so that Alembic can detect them for autogenerate
from app.models.member import Member
from app.models.user import User, UserRole
from app.models.group import Group, GroupLeader, GroupMembership
from app.models.visitor import Visitor
from app.models.meeting import MeetingSession
from app.models.attendance import AttendanceRecord
