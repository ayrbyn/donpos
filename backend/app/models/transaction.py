import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModel


class Transaction(BaseModel):
    __tablename__ = "transactions"

    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    outlet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outlets.id"), index=True
    )
    cashier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    subtotal: Mapped[int] = mapped_column(BigInteger)
    discount: Mapped[int] = mapped_column(BigInteger, default=0)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0")
    )
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    tax_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    total: Mapped[int] = mapped_column(BigInteger)
    payment_method: Mapped[str] = mapped_column(String(20), default="cash")
    paid_amount: Mapped[int] = mapped_column(BigInteger)
    change_amount: Mapped[int] = mapped_column(BigInteger, default=0)
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
    price: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(BigInteger)
    subtotal: Mapped[int] = mapped_column(BigInteger)
    discount: Mapped[int] = mapped_column(BigInteger, default=0)
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0")
    )

    transaction: Mapped["Transaction"] = relationship(back_populates="items")


class InvoiceCounter(Base):
    __tablename__ = "invoice_counters"

    invoice_date: Mapped[date] = mapped_column(Date, primary_key=True)
    outlet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outlets.id"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(Integer, nullable=False)
