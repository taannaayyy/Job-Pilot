"""skills filed general to specific, named technologies as leaves

Revision ID: f2a6c8e1b4d9
Revises: e7d4b9a1c2f3
Create Date: 2026-10-31 18:00:00.000000

Machine learning is split into Classical ML, Deep learning (Computer vision, NLP) and Generative AI,
and a named model, tool or database no longer holds other skills. Skills the user didn't place lose
their parent and tag; the dictionary files its skills again when the app starts, the next reading
files the rest.
"""
from alembic import op


revision = 'f2a6c8e1b4d9'
down_revision = 'e7d4b9a1c2f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE skill SET parent_id = NULL, tag = NULL WHERE group_locked = 0")


def downgrade() -> None:
    pass
