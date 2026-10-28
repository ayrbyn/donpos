import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    sku: str | None = Field(default=None, max_length=50)
    barcode: str | None = Field(default=None, max_length=50)
    price: int = Field(ge=0)
    stock: int = Field(default=0, ge=0)
    category_id: uuid.UUID | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    sku: str | None = Field(default=None, max_length=50)
    barcode: str | None = Field(default=None, max_length=50)
    price: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    category_id: uuid.UUID | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sku: str | None
    barcode: str | None
    price: int
    stock: int
    is_active: bool
    category_id: uuid.UUID | None

class StockAdjust(BaseModel):
    change: int = Field(description="Positif untuk tambah stok, negatif untuk kurangi")
    reason: Literal["restock", "correction", "damaged", "return"]
    note: str | None = Field(default=None, max_length=255)


class StockMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    change: int
    stock_after: int
    reason: str
    note: str | None
    reference_id: uuid.UUID | None
    user_id: uuid.UUID | None
    created_at: datetime