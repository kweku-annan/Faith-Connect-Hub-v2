import uuid
from sqlalchemy import Text, ForeignKey, UniqueConstraint, CheckConstraint, Enum as SAEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from app.db.base import Base
import enum


class AttendanceStatus(enum.Enum):
    present = "present"
    absent = "absent"
    excused = "excused"
    late = "late"


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meeting_sessions.id", ondelete="CASCADE"), nullable=False
    )
    # Exactly one of member_id or visitor_id must be set (enforced by CHECK constraint)
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id", ondelete="CASCADE"), nullable=True
    )
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visitors.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[AttendanceStatus] = mapped_column(SAEnum(AttendanceStatus), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    marked_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    marked_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    session: Mapped["MeetingSession"] = relationship(  # noqa: F821
       "MeetingSession", back_populates="attendance_records"
    )
    member: Mapped["Memeber | None"] = relationship(  # noqa: F821
        "Member", back_populates="attendance_records"
    )
    visitor: Mapped["Visitor | None"] = relationship(  # noqa: F821
        "Visitor", back_populates="attendance_records"
    )

    __table_args__ = (
        # Only one record per member per session
        UniqueConstraint(
            "session_id", "member_id",
            name="uq_attendance_session_member"
        ),
        # Only one record per visitor per session
        UniqueConstraint(
            "session_id", "visitor_id",
            name="uq_attendance_session_visitor"
        ),
        # Must be a member OR a visitor, never both, never neither
        CheckConstraint(
            "(member_id IS NOT NULL AND visitor_id IS NULL) OR"
            "(member_id IS NULL AND visitor_id IS NOT NULL)",
            name="ck_attendance_attendee_visitor"
        )
    )

    def __repr__(self) -> str:
        attendee = self.member_id or self.visitor_id
        return f"<AttendanceRecord session={self.session_id} attendee={attendee}>"