import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionOut

router = APIRouter(prefix="/transactions", tags=["transactions"])

WIB = timezone(timedelta(hours=7))


def make_invoice_number() -> str:
    today = datetime.now(WIB).strftime("%Y%m%d")
    return f"INV-{today}-{uuid.uuid4().hex[:6].upper()}"


async def load_transaction(db: AsyncSession, tx_id: uuid.UUID) -> Transaction | None:
    result = await db.execute(
        select(Transaction)
        .options(selectinload(Transaction.items))
        .where(Transaction.id == tx_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tx_id = data.id or uuid.uuid4()

    # Kalau ID yang sama sudah pernah masuk, kembalikan data lama (tidak dobel)
    existing = await load_transaction(db, tx_id)
    if existing is not None:
        if existing.cashier_id != user.id:
            raise HTTPException(status_code=409, detail="ID transaksi sudah dipakai")
        return existing

    # Gabungkan produk yang sama jika muncul lebih dari sekali
    quantities: dict[uuid.UUID, int] = {}
    for item in data.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    product_ids = sorted(quantities.keys())

    # Kunci baris produk supaya dua kasir tidak mengurangi stok yang sama bersamaan
    result = await db.execute(
        select(Product)
        .where(
            Product.id.in_(product_ids),
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

        line_total = product.price * qty
        subtotal += line_total
        product.stock -= qty

        items.append(
            TransactionItem(
                product_id=product.id,
                product_name=product.name,
                price=product.price,
                quantity=qty,
                subtotal=line_total,
            )
        )
        movements.append(
            StockMovement(
                product_id=product.id,
                change=-qty,
                stock_after=product.stock,
                reason="sale",
                reference_id=tx_id,
            )
        )

    if data.discount > subtotal:
        raise HTTPException(status_code=400, detail="Diskon melebihi subtotal")

    total = subtotal - data.discount
    if data.paid_amount < total:
        raise HTTPException(status_code=400, detail="Uang yang dibayar kurang")

    transaction = Transaction(
        id=tx_id,
        invoice_number=make_invoice_number(),
        cashier_id=user.id,
        subtotal=subtotal,
        discount=data.discount,
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
        existing = await load_transaction(db, tx_id)
        if existing is not None and existing.cashier_id == user.id:
            return existing
        raise HTTPException(status_code=409, detail="Transaksi gagal disimpan")

    return await load_transaction(db, tx_id)


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Transaction).options(selectinload(Transaction.items))
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
):
    transaction = await load_transaction(db, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    if user.role == "cashier" and transaction.cashier_id != user.id:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    return transaction


@router.post("/{transaction_id}/void", response_model=TransactionOut)
async def void_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner", "admin")),
):
    # Kunci baris transaksi supaya tidak dibatalkan dua kali bersamaan
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id).with_for_update()
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
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
    )
    products = {p.id: p for p in products_result.scalars().all()}

    for item in items:
        product = products[item.product_id]
        product.stock += item.quantity
        db.add(
            StockMovement(
                product_id=product.id,
                change=item.quantity,
                stock_after=product.stock,
                reason="void",
                reference_id=transaction.id,
            )
        )

    transaction.status = "voided"
    await db.commit()

    return await load_transaction(db, transaction_id)