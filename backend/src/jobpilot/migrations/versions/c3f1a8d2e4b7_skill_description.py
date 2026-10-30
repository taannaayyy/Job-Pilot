"""skill description and old names

Revision ID: c3f1a8d2e4b7
Revises: 9b7a0e3aed61
Create Date: 2026-10-30 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3f1a8d2e4b7'
down_revision = '9b7a0e3aed61'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('skill') as batch_op:
        batch_op.add_column(sa.Column('description', sa.Text(), server_default='', nullable=False))
        batch_op.add_column(sa.Column('old_keys', sa.Text(), server_default='', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('skill') as batch_op:
        batch_op.drop_column('old_keys')
        batch_op.drop_column('description')
