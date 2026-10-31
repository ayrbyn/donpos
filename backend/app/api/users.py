import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_outlet, require_roles
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models.outlet import Outlet, UserOutlet
from app.models.user import User
from app.schemas.outlet import OutletOut, UserOutletUpdate
from app.schemas.user import (
    UserOut,
    UserPasswordChange,
    UserPasswordReset,
    UserStatusUpdate,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


async def get_user_or_404(
    db: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID, *, lock: bool = False
) -> User:
    query = select(User).where(
        User.id == user_id,
        User.tenant_id == tenant_id,
        User.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    user = await db.scalar(query)
    if user is None:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    return user


async def ensure_manage_scope(
    db: AsyncSession, actor: User, target: User, outlet: Outlet
) -> None:
    if actor.role == "owner":
        return
    if target.role == "owner":
        raise HTTPException(status_code=403, detail="Admin tidak dapat mengubah akun owner")
    membership = await db.scalar(
        select(UserOutlet.user_id).where(
            UserOutlet.user_id == target.id,
            UserOutlet.outlet_id == outlet.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")


async def validate_membership_assignment(
    db: AsyncSession, actor: User, outlet_ids: set[uuid.UUID]
) -> None:
    active_ids = set(
        (
            await db.scalars(
                select(Outlet.id).where(
                    Outlet.id.in_(outlet_ids),
                    Outlet.tenant_id == actor.tenant_id,
                    Outlet.is_active.is_(True),
                    Outlet.deleted_at.is_(None),
                )
            )
        ).all()
    ) if outlet_ids else set()
    if active_ids != outlet_ids:
        raise HTTPException(
            status_code=400, detail="Ada outlet yang tidak ditemukan atau tidak aktif"
        )
    if actor.role == "admin":
        permitted = set(
            (
                await db.scalars(
                    select(UserOutlet.outlet_id).where(
                    UserOutlet.user_id == actor.id,
                    UserOutlet.outlet_id.in_(
                        select(Outlet.id).where(Outlet.tenant_id == actor.tenant_id)
                    ),
                    )
                )
            ).all()
        )
        if not outlet_ids.issubset(permitted):
            raise HTTPException(
                status_code=403,
                detail="Admin hanya dapat menugaskan pengguna ke outlet yang dikelolanya",
            )


async def target_outlet_ids(
    db: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID
) -> set[uuid.UUID]:
    return set(
        (
            await db.scalars(
                select(UserOutlet.outlet_id)
                .join(Outlet, Outlet.id == UserOutlet.outlet_id)
                .where(
                    UserOutlet.user_id == user_id,
                    Outlet.tenant_id == tenant_id,
                )
            )
        ).all()
    )


async def protect_last_active_owner(
    db: AsyncSession,
    target: User,
    *,
    new_role: str | None = None,
    new_is_active: bool | None = None,
) -> None:
    owner_removed = target.role == "owner" and (
        (new_role is not None and new_role != "owner") or new_is_active is False
    )
    if not owner_removed or not target.is_active:
        return
    owner_ids = await db.scalars(
        select(User.id)
        .where(
            User.role == "owner",
            User.tenant_id == target.tenant_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .order_by(User.id)
        .with_for_update()
    )
    if len(owner_ids.all()) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Tidak dapat menonaktifkan atau menurunkan role owner aktif terakhir",
    )


async def replace_user_outlets(
    db: AsyncSession,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    outlet_ids: set[uuid.UUID],
) -> None:
    await db.execute(delete(UserOutlet).where(UserOutlet.user_id == user_id))
    for outlet_id in outlet_ids:
        db.add(UserOutlet(user_id=user_id, outlet_id=outlet_id, tenant_id=tenant_id))


async def admin_preserved_outlets(
    db: AsyncSession, actor: User, target_id: uuid.UUID
) -> set[uuid.UUID]:
    if actor.role != "admin":
        return set()
    permitted = set(
        (
            await db.scalars(
                select(UserOutlet.outlet_id).where(UserOutlet.user_id == actor.id)
            )
        ).all()
    )
    current = await target_outlet_ids(db, target_id, actor.tenant_id)
    return current - permitted


@router.get("", response_model=list[UserOut])
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = True,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    query = select(User).where(
        User.deleted_at.is_(None), User.tenant_id == actor.tenant_id
    )
    if actor.role != "owner":
        query = query.join(UserOutlet, UserOutlet.user_id == User.id).where(
            UserOutlet.outlet_id == outlet.id
        )
    if not include_inactive:
        query = query.where(User.is_active.is_(True))
    result = await db.execute(
        query.distinct().order_by(User.full_name, User.username).limit(limit).offset(offset)
    )
    return result.scalars().all()


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Tidak ada data yang diubah")
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=400, detail="Nilai perubahan tidak boleh kosong")

    target = await get_user_or_404(db, user_id, actor.tenant_id, lock=True)
    await ensure_manage_scope(db, actor, target, outlet)
    if actor.id == target.id and "role" in changes:
        raise HTTPException(status_code=400, detail="Tidak dapat mengubah role akun sendiri")
    if actor.role == "admin" and changes.get("role") == "owner":
        raise HTTPException(status_code=403, detail="Admin tidak dapat memberikan role owner")
    await protect_last_active_owner(db, target, new_role=changes.get("role"))

    if "username" in changes:
        existing = await db.scalar(
            select(User).where(
                User.username == changes["username"], User.id != target.id
            )
        )
        if existing is not None:
            raise HTTPException(status_code=400, detail="Username sudah dipakai")

    requested_outlet_ids = changes.pop("outlet_ids", None)
    next_role = changes.get("role", target.role)
    if next_role == "owner":
        requested_outlet_ids = set()
    elif requested_outlet_ids is None:
        requested_outlet_ids = await target_outlet_ids(db, target.id, actor.tenant_id)
    else:
        requested_outlet_ids = set(requested_outlet_ids)
        await validate_membership_assignment(db, actor, requested_outlet_ids)
    if next_role != "owner":
        requested_outlet_ids |= await admin_preserved_outlets(db, actor, target.id)
    if next_role != "owner" and not requested_outlet_ids:
        raise HTTPException(
            status_code=400, detail="Pengguna harus memiliki minimal satu outlet"
        )
    if actor.role == "owner":
        await validate_membership_assignment(db, actor, requested_outlet_ids)

    for field, value in changes.items():
        setattr(target, field, value)
    if "role" in changes or data.outlet_ids is not None:
        target.token_version += 1
    await replace_user_outlets(
        db, target.id, actor.tenant_id, requested_outlet_ids
    )
    await db.commit()
    await db.refresh(target)
    return target


@router.patch("/{user_id}/status", response_model=UserOut)
async def update_user_status(
    user_id: uuid.UUID,
    data: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    target = await get_user_or_404(db, user_id, actor.tenant_id, lock=True)
    await ensure_manage_scope(db, actor, target, outlet)
    if target.id == actor.id and not data.is_active:
        raise HTTPException(status_code=400, detail="Tidak dapat menonaktifkan akun sendiri")
    await protect_last_active_owner(db, target, new_is_active=data.is_active)
    target.is_active = data.is_active
    target.token_version += 1
    await db.commit()
    await db.refresh(target)
    return target


@router.put("/me/password", status_code=204)
async def change_own_password(
    data: UserPasswordChange,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "cashier")),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password saat ini salah")
    user.password_hash = hash_password(data.new_password)
    user.token_version += 1
    await db.commit()


@router.put("/{user_id}/password", status_code=204)
async def reset_user_password(
    user_id: uuid.UUID,
    data: UserPasswordReset,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    target = await get_user_or_404(db, user_id, actor.tenant_id)
    await ensure_manage_scope(db, actor, target, outlet)
    target.password_hash = hash_password(data.password)
    target.token_version += 1
    await db.commit()


@router.get("/{user_id}/outlets", response_model=list[OutletOut])
async def list_user_outlets(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    target = await get_user_or_404(db, user_id, actor.tenant_id)
    await ensure_manage_scope(db, actor, target, outlet)
    result = await db.execute(
        select(Outlet)
        .join(UserOutlet, UserOutlet.outlet_id == Outlet.id)
        .where(
            UserOutlet.user_id == target.id,
            Outlet.tenant_id == actor.tenant_id,
        )
        .order_by(Outlet.name)
    )
    return result.scalars().all()


@router.put("/{user_id}/outlets", response_model=list[OutletOut])
async def update_user_outlets(
    user_id: uuid.UUID,
    data: UserOutletUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
    outlet: Outlet = Depends(get_current_outlet),
):
    target = await get_user_or_404(db, user_id, actor.tenant_id, lock=True)
    await ensure_manage_scope(db, actor, target, outlet)
    if target.role == "owner" and data.outlet_ids:
        raise HTTPException(status_code=400, detail="Owner memiliki akses global dan tidak memakai penugasan outlet")
    outlet_ids = set(data.outlet_ids)
    await validate_membership_assignment(db, actor, outlet_ids)
    if target.role != "owner":
        outlet_ids |= await admin_preserved_outlets(db, actor, target.id)
    if target.role != "owner" and not outlet_ids:
        raise HTTPException(status_code=400, detail="Pengguna harus memiliki minimal satu outlet")
    await replace_user_outlets(db, target.id, actor.tenant_id, outlet_ids)
    target.token_version += 1
    await db.commit()
    if not outlet_ids:
        return []
    result = await db.execute(
        select(Outlet)
        .where(Outlet.id.in_(outlet_ids), Outlet.tenant_id == actor.tenant_id)
        .order_by(Outlet.name)
    )
    return result.scalars().all()
