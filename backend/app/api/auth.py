from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import TokenOut, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/bootstrap", response_model=UserOut, status_code=201)
async def bootstrap_owner(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Membuat akun owner pertama. Hanya bisa dipakai saat tabel users masih kosong."""
    total = await db.scalar(select(func.count()).select_from(User))
    if total and total > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner sudah ada. Gunakan endpoint register dengan akun owner.",
        )

    user = User(
        username=data.username.lower(),
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role="owner",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner")),
):
    """Membuat akun kasir atau admin baru. Hanya owner yang boleh."""
    if data.role not in ("owner", "admin", "cashier"):
        raise HTTPException(status_code=400, detail="Role tidak dikenal")

    exists = await db.scalar(
        select(User).where(User.username == data.username.lower())
    )
    if exists:
        raise HTTPException(status_code=400, detail="Username sudah dipakai")

    user = User(
        username=data.username.lower(),
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
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

    token = create_access_token(str(user.id), user.role)
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user