from pydantic import BaseModel


class RowMessage(BaseModel):
    row: int
    message: str


class ImportResult(BaseModel):
    dry_run: bool
    saved: bool
    total_rows: int
    to_create: int
    to_update: int
    categories_to_create: list[str]
    error_count: int
    errors: list[RowMessage]
    warnings: list[RowMessage]