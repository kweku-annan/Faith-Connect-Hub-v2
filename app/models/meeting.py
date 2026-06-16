import uuid
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import Boolean, Text, ForeignKey, Date, UniqueConstraint, Enum as SAEnum, Time
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, date, time
from app.db.base import Base
import enum


class MeetingType(str, enum.Enum):
    general = "General"
    fellowship_meeting = "fellowship_meeting"
    # group_meeting = "group_meeting"


class MeetingSession(Base):
    __tablename__ = "meeting_session"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # NULL group_id = church-wide service/meeting
    # Non-null group_id = fellowship meeting for that group
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("group.id", ondelete="RESTRICT"), nullable=True
    )
    meeting_type: Mapped[MeetingType] = mapped_column(SAEnum(MeetingType), nullable=False)
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False)
    meeting_time: Mapped[time] = mapped_column(Time, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Relationships
    group: Mapped["Group | None"] = relationship(  # noqa: F821
        "Group", back_populates="meeting_sessions"
    )
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(  # noqa
        "AttendanceRecord", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # No duplicate sessions per group per day per type
        UniqueConstraint(
            "group_id", "meeting_date", "meeting_type",
            name="uq_meeting_sessions_group_date_type"
        ),

    )

    def __repr__(self) -> str:
        return f"<MeetingSession {self.meeting_type} {self.meeting_date}>"

