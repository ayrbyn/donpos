import csv
import io
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_outlet, require_roles
from app.db.session import get_db
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User
from app.models.outlet import Outlet
from app.schemas.report import (
    CashierSales,
    DailySales,
    ProductSales,
    SalesMetrics,
    SalesReport,
)

router = APIRouter(prefix="/reports", tags=["reports"])
WIB = timezone(timedelta(hours=7))
UTC = timezone.utc


def report_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from tidak boleh setelah date_to")
    start = datetime.combine(date_from, time.min, tzinfo=WIB).astimezone(UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=WIB).astimezone(UTC)
    return start, end


def metrics_columns():
    return (
        func.count(case((Transaction.status == "completed", 1))).label("completed_transactions"),
        func.count(case((Transaction.status == "voided", 1))).label("voided_transactions"),
        func.coalesce(func.sum(case((Transaction.status == "completed", Transaction.subtotal), else_=0)), 0).label("subtotal"),
        func.coalesce(func.sum(case((Transaction.status == "completed", Transaction.discount), else_=0)), 0).label("discount"),
        func.coalesce(func.sum(case((Transaction.status == "completed", Transaction.tax_amount), else_=0)), 0).label("tax_amount"),
        func.coalesce(func.sum(case((Transaction.status == "completed", Transaction.total), else_=0)), 0).label("total_sales"),
    )


def safe_spreadsheet_text(value: str) -> str:
    if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


async def build_report(
    db: AsyncSession, date_from: date, date_to: date, outlet_id: uuid.UUID
) -> SalesReport:
    start, end = report_bounds(date_from, date_to)
    summary_result = await db.execute(
        select(*metrics_columns()).where(
            Transaction.outlet_id == outlet_id,
            Transaction.created_at >= start, Transaction.created_at < end
        )
    )
    summary_row = summary_result.mappings().one()
    summary = SalesMetrics(**summary_row)

    local_day = cast(func.timezone("Asia/Jakarta", Transaction.created_at), Date)
    daily_result = await db.execute(
        select(local_day.label("date"), *metrics_columns())
        .where(Transaction.outlet_id == outlet_id, Transaction.created_at >= start, Transaction.created_at < end)
        .group_by(local_day)
        .order_by(local_day)
    )
    daily = [DailySales(**row) for row in daily_result.mappings().all()]

    item_result = await db.execute(
        select(
            TransactionItem.product_name.label("product_name"),
            func.coalesce(func.sum(TransactionItem.quantity), 0).label("quantity_sold"),
            func.coalesce(
                func.sum(TransactionItem.subtotal - TransactionItem.discount), 0
            ).label("total_sales"),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(
            Transaction.created_at >= start,
            Transaction.created_at < end,
            Transaction.outlet_id == outlet_id,
            Transaction.status == "completed",
        )
        .group_by(TransactionItem.product_name)
        .order_by(
            func.sum(TransactionItem.subtotal - TransactionItem.discount).desc(),
            TransactionItem.product_name,
        )
    )
    products = [ProductSales(**row) for row in item_result.mappings().all()]

    cashier_result = await db.execute(
        select(User.id.label("cashier_id"), User.full_name.label("cashier_name"), *metrics_columns())
        .join(Transaction, Transaction.cashier_id == User.id)
        .where(Transaction.outlet_id == outlet_id, Transaction.created_at >= start, Transaction.created_at < end)
        .group_by(User.id, User.full_name)
        .order_by(func.sum(case((Transaction.status == "completed", Transaction.total), else_=0)).desc(), User.full_name)
    )
    cashiers = [CashierSales(**row) for row in cashier_result.mappings().all()]

    return SalesReport(
        date_from=date_from,
        date_to=date_to,
        summary=summary,
        daily=daily,
        products=products,
        cashiers=cashiers,
    )


async def get_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
) -> SalesReport:
    return await build_report(db, date_from, date_to, outlet.id)


@router.get("/sales", response_model=SalesReport)
async def sales_report(report: SalesReport = Depends(get_report)):
    return report


@router.get("/sales/export.csv")
async def export_sales_report(report: SalesReport = Depends(get_report)):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["section", "date_from", "date_to", "name", "cashier_id", "completed_transactions", "voided_transactions", "subtotal", "discount", "tax_amount", "total_sales", "quantity_sold"])
    writer.writerow(["summary", report.date_from.isoformat(), report.date_to.isoformat(), "", "", report.summary.completed_transactions, report.summary.voided_transactions, report.summary.subtotal, report.summary.discount, report.summary.tax_amount, report.summary.total_sales, ""])
    for row in report.daily:
        writer.writerow(["daily", row.date.isoformat(), "", "", "", row.completed_transactions, row.voided_transactions, row.subtotal, row.discount, row.tax_amount, row.total_sales, ""])
    for row in report.products:
        writer.writerow(["product", "", "", safe_spreadsheet_text(row.product_name), "", "", "", "", "", "", row.total_sales, row.quantity_sold])
    for row in report.cashiers:
        writer.writerow(["cashier", "", "", safe_spreadsheet_text(row.cashier_name), row.cashier_id, row.completed_transactions, row.voided_transactions, row.subtotal, row.discount, row.tax_amount, row.total_sales, ""])

    content = "\ufeff" + output.getvalue()
    filename = f"laporan-penjualan-{report.date_from.isoformat()}-sampai-{report.date_to.isoformat()}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
