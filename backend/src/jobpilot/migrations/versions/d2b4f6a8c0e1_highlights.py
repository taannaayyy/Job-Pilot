"""words highlighted in a job description to read again, without adding them as a skill

Revision ID: d2b4f6a8c0e1
Revises: b3d5f7a9c1e2
Create Date: 2026-11-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2b4f6a8c0e1'
down_revision = 'b3d5f7a9c1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('job') as batch_op:
        batch_op.add_column(sa.Column('highlights', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('job') as batch_op:
        batch_op.drop_column('highlights')
