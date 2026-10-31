import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db

from app.models.outlet import Outlet, UserOutlet
from app.models.tenant import SignupAttempt, Tenant
from app.models.user import User
from app.schemas.tenant import TenantCreate, TenantSignupOut
from app.schemas.user import TokenOut, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def generate_tenant_code() -> str:
    return secrets.token_hex(6).upper()


async def consume_signup_attempt(db: AsyncSession, request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = hmac.new(
        settings.SECRET_KEY.encode(), client_ip.encode(), hashlib.sha256
    ).hexdigest()
    now = datetime.now(timezone.utc)
    expired = SignupAttempt.window_started_at <= now - timedelta(hours=1)
    statement = (
        pg_insert(SignupAttempt)
        .values(ip_hash=ip_hash, window_started_at=now, attempts=1)
        .on_conflict_do_update(
            index_elements=[SignupAttempt.ip_hash],
            set_={
                "window_started_at": case(
                    (expired, now), else_=SignupAttempt.window_started_at
                ),
                "attempts": case((expired, 1), else_=SignupAttempt.attempts + 1),
            },
        )
        .returning(SignupAttempt.attempts)
    )
    attempts = (await db.execute(statement)).scalar_one()
    await db.execute(
        delete(SignupAttempt).where(
            SignupAttempt.window_started_at < now - timedelta(days=2),
            SignupAttempt.ip_hash != ip_hash,
        )
    )
    await db.commit()
    if attempts > 5:
        raise HTTPException(
            status_code=429,
            detail="Batas pendaftaran tercapai. Coba lagi dalam satu jam.",
            headers={"Retry-After": "3600"},
        )


@router.post("/signup", response_model=TenantSignupOut, status_code=201)
async def signup_tenant(
    data: TenantCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Buat tenant, owner, dan outlet pertama dalam satu transaksi."""
    await consume_signup_attempt(db, request)
    username = data.username
    if await db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(status_code=400, detail="Username sudah dipakai")

    tenant = Tenant(name=data.name, code=generate_tenant_code(), is_active=True)
    db.add(tenant)
    try:
        await db.flush()
        owner = User(
            tenant_id=tenant.id,
            username=username,
            full_name=data.full_name,
            password_hash=hash_password(data.password),
            role="owner",
            is_active=True,
        )
        outlet = Outlet(
            tenant_id=tenant.id,
            name="Cabang Utama",
            code="MAIN",
            is_active=True,
        )
        db.add_all([owner, outlet])
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Usaha atau akun gagal dibuat")
    await db.refresh(tenant)
    await db.refresh(owner)
    token = create_access_token(
        str(owner.id), owner.role, str(tenant.id), owner.token_version
    )
    return TenantSignupOut(tenant=tenant, user=owner, access_token=token)


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner")),
):
    """Membuat akun kasir atau admin baru. Hanya owner yang boleh."""
    if data.role not in ("owner", "admin", "cashier"):
        raise HTTPException(status_code=400, detail="Role tidak dikenal")
    outlet_ids = set(data.outlet_ids)
    if data.role != "owner" and not outlet_ids:
        raise HTTPException(status_code=400, detail="Pengguna harus ditugaskan minimal ke satu outlet")
    if outlet_ids:
        active_outlet_ids = set(
            (await db.scalars(
                select(Outlet.id).where(
                    Outlet.id.in_(outlet_ids),
                    Outlet.tenant_id == _.tenant_id,
                    Outlet.is_active.is_(True),
                    Outlet.deleted_at.is_(None),
                )
            )).all()
        )
        if active_outlet_ids != outlet_ids:
            raise HTTPException(status_code=400, detail="Ada outlet yang tidak ditemukan atau tidak aktif")

    exists = await db.scalar(
        select(User).where(User.username == data.username.lower())
    )
    if exists:
        raise HTTPException(status_code=400, detail="Username sudah dipakai")

    user = User(
        tenant_id=_.tenant_id,
        username=data.username.lower(),
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.flush()
    for outlet_id in outlet_ids:
        db.add(
            UserOutlet(user_id=user.id, outlet_id=outlet_id, tenant_id=_.tenant_id)
        )
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(
            User.username == form.username.lower(), User.deleted_at.is_(None)
        )
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Akun dinonaktifkan"
        )
    tenant_is_active = await db.scalar(
        select(Tenant.is_active).where(
            Tenant.id == user.tenant_id, Tenant.deleted_at.is_(None)
        )
    )
    if not tenant_is_active:
        raise HTTPException(status_code=403, detail="Akun usaha dinonaktifkan")

    token = create_access_token(
        str(user.id), user.role, str(user.tenant_id), user.token_version
    )
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
