import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

try:
    from src.database.base import Base, TimestampMixin
except ImportError:
    from database.base import Base, TimestampMixin


class KDGIndexJob(Base, TimestampMixin):
    """SQLAlchemy model tracking two-phase Knowledge Discovery Graph indexing jobs."""
    __tablename__ = "kdg_index_jobs"

    job_id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    phase: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="structural",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
