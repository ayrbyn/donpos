from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class Tenant(BaseModel):
    __tablename__ = "tenants"
    __table_args__ = (UniqueConstraint("code", name="uq_tenants_code"),)

    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(12), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SignupAttempt(Base):
    """Database-backed global signup throttling across API workers."""

    __tablename__ = "signup_attempts"

    ip_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)

