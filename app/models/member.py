import uuid

from sqlalchemy import String, Boolean, Date, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import date, datetime
from app.db.base import Base
import enum


class Gender(str, enum.Enum):
    male = 'male'
    female = 'female'


class MemberStatus(str, enum.Enum):
    active = 'active'
    inactive = 'inactive'
    transferred = 'transferred'
    deceased = 'deceased'


class Member(Base):
    __tablename__ = 'members'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(15), nullable=False)
    gender: Mapped[Gender] = mapped_column(SAEnum(Gender), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_joined: Mapped[date] = mapped_column(Date, nullable=True)
    status: Mapped[MemberStatus] = mapped_column(
        SAEnum(MemberStatus), default=MemberStatus.active, nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True) # FK set via relationship to avoid circular import
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user_account: Mapped["User"] = relationship(  # noqa: F821
    "User", back_populates="members", uselist=False
    )
    group_membership: Mapped["GroupMembership"] = relationship(  # noqa: F821
    "GroupMembership", back_populates="members", uselist=False
    )
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(  # noqa: F821
        "AttendanceRecord", back_populates="members"
    )

    def __repr__(self) -> str:
        return f"<Member {self.first_name} {self.last_name}>"
