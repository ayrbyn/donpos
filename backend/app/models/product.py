import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class Product(BaseModel):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("outlet_id", "sku", name="uq_products_outlet_sku"),
        UniqueConstraint("outlet_id", "barcode", name="uq_products_outlet_barcode"),
    )

    name: Mapped[str] = mapped_column(String(150), index=True)
    outlet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outlets.id"), index=True
    )
    sku: Mapped[str | None] = mapped_column(String(50), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    price: Mapped[int] = mapped_column(BigInteger)
    stock: Mapped[int] = mapped_column(BigInteger, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True
    )
