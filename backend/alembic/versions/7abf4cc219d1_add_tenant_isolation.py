"""add tenant isolation and tenant onboarding

Revision ID: 7abf4cc219d1
Revises: 3c781b5ea942
Create Date: 2026-10-31 00:00:00.000000
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "7abf4cc219d1"
down_revision: Union[str, Sequence[str], None] = "3c781b5ea942"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=12), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_tenants_code"),
    )
    op.create_index("ix_tenants_code", "tenants", ["code"], unique=False)
    op.create_table(
        "signup_attempts",
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("ip_hash"),
    )
    op.bulk_insert(
        sa.table(
            "tenants",
            sa.column("id", sa.UUID()),
            sa.column("name", sa.String()),
            sa.column("code", sa.String()),
            sa.column("is_active", sa.Boolean()),
        ),
        [{"id": DEFAULT_TENANT_ID, "name": "Usaha Utama", "code": "DONPOS01", "is_active": True}],
    )

    op.add_column("users", sa.Column("tenant_id", sa.UUID(), nullable=True))
    op.execute(
        sa.text("UPDATE users SET tenant_id = :tenant_id").bindparams(
            tenant_id=DEFAULT_TENANT_ID
        )
    )
    op.alter_column("users", "tenant_id", nullable=False)
    op.create_foreign_key("fk_users_tenant_id_tenants", "users", "tenants", ["tenant_id"], ["id"])
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_unique_constraint("uq_users_id_tenant_id", "users", ["id", "tenant_id"])
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("users", "token_version", server_default=None)

    op.add_column("outlets", sa.Column("tenant_id", sa.UUID(), nullable=True))
    op.execute(
        sa.text("UPDATE outlets SET tenant_id = :tenant_id").bindparams(
            tenant_id=DEFAULT_TENANT_ID
        )
    )
    op.alter_column("outlets", "tenant_id", nullable=False)
    op.create_foreign_key("fk_outlets_tenant_id_tenants", "outlets", "tenants", ["tenant_id"], ["id"])
    op.create_index("ix_outlets_tenant_id", "outlets", ["tenant_id"])
    op.create_unique_constraint("uq_outlets_id_tenant_id", "outlets", ["id", "tenant_id"])
    op.drop_index("ix_outlets_code", table_name="outlets")
    op.create_unique_constraint("uq_outlets_tenant_code", "outlets", ["tenant_id", "code"])

    op.add_column("user_outlets", sa.Column("tenant_id", sa.UUID(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE user_outlets AS uo SET tenant_id = u.tenant_id "
            "FROM users AS u WHERE u.id = uo.user_id"
        )
    )
    op.alter_column("user_outlets", "tenant_id", nullable=False)
    op.drop_constraint("fk_user_outlets_user_id_users", "user_outlets", type_="foreignkey")
    op.drop_constraint("fk_user_outlets_outlet_id_outlets", "user_outlets", type_="foreignkey")
    op.create_foreign_key(
        "fk_user_outlets_user_tenant",
        "user_outlets",
        "users",
        ["user_id", "tenant_id"],
        ["id", "tenant_id"],
    )
    op.create_foreign_key(
        "fk_user_outlets_outlet_tenant",
        "user_outlets",
        "outlets",
        ["outlet_id", "tenant_id"],
        ["id", "tenant_id"],
    )

    op.alter_column(
        "transactions",
        "invoice_number",
        existing_type=sa.String(length=30),
        type_=sa.String(length=50),
        existing_nullable=False,
    )


def downgrade() -> None:
    raise RuntimeError(
        "Tenant isolation cannot be safely downgraded while tenant data exists. "
        "Back up and consolidate tenants before restoring the prior schema."
    )
