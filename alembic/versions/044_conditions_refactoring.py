"""Refactor conditions: add condition_options, trip_conditions tables,
add formulas.condition_option_id, make conditions.trip_id nullable.

Additive migration — nothing is dropped. Cleanup in a later migration.

Revision ID: 044_conditions_refactoring
Revises: 043_rename_gde_equipe
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "044_conditions_refactoring"
down_revision = "043_rename_gde_equipe"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Create condition_options table ──────────────────────────────
    op.create_table(
        "condition_options",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("condition_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["condition_id"], ["conditions.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
        ),
    )
    op.create_index("idx_condition_options_tenant_id", "condition_options", ["tenant_id"])
    op.create_index("idx_condition_options_condition_id", "condition_options", ["condition_id"])

    # ── 2. Create trip_conditions table ────────────────────────────────
    op.create_table(
        "trip_conditions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", sa.BigInteger(), nullable=False),
        sa.Column("condition_id", sa.BigInteger(), nullable=False),
        sa.Column("selected_option_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["condition_id"], ["conditions.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["selected_option_id"], ["condition_options.id"], ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint("trip_id", "condition_id", name="uq_trip_conditions_trip_condition"),
    )
    op.create_index("idx_trip_conditions_tenant_id", "trip_conditions", ["tenant_id"])
    op.create_index("idx_trip_conditions_trip_id", "trip_conditions", ["trip_id"])
    op.create_index("idx_trip_conditions_condition_id", "trip_conditions", ["condition_id"])

    # ── 3. Make conditions.trip_id nullable (was NOT NULL) ─────────────
    op.alter_column("conditions", "trip_id", existing_type=sa.BigInteger(), nullable=True)

    # ── 4. Add condition_option_id to formulas ─────────────────────────
    op.add_column(
        "formulas",
        sa.Column("condition_option_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_formulas_condition_option",
        "formulas",
        "condition_options",
        ["condition_option_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_formulas_condition_option_id", "formulas", ["condition_option_id"])

    # ── 5. Data migration: convert existing trip-scoped conditions ─────
    # For each existing condition:
    #   a) Create 2 options: "Actif" and "Inactif"
    #   b) Create a TripCondition linking the old trip to this condition
    #   c) Set condition_option_id on formulas whose items reference this condition
    #   d) Clear trip_id to make it tenant-scoped
    conn = op.get_bind()

    rows = conn.execute(
        sa.text("SELECT id, tenant_id, trip_id, is_active FROM conditions WHERE trip_id IS NOT NULL")
    ).fetchall()

    for row in rows:
        cond_id = row[0]
        tenant_id = row[1]
        trip_id = row[2]
        is_active = row[3]

        # a) Create "Actif" option
        result = conn.execute(
            sa.text(
                "INSERT INTO condition_options (tenant_id, condition_id, label, sort_order) "
                "VALUES (:tenant_id, :condition_id, 'Actif', 0) RETURNING id"
            ),
            {"tenant_id": tenant_id, "condition_id": cond_id},
        )
        actif_option_id = result.fetchone()[0]

        # Create "Inactif" option
        conn.execute(
            sa.text(
                "INSERT INTO condition_options (tenant_id, condition_id, label, sort_order) "
                "VALUES (:tenant_id, :condition_id, 'Inactif', 1)"
            ),
            {"tenant_id": tenant_id, "condition_id": cond_id},
        )

        # b) Create TripCondition
        conn.execute(
            sa.text(
                "INSERT INTO trip_conditions (tenant_id, trip_id, condition_id, selected_option_id, is_active) "
                "VALUES (:tenant_id, :trip_id, :condition_id, :selected_option_id, :is_active)"
            ),
            {
                "tenant_id": tenant_id,
                "trip_id": trip_id,
                "condition_id": cond_id,
                "selected_option_id": actif_option_id,
                "is_active": is_active,
            },
        )

        # c) Set condition_option_id on formulas that have items with this condition_id
        conn.execute(
            sa.text(
                "UPDATE formulas SET condition_option_id = :opt_id "
                "WHERE id IN (SELECT DISTINCT formula_id FROM items WHERE condition_id = :cond_id)"
            ),
            {"opt_id": actif_option_id, "cond_id": cond_id},
        )

        # d) Clear trip_id to make the condition tenant-scoped
        conn.execute(
            sa.text("UPDATE conditions SET trip_id = NULL WHERE id = :id"),
            {"id": cond_id},
        )


def downgrade():
    # Reverse data migration: restore trip_id on conditions from trip_conditions
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE conditions c SET trip_id = tc.trip_id "
            "FROM trip_conditions tc WHERE tc.condition_id = c.id AND c.trip_id IS NULL"
        )
    )

    # Remove formulas.condition_option_id
    op.drop_index("idx_formulas_condition_option_id")
    op.drop_constraint("fk_formulas_condition_option", "formulas", type_="foreignkey")
    op.drop_column("formulas", "condition_option_id")

    # Restore conditions.trip_id NOT NULL
    op.alter_column("conditions", "trip_id", existing_type=sa.BigInteger(), nullable=False)

    # Drop trip_conditions
    op.drop_index("idx_trip_conditions_condition_id")
    op.drop_index("idx_trip_conditions_trip_id")
    op.drop_index("idx_trip_conditions_tenant_id")
    op.drop_table("trip_conditions")

    # Drop condition_options
    op.drop_index("idx_condition_options_condition_id")
    op.drop_index("idx_condition_options_tenant_id")
    op.drop_table("condition_options")
