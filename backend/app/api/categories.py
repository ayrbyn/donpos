import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.category import Category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


async def get_category_or_404(db: AsyncSession, category_id: uuid.UUID) -> Category:
    result = await db.execute(
        select(Category).where(
            Category.id == category_id, Category.deleted_at.is_(None)
        )
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")
    return category


async def ensure_name_free(
    db: AsyncSession, name: str, exclude_id: uuid.UUID | None = None
) -> None:
    query = select(Category).where(Category.name == name)
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    result = await db.execute(query)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Nama kategori sudah dipakai")


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Category).where(Category.deleted_at.is_(None)).order_by(Category.name)
    )
    return result.scalars().all()


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner", "admin")),
):
    name = data.name.strip()
    await ensure_name_free(db, name)
    category = Category(name=name)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner", "admin")),
):
    category = await get_category_or_404(db, category_id)
    name = data.name.strip()
    await ensure_name_free(db, name, exclude_id=category.id)
    category.name = name
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("owner", "admin")),
):
    category = await get_category_or_404(db, category_id)
    category.deleted_at = datetime.now(timezone.utc)
    category.name = f"{category.name}__dihapus__{category.id}"
    await db.commit()