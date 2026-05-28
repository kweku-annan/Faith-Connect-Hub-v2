import uuid

from dns.btree import Member
from sqlalchemy import String, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from app.db.base import Base
import enum


class RoleName(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    pastor = "pastor"
    leader = "leader"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_login: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    member: Mapped["Member"] = relationship(  # noqa: F821
        "Member", back_populates="user_account"
    )
    roles: Mapped[list["UserRole"]] = relationship(
        "UserRole", back_populates="users", cascade="all, delete-orphan"
    )
    invited_by: Mapped["User | None"] = relationship(
        "User", remote_side="User.id", foreign_keys=[invited_by_id]
    )
    group_leadership: Mapped["GroupLeader"] = relationship(  # noqa: F821
        "GroupLeader", back_populates="user", uselist=False
    )

    def has_role(self, role: RoleName) -> bool:
        return any(r.role == role for r in self.roles)

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[RoleName] = mapped_column(SAEnum(RoleName), nullable=False)
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="roles", foreign_keys=[user_id])

    __table_args__ = (
        # A user cannot hold the same role twice
        __import__("sqlalchemy").UniqueContraint("user_id", "role", name="uq_user_roles_user_id_role")
    )

    def __repr__(self) -> str:
        return f"<UserRole {self.user_id} - {self.role}>"