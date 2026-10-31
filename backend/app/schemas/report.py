from datetime import date
import uuid

from pydantic import BaseModel, ConfigDict


class SalesMetrics(BaseModel):
    completed_transactions: int
    voided_transactions: int
    subtotal: int
    discount: int
    tax_amount: int
    total_sales: int


class DailySales(SalesMetrics):
    date: date


class ProductSales(BaseModel):
    product_name: str
    quantity_sold: int
    total_sales: int


class CashierSales(SalesMetrics):
    model_config = ConfigDict(from_attributes=True)

    cashier_id: uuid.UUID
    cashier_name: str


class SalesReport(BaseModel):
    date_from: date
    date_to: date
    summary: SalesMetrics
    daily: list[DailySales]
    products: list[ProductSales]
    cashiers: list[CashierSales]
