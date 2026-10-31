"""expand stock and monetary columns to bigint

Revision ID: b62f1a8c4e37
Revises: 7abf4cc219d1
Create Date: 2026-10-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b62f1a8c4e37"
down_revision: Union[str, Sequence[str], None] = "7abf4cc219d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNS = {
    "products": ("price", "stock"),
    "stock_movements": ("change", "stock_after"),
    "transactions": (
        "subtotal", "discount", "tax_amount", "total", "paid_amount", "change_amount"
    ),
    "transaction_items": ("price", "quantity", "subtotal", "discount"),
}


def upgrade() -> None:
    for table, columns in COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                existing_nullable=False,
                postgresql_using=f"{column}::bigint",
            )


def downgrade() -> None:
    bind = op.get_bind()
    for table, columns in COLUMNS.items():
        for column in columns:
            out_of_range = bind.execute(
                sa.text(
                    f'SELECT 1 FROM "{table}" WHERE "{column}" > 2147483647 '
                    f'OR "{column}" < -2147483648 LIMIT 1'
                )
            ).first()
            if out_of_range:
                raise RuntimeError(
                    f"{table}.{column} berisi nilai di luar batas INTEGER; downgrade dibatalkan"
                )
    for table, columns in COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.BigInteger(),
                type_=sa.Integer(),
                existing_nullable=False,
                postgresql_using=f"{column}::integer",
            )
