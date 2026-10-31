from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"
    TAX_RATE_PERCENT: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2
    )

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
