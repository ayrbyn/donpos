import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OutletCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=2, max_length=8)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Nama outlet tidak boleh kosong")
        return value

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{2,8}", value):
            raise ValueError("Kode outlet harus 2–8 huruf atau angka")
        return value


class OutletUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=2, max_length=8)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Nama outlet tidak boleh kosong")
        return value

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{2,8}", value):
            raise ValueError("Kode outlet harus 2–8 huruf atau angka")
        return value


class OutletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    code: str
    is_active: bool


class UserOutletUpdate(BaseModel):
    outlet_ids: list[uuid.UUID]
