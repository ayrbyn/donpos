import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_outlet, get_current_user, require_roles
from app.core.constants import MAX_BIGINT
from app.db.session import get_db
from app.models.category import Category
from app.models.product import Product
from app.models.outlet import Outlet
from app.models.user import User
from app.models.stock_movement import StockMovement
from app.schemas.product import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    StockAdjust,
    StockMovementOut,
)

router = APIRouter(prefix="/products", tags=["products"])


async def get_product_or_404(
    db: AsyncSession, product_id: uuid.UUID, outlet_id: uuid.UUID
) -> Product:
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.outlet_id == outlet_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    return product


async def ensure_category_exists(
    db: AsyncSession, category_id: uuid.UUID, outlet_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            Category.outlet_id == outlet_id,
            Category.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="Kategori tidak ditemukan")


async def ensure_unique(
    db: AsyncSession,
    sku: str | None,
    barcode: str | None,
    outlet_id: uuid.UUID,
    exclude_id: uuid.UUID | None = None,
) -> None:
    if sku:
        query = select(Product).where(
            Product.sku == sku, Product.outlet_id == outlet_id
        )
        if exclude_id is not None:
            query = query.where(Product.id != exclude_id)
        if (await db.execute(query)).scalar_one_or_none() is not None:
            raise HTTPException(status_code=400, detail="SKU sudah dipakai")
    if barcode:
        query = select(Product).where(
            Product.barcode == barcode, Product.outlet_id == outlet_id
        )
        if exclude_id is not None:
            query = query.where(Product.id != exclude_id)
        if (await db.execute(query)).scalar_one_or_none() is not None:
            raise HTTPException(status_code=400, detail="Barcode sudah dipakai")


@router.get("", response_model=list[ProductOut])
async def list_products(
    q: str | None = Query(default=None, description="Cari nama, SKU, atau barcode"),
    category_id: uuid.UUID | None = None,
    only_active: bool = True,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    outlet: Outlet = Depends(get_current_outlet),
):
    query = select(Product).where(
        Product.deleted_at.is_(None), Product.outlet_id == outlet.id
    )
    if only_active:
        query = query.where(Product.is_active.is_(True))
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Product.name.ilike(pattern),
                Product.sku.ilike(pattern),
                Product.barcode.ilike(pattern),
            )
        )
    query = query.order_by(Product.name).limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/barcode/{barcode}", response_model=ProductOut)
async def get_by_barcode(
    barcode: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    outlet: Outlet = Depends(get_current_outlet),
):
    result = await db.execute(
        select(Product).where(
            Product.barcode == barcode,
            Product.outlet_id == outlet.id,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    return product


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    outlet: Outlet = Depends(get_current_outlet),
):
    return await get_product_or_404(db, product_id, outlet.id)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    sku = data.sku.strip() if data.sku else None
    barcode = data.barcode.strip() if data.barcode else None
    await ensure_unique(db, sku, barcode, outlet.id)
    if data.category_id is not None:
        await ensure_category_exists(db, data.category_id, outlet.id)

    product = Product(
        outlet_id=outlet.id,
        name=data.name.strip(),
        sku=sku or None,
        barcode=barcode or None,
        price=data.price,
        stock=data.stock,
        category_id=data.category_id,
    )
    db.add(product)
    await db.flush()

    if data.stock > 0:
        db.add(
            StockMovement(
                product_id=product.id,
                outlet_id=outlet.id,
                change=data.stock,
                stock_after=data.stock,
                reason="initial",
                note="Stok awal",
                user_id=user.id,
            )
        )

    await db.commit()
    await db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    product = await get_product_or_404(db, product_id, outlet.id)
    changes = data.model_dump(exclude_unset=True)

    sku = changes.get("sku", product.sku)
    barcode = changes.get("barcode", product.barcode)
    sku = sku.strip() if sku else None
    barcode = barcode.strip() if barcode else None
    await ensure_unique(db, sku, barcode, outlet.id, exclude_id=product.id)

    if changes.get("category_id") is not None:
        await ensure_category_exists(db, changes["category_id"], outlet.id)

    for field in ("name", "price", "is_active", "category_id"):
        if field in changes:
            setattr(product, field, changes[field])
    if "sku" in changes:
        product.sku = sku or None
    if "barcode" in changes:
        product.barcode = barcode or None

    await db.commit()
    await db.refresh(product)
    return product

@router.post("/{product_id}/stock-adjustments", response_model=ProductOut)
async def adjust_stock(
    product_id: uuid.UUID,
    data: StockAdjust,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    if data.change == 0:
        raise HTTPException(status_code=400, detail="Perubahan stok tidak boleh nol")

    # Kunci baris produk supaya tidak bentrok dengan transaksi yang sedang berjalan
    result = await db.execute(
        select(Product)
        .where(
            Product.id == product_id,
            Product.outlet_id == outlet.id,
            Product.deleted_at.is_(None),
        )
        .with_for_update()
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")

    new_stock = product.stock + data.change
    if new_stock < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Stok tidak boleh negatif (stok sekarang {product.stock})",
        )
    if new_stock > MAX_BIGINT:
        raise HTTPException(status_code=400, detail="Stok melampaui batas BIGINT")

    product.stock = new_stock
    db.add(
        StockMovement(
            product_id=product.id,
            outlet_id=outlet.id,
            change=data.change,
            stock_after=new_stock,
            reason=data.reason,
            note=data.note,
            user_id=user.id,
        )
    )
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/{product_id}/stock-movements", response_model=list[StockMovementOut])
async def list_stock_movements(
    product_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    await get_product_or_404(db, product_id, outlet.id)
    result = await db.execute(
        select(StockMovement)
        .where(
            StockMovement.product_id == product_id,
            StockMovement.outlet_id == outlet.id,
        )
        .order_by(StockMovement.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    product = await get_product_or_404(db, product_id, outlet.id)
    product.deleted_at = datetime.now(timezone.utc)
    # Kosongkan sku dan barcode supaya bisa dipakai produk baru
    product.sku = None
    product.barcode = None
    await db.commit()
