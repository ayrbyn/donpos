import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class Category(BaseModel):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("outlet_id", "name", name="uq_categories_outlet_name"),
    )

    outlet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outlets.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
