import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Transaction(BaseModel):
    __tablename__ = "transactions"

    invoice_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    cashier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    subtotal: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)
    payment_method: Mapped[str] = mapped_column(String(20), default="cash")
    paid_amount: Mapped[int] = mapped_column(Integer)
    change_amount: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    items: Mapped[list["TransactionItem"]] = relationship(
        back_populates="transaction"
    )


class TransactionItem(BaseModel):
    __tablename__ = "transaction_items"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(150))
    price: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    subtotal: Mapped[int] = mapped_column(Integer)

    transaction: Mapped["Transaction"] = relationship(back_populates="items")