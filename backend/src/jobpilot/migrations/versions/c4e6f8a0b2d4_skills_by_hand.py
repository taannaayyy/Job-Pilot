"""skills are connected to postings by hand: nothing reads job descriptions

Revision ID: c4e6f8a0b2d4
Revises: d8f1a3b6c2e5
Create Date: 2026-11-01 14:00:00.000000

The reading status of a job goes. The connections already made stay (the user removes what they
disagree with); the ones the user had removed, kept only so a reading wouldn't add them back, go.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4e6f8a0b2d4'
down_revision = 'd8f1a3b6c2e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('job') as batch_op:
        batch_op.drop_column('extraction_status')
        batch_op.drop_column('extraction_error')
        batch_op.drop_column('extracted_at')
        batch_op.drop_column('extracted_with')
    op.execute("DELETE FROM requirement WHERE source = 'removed'")


def downgrade() -> None:
    with op.batch_alter_table('job') as batch_op:
        batch_op.add_column(sa.Column('extraction_status', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('extraction_error', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('extracted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('extracted_with', sa.String(length=200), nullable=True))
