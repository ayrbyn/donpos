import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.constants import MAX_BIGINT


class TransactionItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=10000)
    discount: int | None = Field(default=None, ge=0, le=MAX_BIGINT)
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )

    @model_validator(mode="after")
    def validate_discount_options(self):
        if self.discount is not None and self.discount_percent is not None:
            raise ValueError("Pilih diskon nominal atau persen untuk item")
        return self


class TransactionCreate(BaseModel):
    id: uuid.UUID | None = None
    items: list[TransactionItemIn] = Field(min_length=1)
    discount: int | None = Field(default=None, ge=0, le=MAX_BIGINT)
    discount_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    payment_method: Literal["cash"] = "cash"
    paid_amount: int = Field(ge=0, le=MAX_BIGINT)
    note: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_discount_options(self):
        if self.discount is not None and self.discount_percent is not None:
            raise ValueError("Pilih diskon nominal atau persen untuk transaksi")
        return self


class TransactionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID
    product_name: str
    price: int
    quantity: int
    subtotal: int
    discount: int
    discount_percent: Decimal


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outlet_id: uuid.UUID
    invoice_number: str
    cashier_id: uuid.UUID
    subtotal: int
    discount: int
    discount_percent: Decimal
    tax_percent: Decimal
    tax_amount: int
    total: int
    payment_method: str
    paid_amount: int
    change_amount: int
    status: str
    note: str | None
    created_at: datetime
    items: list[TransactionItemOut]
