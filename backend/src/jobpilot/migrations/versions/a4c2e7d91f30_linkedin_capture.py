"""linkedin capture

Revision ID: a4c2e7d91f30
Revises: 1ce10cf9c0b2
Create Date: 2026-10-29 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from jobpilot.linkedin import job_id_from_url


revision = 'a4c2e7d91f30'
down_revision = '1ce10cf9c0b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('company', schema=None) as batch_op:
        batch_op.add_column(sa.Column('linkedin_slug', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('logo_source', sa.String(length=20), nullable=True))
        batch_op.create_index(batch_op.f('ix_company_linkedin_slug'), ['linkedin_slug'], unique=True)

    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('linkedin_job_id', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('raw_text', sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f('ix_job_linkedin_job_id'), ['linkedin_job_id'], unique=True)

    # Jobs saved by hand from a LinkedIn link get their job ID, so capturing them again is caught.
    conn = op.get_bind()
    seen = set()
    for job_id, url in conn.execute(sa.text("SELECT id, url FROM job ORDER BY id")).all():
        linkedin_id = job_id_from_url(url)
        if linkedin_id and linkedin_id not in seen:
            seen.add(linkedin_id)
            conn.execute(sa.text("UPDATE job SET linkedin_job_id = :l WHERE id = :i"), {"l": linkedin_id, "i": job_id})


def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_linkedin_job_id'))
        batch_op.drop_column('raw_text')
        batch_op.drop_column('linkedin_job_id')

    with op.batch_alter_table('company', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_company_linkedin_slug'))
        batch_op.drop_column('logo_source')
        batch_op.drop_column('linkedin_slug')
