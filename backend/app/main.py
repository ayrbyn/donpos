from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import auth, categories, products, transactions
from app.db.session import get_db

app = FastAPI(title="POS API")

app.include_router(auth.router)
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(transactions.router)


@app.get("/")
async def root():
    return {"message": "POS API berjalan"}


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "terhubung"}