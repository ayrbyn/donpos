import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TransactionItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=10000)


class TransactionCreate(BaseModel):
    id: uuid.UUID | None = None
    items: list[TransactionItemIn] = Field(min_length=1)
    discount: int = Field(default=0, ge=0)
    payment_method: Literal["cash"] = "cash"
    paid_amount: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=255)


class TransactionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID
    product_name: str
    price: int
    quantity: int
    subtotal: int


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    cashier_id: uuid.UUID
    subtotal: int
    discount: int
    total: int
    payment_method: str
    paid_amount: int
    change_amount: int
    status: str
    note: str | None
    created_at: datetime
    items: list[TransactionItemOut]