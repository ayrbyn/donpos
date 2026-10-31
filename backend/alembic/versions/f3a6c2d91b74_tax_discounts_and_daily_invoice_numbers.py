"""add transaction tax/discount data and daily invoice counters

Revision ID: f3a6c2d91b74
Revises: d95b7cec3c85
Create Date: 2026-10-31 00:00:00.000000
"""

import re
from datetime import date, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a6c2d91b74"
down_revision: Union[str, Sequence[str], None] = "d95b7cec3c85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "transactions",
        sa.Column("tax_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "transactions",
        sa.Column("tax_amount", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "transaction_items",
        sa.Column("discount", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "transaction_items",
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    for table_name, column_name in (
        ("transactions", "discount_percent"),
        ("transactions", "tax_percent"),
        ("transactions", "tax_amount"),
        ("transaction_items", "discount"),
        ("transaction_items", "discount_percent"),
    ):
        op.alter_column(table_name, column_name, server_default=None)
    op.create_table(
        "invoice_counters",
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("invoice_date"),
    )

    bind = op.get_bind()
    counters: dict[date, int] = {}
    for invoice_number in bind.execute(
        sa.text("SELECT invoice_number FROM transactions")
    ).scalars():
        match = re.fullmatch(r"INV-(\d{8})-(\d{6})", invoice_number)
        if match:
            invoice_date = datetime.strptime(match.group(1), "%Y%m%d").date()
            counters[invoice_date] = max(counters.get(invoice_date, 0), int(match.group(2)))
    if counters:
        invoice_counters = sa.table(
            "invoice_counters",
            sa.column("invoice_date", sa.Date()),
            sa.column("last_number", sa.Integer()),
        )
        op.bulk_insert(
            invoice_counters,
            [
                {"invoice_date": invoice_date, "last_number": last_number}
                for invoice_date, last_number in counters.items()
            ],
        )


def downgrade() -> None:
    op.drop_table("invoice_counters")
    op.drop_column("transaction_items", "discount_percent")
    op.drop_column("transaction_items", "discount")
    op.drop_column("transactions", "tax_amount")
    op.drop_column("transactions", "tax_percent")
    op.drop_column("transactions", "discount_percent")
