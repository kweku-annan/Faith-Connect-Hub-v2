import uuid
from sqlalchemy import String, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from app.db.base import Base


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    leaders: Mapped[list["GroupLeader"]] = relationship(
        "GroupLeader", back_populates="group", cascade="all, delete-orphan"
    )
    memberships: Mapped[list["GroupMembership"]] = relationship(
        "GroupMembership", back_populates="group", cascade="all, delete-orphan"
    )
    meeting_sessions: Mapped[list["MeetingSession"]] = relationship(  # noqa: F821
        "MeetingSession", back_populates="group"
    )

    def __repr__(self) -> str:
        return f"<Group {self.name}"


class GroupLeader(Base):
    __tablename__ = "group_leaders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assigned_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="leaders")
    user: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="group_leadership", foreign_keys=[user_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "group_id", "user_id", name="uq_group_leaders_group_id_user_id"
        )
    )

    def __repr__(self) -> str:
        return f"<GroupLeader group={self.group_id} user={self.user_id}>"


class GroupMembership(Base):
    __tablename__ = "group_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    assigned_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Relationships
    group: Mapped["Group"] = relationship("Group", back_populates="memberships")
    member: Mapped["Member"] = relationship(  # noqa: F821
        "Member", back_populates="group_membership"
    )

    def __repr__(self) -> str:
        return f"<GroupMembership group={self.group_id} member={self.member_id}>"