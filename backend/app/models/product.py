import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class Product(BaseModel):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(150), index=True)
    sku: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    price: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True
    )