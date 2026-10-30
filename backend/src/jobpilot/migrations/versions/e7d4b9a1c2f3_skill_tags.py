"""skill tags, and the tree reorganized by topic

Revision ID: e7d4b9a1c2f3
Revises: c3f1a8d2e4b7
Create Date: 2026-10-31 10:00:00.000000

The tree no longer splits Technologies from Knowledge areas: groups are topics, depth comes from
skills under skills, and what kind of thing a skill is moves to its tag. The old groups are replaced
by the new starting tree; skills lose their place and are filed again by the next reading (the
dictionary's at once, when the app starts).
"""
from alembic import op
import sqlalchemy as sa



revision = 'e7d4b9a1c2f3'
down_revision = 'c3f1a8d2e4b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('skill') as batch_op:
        batch_op.add_column(sa.Column('tag', sa.String(length=20), nullable=True))
    op.execute("UPDATE skill SET group_id = NULL, parent_id = NULL, group_locked = 0, tag = NULL")
    # The new groups were seeded here; the tree is now made of skills (b5e9d2c4a7f1).
    op.execute("DELETE FROM skill_group")


def downgrade() -> None:
    with op.batch_alter_table('skill') as batch_op:
        batch_op.drop_column('tag')
