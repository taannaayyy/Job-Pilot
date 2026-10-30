"""groups in the skill tree: nodes that only organize

Revision ID: d8f1a3b6c2e5
Revises: b5e9d2c4a7f1
Create Date: 2026-11-01 10:00:00.000000

A group ("Cloud") holds skills and is never asked for itself. The starting tree's containers
(taxonomy.TREE, in brackets) become groups when they are still in the tree.
"""
from alembic import op
import sqlalchemy as sa

from jobpilot.skills import skill_key
from jobpilot.taxonomy import nodes


revision = 'd8f1a3b6c2e5'
down_revision = 'b5e9d2c4a7f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('skill') as batch_op:
        batch_op.add_column(sa.Column('is_group', sa.Boolean(), server_default='0', nullable=False))
    conn = op.get_bind()
    for name, _, _, group in nodes():
        if group:
            conn.execute(sa.text("UPDATE skill SET is_group = 1 WHERE key = :key AND placed = 1"), {"key": skill_key(name)})


def downgrade() -> None:
    with op.batch_alter_table('skill') as batch_op:
        batch_op.drop_column('is_group')
