"""a skill is a concept or a tool: tools are things you can point to ("Docker")

Revision ID: b3d5f7a9c1e2
Revises: a7c9e1f3b5d6
Create Date: 2026-11-01 12:00:00.000000

The starting tree's tools (taxonomy.TOOLS) are marked as tools; every other skill starts as a concept.
"""
from alembic import op
import sqlalchemy as sa

from jobpilot.skills import skill_key
from jobpilot.taxonomy import TOOLS


revision = 'b3d5f7a9c1e2'
down_revision = 'a7c9e1f3b5d6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('skill') as batch_op:
        batch_op.add_column(sa.Column('is_tool', sa.Boolean(), server_default='0', nullable=False))
    conn = op.get_bind()
    for name in TOOLS:
        conn.execute(sa.text("UPDATE skill SET is_tool = 1 WHERE key = :key AND is_group = 0"), {"key": skill_key(name)})


def downgrade() -> None:
    with op.batch_alter_table('skill') as batch_op:
        batch_op.drop_column('is_tool')
