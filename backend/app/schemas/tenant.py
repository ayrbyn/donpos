import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.user import UserOut


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=72)

    @field_validator("name", "full_name")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nilai tidak boleh kosong")
        return value

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9_.-]{3,50}", value):
            raise ValueError("Username hanya boleh berisi huruf, angka, titik, garis bawah, dan tanda hubung")
        return value


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    is_active: bool


class TenantUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nama usaha tidak boleh kosong")
        return value


class TenantSignupOut(BaseModel):
    tenant: TenantOut
    user: UserOut
    access_token: str
    token_type: str = "bearer"

