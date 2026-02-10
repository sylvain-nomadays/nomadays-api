"""Rename GDE cost nature label from Guide to Equipe.

Revision ID: 043_rename_gde_equipe
Revises: 042_transversal_formulas
"""
from alembic import op

revision = "043_rename_gde_equipe"
down_revision = "042_transversal_formulas"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE cost_natures SET label = 'Équipe' WHERE code = 'GDE'")


def downgrade():
    op.execute("UPDATE cost_natures SET label = 'Guide' WHERE code = 'GDE'")
