from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantOut, TenantUpdate

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/me", response_model=TenantOut)
async def get_my_tenant(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "cashier")),
):
    tenant = await db.scalar(
        select(Tenant).where(Tenant.id == user.tenant_id, Tenant.deleted_at.is_(None))
    )
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Akun usaha dinonaktifkan")
    return tenant


@router.patch("/me", response_model=TenantOut)
async def update_my_tenant(
    data: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner")),
):
    tenant = await db.scalar(
        select(Tenant)
        .where(Tenant.id == user.tenant_id, Tenant.deleted_at.is_(None))
        .with_for_update()
    )
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Akun usaha dinonaktifkan")
    tenant.name = data.name
    await db.commit()
    await db.refresh(tenant)
    return tenant
