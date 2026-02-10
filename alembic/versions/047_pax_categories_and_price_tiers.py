"""Add pax_categories, item_price_tiers tables and tier_categories column.

Introduces configurable PAX categories (tourist/staff/leader) per tenant,
tiered pricing per pax count on items, and a tier_categories selector
to control which categories count for tier selection.

Seeds default pax categories for all existing tenants.

Revision ID: 047
Revises: 046
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision = "047_pax_cats_price_tiers"
down_revision = "046_condition_applies_to"
branch_labels = None
depends_on = None


# Default pax categories to seed for every tenant
DEFAULT_PAX_CATEGORIES = [
    {"code": "adult", "label": "Adulte", "group_type": "tourist", "age_min": 18, "age_max": None, "counts_for_pricing": True, "is_system": True, "sort_order": 1},
    {"code": "teen", "label": "Teenager (11-16)", "group_type": "tourist", "age_min": 11, "age_max": 16, "counts_for_pricing": True, "is_system": True, "sort_order": 2},
    {"code": "child", "label": "Enfant (2-10)", "group_type": "tourist", "age_min": 2, "age_max": 10, "counts_for_pricing": True, "is_system": True, "sort_order": 3},
    {"code": "baby", "label": "Bébé (-2 ans)", "group_type": "tourist", "age_min": 0, "age_max": 1, "counts_for_pricing": True, "is_system": True, "sort_order": 4},
    {"code": "tour_leader", "label": "Tour Leader", "group_type": "leader", "age_min": None, "age_max": None, "counts_for_pricing": False, "is_system": True, "sort_order": 5},
    {"code": "guide", "label": "Guide", "group_type": "staff", "age_min": None, "age_max": None, "counts_for_pricing": True, "is_system": True, "sort_order": 10},
    {"code": "driver", "label": "Chauffeur", "group_type": "staff", "age_min": None, "age_max": None, "counts_for_pricing": True, "is_system": True, "sort_order": 11},
    {"code": "cook", "label": "Cuisinier", "group_type": "staff", "age_min": None, "age_max": None, "counts_for_pricing": True, "is_system": True, "sort_order": 12},
]


def upgrade() -> None:
    # ── 1. pax_categories table ──────────────────────────────────────────
    op.create_table(
        "pax_categories",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("group_type", sa.String(20), nullable=False, server_default="tourist"),
        sa.Column("age_min", sa.Integer, nullable=True),
        sa.Column("age_max", sa.Integer, nullable=True),
        sa.Column("counts_for_pricing", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_pax_categories_tenant", "pax_categories", ["tenant_id"])
    op.create_unique_constraint("uk_pax_cat_tenant_code", "pax_categories", ["tenant_id", "code"])

    # ── 2. item_price_tiers table ────────────────────────────────────────
    op.create_table(
        "item_price_tiers",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.BigInteger, sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pax_min", sa.Integer, nullable=False),
        sa.Column("pax_max", sa.Integer, nullable=False),
        sa.Column("unit_cost", sa.DECIMAL(12, 2), nullable=False),
        sa.Column("category_adjustments_json", sa.JSON, nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_tiers_item", "item_price_tiers", ["item_id"])
    op.create_index("idx_tiers_tenant", "item_price_tiers", ["tenant_id"])

    # ── 3. tier_categories column on items ───────────────────────────────
    op.add_column(
        "items",
        sa.Column("tier_categories", sa.String(255), nullable=True),
    )

    # ── 4. Seed default pax categories for all existing tenants ──────────
    conn = op.get_bind()
    tenants = conn.execute(sa.text("SELECT id FROM tenants")).fetchall()

    if tenants:
        for tenant in tenants:
            tenant_id = tenant[0]
            for cat in DEFAULT_PAX_CATEGORIES:
                conn.execute(
                    sa.text(
                        "INSERT INTO pax_categories "
                        "(tenant_id, code, label, group_type, age_min, age_max, "
                        "counts_for_pricing, is_active, is_system, sort_order) "
                        "VALUES (:tenant_id, :code, :label, :group_type, :age_min, :age_max, "
                        ":counts_for_pricing, true, :is_system, :sort_order)"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "code": cat["code"],
                        "label": cat["label"],
                        "group_type": cat["group_type"],
                        "age_min": cat["age_min"],
                        "age_max": cat["age_max"],
                        "counts_for_pricing": cat["counts_for_pricing"],
                        "is_system": cat["is_system"],
                        "sort_order": cat["sort_order"],
                    },
                )


def downgrade() -> None:
    op.drop_column("items", "tier_categories")
    op.drop_index("idx_tiers_tenant", table_name="item_price_tiers")
    op.drop_index("idx_tiers_item", table_name="item_price_tiers")
    op.drop_table("item_price_tiers")
    op.drop_unique_constraint("uk_pax_cat_tenant_code", table_name="pax_categories")
    op.drop_index("idx_pax_categories_tenant", table_name="pax_categories")
    op.drop_table("pax_categories")
