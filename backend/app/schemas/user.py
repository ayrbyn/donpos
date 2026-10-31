import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=72)
    role: str = "cashier"
    outlet_ids: list[uuid.UUID] = Field(default_factory=list)


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["owner", "admin", "cashier"] | None = None
    outlet_ids: list[uuid.UUID] | None = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Username tidak boleh kosong")
        return normalized

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Nama lengkap tidak boleh kosong")
        return normalized


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserPasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=72)


class UserPasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=12, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    username: str
    full_name: str
    role: str
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
