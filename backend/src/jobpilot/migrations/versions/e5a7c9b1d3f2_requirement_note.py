"""the user's own note on a skill a job asks for, written on its words in the description

Revision ID: e5a7c9b1d3f2
Revises: d2b4f6a8c0e1
Create Date: 2026-11-03 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5a7c9b1d3f2'
down_revision = 'd2b4f6a8c0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('requirement') as batch_op:
        batch_op.add_column(sa.Column('note', sa.Text(), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('requirement') as batch_op:
        batch_op.drop_column('note')
