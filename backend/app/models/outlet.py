import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class Outlet(BaseModel):
    __tablename__ = "outlets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_outlets_tenant_code"),
        UniqueConstraint("id", "tenant_id", name="uq_outlets_id_tenant_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(8))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserOutlet(Base):
    __tablename__ = "user_outlets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_user_outlets_user_tenant",
        ),
        ForeignKeyConstraint(
            ["outlet_id", "tenant_id"],
            ["outlets.id", "outlets.tenant_id"],
            name="fk_user_outlets_outlet_tenant",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    outlet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
