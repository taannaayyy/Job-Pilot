"""where in the description a skill's words were selected, so only they are highlighted

Revision ID: a7c9e1f3b5d6
Revises: c4e6f8a0b2d4
Create Date: 2026-10-31 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7c9e1f3b5d6'
down_revision = 'c4e6f8a0b2d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('requirement') as batch_op:
        batch_op.add_column(sa.Column('evidence_at', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('requirement') as batch_op:
        batch_op.drop_column('evidence_at')
