from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class Category(BaseModel):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)