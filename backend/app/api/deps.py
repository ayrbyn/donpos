import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.models.outlet import Outlet, UserOutlet
from app.models.tenant import Tenant

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise error

    try:
        user_id = uuid.UUID(payload.get("sub", ""))
    except ValueError:
        raise error

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise error
    # Token tenant claim is checked on every request; changing tenant membership
    # invalidates tokens issued before that change.
    if payload.get("tid") != str(user.tenant_id):
        raise error
    if payload.get("ver") != user.token_version:
        raise error
    tenant = await db.scalar(
        select(Tenant).where(Tenant.id == user.tenant_id, Tenant.deleted_at.is_(None))
    )
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=403, detail="Akun usaha dinonaktifkan")
    return user


def require_roles(*roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kamu tidak punya izin untuk aksi ini",
            )
        return user

    return checker


async def get_current_outlet(
    outlet_id: uuid.UUID = Header(alias="X-Outlet-ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Outlet:
    outlet = await db.scalar(
        select(Outlet).where(
            Outlet.id == outlet_id,
            Outlet.tenant_id == user.tenant_id,
            Outlet.is_active.is_(True),
            Outlet.deleted_at.is_(None),
        )
    )
    if outlet is None:
        raise HTTPException(status_code=404, detail="Outlet tidak ditemukan atau tidak aktif")

    if user.role != "owner":
        membership = await db.scalar(
            select(UserOutlet.user_id).where(
                UserOutlet.user_id == user.id,
                UserOutlet.outlet_id == outlet.id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=403, detail="Kamu tidak terdaftar di outlet ini")
    return outlet
