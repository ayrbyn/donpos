"""add outlet scoping and memberships

Revision ID: 3c781b5ea942
Revises: f3a6c2d91b74
Create Date: 2026-10-31 00:00:00.000000
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "3c781b5ea942"
down_revision: Union[str, Sequence[str], None] = "f3a6c2d91b74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_OUTLET_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def upgrade() -> None:
    op.create_table(
        "outlets",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outlets_code", "outlets", ["code"], unique=True)
    op.bulk_insert(
        sa.table(
            "outlets",
            sa.column("id", sa.UUID()),
            sa.column("name", sa.String()),
            sa.column("code", sa.String()),
            sa.column("is_active", sa.Boolean()),
        ),
        [{"id": DEFAULT_OUTLET_ID, "name": "Cabang Utama", "code": "MAIN", "is_active": True}],
    )

    for table_name in ("categories", "products", "transactions", "stock_movements", "invoice_counters"):
        op.add_column(table_name, sa.Column("outlet_id", sa.UUID(), nullable=True))
        op.execute(
            sa.text(f'UPDATE "{table_name}" SET outlet_id = :outlet_id').bindparams(
                outlet_id=DEFAULT_OUTLET_ID
            )
        )
        op.alter_column(table_name, "outlet_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table_name}_outlet_id_outlets",
            table_name,
            "outlets",
            ["outlet_id"],
            ["id"],
        )
        op.create_index(f"ix_{table_name}_outlet_id", table_name, ["outlet_id"])

    op.drop_index("ix_categories_name", table_name="categories")
    op.create_unique_constraint(
        "uq_categories_outlet_name", "categories", ["outlet_id", "name"]
    )

    op.drop_constraint("products_sku_key", "products", type_="unique")
    op.drop_constraint("products_barcode_key", "products", type_="unique")
    op.create_unique_constraint(
        "uq_products_outlet_sku", "products", ["outlet_id", "sku"]
    )
    op.create_unique_constraint(
        "uq_products_outlet_barcode", "products", ["outlet_id", "barcode"]
    )

    op.drop_constraint("invoice_counters_pkey", "invoice_counters", type_="primary")
    op.create_primary_key(
        "invoice_counters_pkey", "invoice_counters", ["invoice_date", "outlet_id"]
    )

    op.create_table(
        "user_outlets",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("outlet_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_outlets_user_id_users"),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"], name="fk_user_outlets_outlet_id_outlets"),
        sa.PrimaryKeyConstraint("user_id", "outlet_id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO user_outlets (user_id, outlet_id) "
            "SELECT id, :outlet_id FROM users WHERE role <> 'owner'"
        ).bindparams(outlet_id=DEFAULT_OUTLET_ID)
    )


def downgrade() -> None:
    raise RuntimeError(
        "Multi-outlet data cannot be safely downgraded to a single outlet. "
        "Back up and manually consolidate data before restoring the prior schema."
    )
