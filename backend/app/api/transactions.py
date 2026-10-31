import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_outlet, get_current_user, require_roles
from app.core.config import settings
from app.core.constants import MAX_BIGINT
from app.db.session import get_db
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.transaction import InvoiceCounter, Transaction, TransactionItem
from app.models.outlet import Outlet
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionOut

router = APIRouter(prefix="/transactions", tags=["transactions"])

WIB = timezone(timedelta(hours=7))


async def make_invoice_number(
    db: AsyncSession, outlet: Outlet, tenant_id: uuid.UUID
) -> str:
    today = datetime.now(WIB).date()
    counter_stmt = (
        pg_insert(InvoiceCounter)
        .values(invoice_date=today, outlet_id=outlet.id, last_number=1)
        .on_conflict_do_update(
            index_elements=[InvoiceCounter.invoice_date, InvoiceCounter.outlet_id],
            set_={"last_number": InvoiceCounter.last_number + 1},
        )
        .returning(InvoiceCounter.last_number)
    )
    number = (await db.execute(counter_stmt)).scalar_one()
    if number > 999999:
        raise HTTPException(
            status_code=409, detail="Nomor invoice hari ini sudah habis"
        )
    tenant_code = await db.scalar(select(Tenant.code).where(Tenant.id == tenant_id))
    return f"INV-{tenant_code}-{outlet.code}-{today:%Y%m%d}-{number:06d}"


def amount_from_percent(amount: int, rate: Decimal) -> int:
    return int(
        (Decimal(amount) * rate / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


async def load_transaction(
    db: AsyncSession, tx_id: uuid.UUID, outlet_id: uuid.UUID | None = None
) -> Transaction | None:
    query = select(Transaction).options(selectinload(Transaction.items)).where(Transaction.id == tx_id)
    if outlet_id is not None:
        query = query.where(Transaction.outlet_id == outlet_id)
    result = await db.execute(
        query
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    outlet: Outlet = Depends(get_current_outlet),
):
    tx_id = data.id or uuid.uuid4()

    # Kalau ID yang sama sudah pernah masuk, kembalikan data lama (tidak dobel)
    existing = await load_transaction(db, tx_id, outlet.id)
    if existing is not None:
        if existing.cashier_id != user.id:
            raise HTTPException(status_code=409, detail="ID transaksi sudah dipakai")
        return existing

    # Kumpulkan kuantitas untuk validasi dan pengurangan stok per produk.
    quantities: dict[uuid.UUID, int] = {}
    for item in data.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    product_ids = sorted(quantities.keys())

    # Kunci baris produk supaya dua kasir tidak mengurangi stok yang sama bersamaan
    result = await db.execute(
        select(Product)
        .where(
            Product.id.in_(product_ids),
            Product.outlet_id == outlet.id,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
        )
        .order_by(Product.id)
        .with_for_update()
    )
    products = {p.id: p for p in result.scalars().all()}
    if len(products) != len(product_ids):
        raise HTTPException(
            status_code=400, detail="Ada produk yang tidak ditemukan atau tidak aktif"
        )

    subtotal = 0
    item_discount_total = 0
    items: list[TransactionItem] = []
    movements: list[StockMovement] = []

    for product_id in product_ids:
        product = products[product_id]
        qty = quantities[product_id]

        if product.stock < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Stok {product.name} tidak cukup (sisa {product.stock})",
            )

        product.stock -= qty
        movements.append(
            StockMovement(
                product_id=product.id,
                outlet_id=outlet.id,
                change=-qty,
                stock_after=product.stock,
                reason="sale",
                reference_id=tx_id,
                user_id=user.id,
            )
        )

    for requested_item in data.items:
        product = products[requested_item.product_id]
        line_subtotal = product.price * requested_item.quantity
        if line_subtotal > MAX_BIGINT or subtotal > MAX_BIGINT - line_subtotal:
            raise HTTPException(status_code=400, detail="Subtotal transaksi melampaui batas BIGINT")
        line_discount_percent = requested_item.discount_percent or Decimal("0")
        line_discount = (
            requested_item.discount
            if requested_item.discount is not None
            else amount_from_percent(line_subtotal, line_discount_percent)
        )
        if line_discount > line_subtotal:
            raise HTTPException(
                status_code=400,
                detail=f"Diskon item {product.name} melebihi subtotal item",
            )
        subtotal += line_subtotal
        item_discount_total += line_discount
        items.append(
            TransactionItem(
                product_id=product.id,
                product_name=product.name,
                price=product.price,
                quantity=requested_item.quantity,
                subtotal=line_subtotal,
                discount=line_discount,
                discount_percent=line_discount_percent,
            )
        )

    subtotal_after_items = subtotal - item_discount_total
    transaction_discount_percent = data.discount_percent or Decimal("0")
    transaction_discount = (
        data.discount
        if data.discount is not None
        else amount_from_percent(subtotal_after_items, transaction_discount_percent)
    )
    if transaction_discount > subtotal_after_items:
        raise HTTPException(
            status_code=400,
            detail="Diskon transaksi melebihi subtotal setelah diskon item",
        )

    total_discount = item_discount_total + transaction_discount
    tax_percent = settings.TAX_RATE_PERCENT
    tax_amount = amount_from_percent(subtotal - total_discount, tax_percent)
    total = subtotal - total_discount + tax_amount
    if total_discount > MAX_BIGINT or tax_amount > MAX_BIGINT or total > MAX_BIGINT:
        raise HTTPException(status_code=400, detail="Nilai transaksi melampaui batas BIGINT")
    if data.paid_amount < total:
        raise HTTPException(status_code=400, detail="Uang yang dibayar kurang")

    transaction = Transaction(
        id=tx_id,
        outlet_id=outlet.id,
        invoice_number=await make_invoice_number(db, outlet, user.tenant_id),
        cashier_id=user.id,
        subtotal=subtotal,
        discount=total_discount,
        discount_percent=transaction_discount_percent,
        tax_percent=tax_percent,
        tax_amount=tax_amount,
        total=total,
        payment_method=data.payment_method,
        paid_amount=data.paid_amount,
        change_amount=data.paid_amount - total,
        status="completed",
        note=data.note,
        items=items,
    )
    db.add(transaction)
    db.add_all(movements)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await load_transaction(db, tx_id, outlet.id)
        if existing is not None and existing.cashier_id == user.id:
            return existing
        raise HTTPException(status_code=409, detail="Transaksi gagal disimpan")

    return await load_transaction(db, tx_id, outlet.id)


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    outlet: Outlet = Depends(get_current_outlet),
):
    query = select(Transaction).options(selectinload(Transaction.items)).where(Transaction.outlet_id == outlet.id)
    if user.role == "cashier":
        query = query.where(Transaction.cashier_id == user.id)
    if status_filter:
        query = query.where(Transaction.status == status_filter)
    query = query.order_by(Transaction.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{transaction_id}", response_model=TransactionOut)
async def get_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    outlet: Outlet = Depends(get_current_outlet),
):
    transaction = await load_transaction(db, transaction_id, outlet.id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    if user.role == "cashier" and transaction.cashier_id != user.id:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    return transaction


@router.post("/{transaction_id}/void", response_model=TransactionOut)
async def void_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    # Kunci baris transaksi supaya tidak dibatalkan dua kali bersamaan
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.outlet_id == outlet.id).with_for_update()
    )
    transaction = result.scalar_one_or_none()
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    if transaction.status == "voided":
        raise HTTPException(status_code=400, detail="Transaksi sudah dibatalkan")

    items_result = await db.execute(
        select(TransactionItem).where(TransactionItem.transaction_id == transaction.id)
    )
    items = items_result.scalars().all()
    product_ids = sorted({item.product_id for item in items})

    products_result = await db.execute(
        select(Product)
        .where(Product.id.in_(product_ids), Product.outlet_id == outlet.id)
        .order_by(Product.id)
        .with_for_update()
    )
    products = {p.id: p for p in products_result.scalars().all()}

    for item in items:
        product = products[item.product_id]
        if product.stock > MAX_BIGINT - item.quantity:
            raise HTTPException(status_code=409, detail=f"Stok {product.name} akan melampaui batas BIGINT")
        product.stock += item.quantity
        db.add(
            StockMovement(
                product_id=product.id,
                outlet_id=outlet.id,
                change=item.quantity,
                stock_after=product.stock,
                reason="void",
                reference_id=transaction.id,
                user_id=user.id,
            )
        )

    transaction.status = "voided"
    await db.commit()

    return await load_transaction(db, transaction_id, outlet.id)
