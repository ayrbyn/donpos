from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import (
    auth,
    categories,
    outlets,
    product_import,
    products,
    reports,
    transactions,
    tenants,
    users,
)
from app.db.session import get_db

app = FastAPI(title="POS API")

app.include_router(auth.router)
app.include_router(outlets.router)
app.include_router(tenants.router)
app.include_router(categories.router)
app.include_router(product_import.router)
app.include_router(products.router)
app.include_router(transactions.router)
app.include_router(reports.router)
app.include_router(users.router)


@app.get("/")
async def root():
    return {"message": "POS API berjalan"}


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "terhubung"}
