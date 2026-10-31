import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.outlet import Outlet, UserOutlet
from app.models.transaction import Transaction
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.outlet import OutletCreate, OutletOut, OutletUpdate

router = APIRouter(prefix="/outlets", tags=["outlets"])


@router.get("", response_model=list[OutletOut])
async def list_outlets(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Outlet).where(
        Outlet.tenant_id == user.tenant_id,
        Outlet.is_active.is_(True), Outlet.deleted_at.is_(None)
    )
    if user.role != "owner":
        query = query.join(UserOutlet, UserOutlet.outlet_id == Outlet.id).where(
            UserOutlet.user_id == user.id
        )
    result = await db.execute(query.order_by(Outlet.name))
    return result.scalars().all()


@router.post("", response_model=OutletOut, status_code=status.HTTP_201_CREATED)
async def create_outlet(
    data: OutletCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner")),
):
    existing = await db.scalar(
        select(Outlet.id).where(
            Outlet.tenant_id == _.tenant_id, Outlet.code == data.code
        )
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="Kode outlet sudah dipakai")
    outlet = Outlet(
        tenant_id=_.tenant_id, name=data.name, code=data.code, is_active=True
    )
    db.add(outlet)
    await db.commit()
    await db.refresh(outlet)
    return outlet


@router.patch("/{outlet_id}", response_model=OutletOut)
async def update_outlet(
    outlet_id: uuid.UUID,
    data: OutletUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner")),
):
    outlet = await db.scalar(
        select(Outlet).where(
            Outlet.id == outlet_id,
            Outlet.tenant_id == _.tenant_id,
            Outlet.deleted_at.is_(None),
        )
    )
    if outlet is None:
        raise HTTPException(status_code=404, detail="Outlet tidak ditemukan")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Tidak ada data yang diubah")
    if "code" in changes:
        has_transactions = await db.scalar(
            select(Transaction.id).where(Transaction.outlet_id == outlet.id).limit(1)
        )
        if has_transactions is not None and changes["code"] != outlet.code:
            raise HTTPException(
                status_code=400,
                detail="Kode outlet tidak dapat diubah setelah memiliki transaksi",
            )
        tenant_code = await db.scalar(
            select(Tenant.code).where(Tenant.id == outlet.tenant_id)
        )
        code_was_used = await db.scalar(
            select(Transaction.id)
            .where(
                Transaction.invoice_number.startswith(
                    f"INV-{tenant_code}-{changes['code']}-"
                )
            )
            .limit(1)
        )
        if code_was_used is not None and changes["code"] != outlet.code:
            raise HTTPException(
                status_code=400,
                detail="Kode outlet pernah dipakai pada nomor invoice",
            )
        existing = await db.scalar(
            select(Outlet.id).where(
                Outlet.tenant_id == outlet.tenant_id,
                Outlet.code == changes["code"],
                Outlet.id != outlet.id,
            )
        )
        if existing is not None:
            raise HTTPException(status_code=400, detail="Kode outlet sudah dipakai")
    for field, value in changes.items():
        setattr(outlet, field, value)
    await db.commit()
    await db.refresh(outlet)
    return outlet
