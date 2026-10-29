"""skill gap

Revision ID: 5d0da09ff390
Revises: a4c2e7d91f30
Create Date: 2026-10-30 00:02:09.100464
"""
from alembic import op
import sqlalchemy as sa
import jobpilot.db


revision = '5d0da09ff390'
down_revision = 'a4c2e7d91f30'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('role_group',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('created_at', jobpilot.db.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('skill',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('key', sa.String(length=200), nullable=False),
    sa.Column('category', sa.String(length=30), nullable=False),
    sa.Column('mark', sa.String(length=10), nullable=True),
    sa.Column('plan_note', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', jobpilot.db.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('skill_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.Column('from_mark', sa.String(length=10), nullable=True),
    sa.Column('to_mark', sa.String(length=10), nullable=True),
    sa.Column('timestamp', jobpilot.db.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['skill_id'], ['skill.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('skill_event', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_skill_event_skill_id'), ['skill_id'], unique=False)

    op.create_table('requirement',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('skill_id', sa.Integer(), nullable=False),
    sa.Column('importance', sa.String(length=10), nullable=False),
    sa.Column('evidence', sa.String(length=500), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['job.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['skill_id'], ['skill.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_id', 'skill_id')
    )
    with op.batch_alter_table('requirement', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_requirement_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_requirement_skill_id'), ['skill_id'], unique=False)

    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_group_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('study_only', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('extraction_status', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('extraction_error', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('extracted_at', jobpilot.db.UTCDateTime(), nullable=True))
        batch_op.add_column(sa.Column('extracted_with', sa.String(length=200), nullable=True))
        batch_op.create_index(batch_op.f('ix_job_target_group_id'), ['target_group_id'], unique=False)
        batch_op.create_foreign_key('fk_job_target_group_id', 'role_group', ['target_group_id'], ['id'], ondelete='SET NULL')



def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_constraint('fk_job_target_group_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_job_target_group_id'))
        batch_op.drop_column('extracted_with')
        batch_op.drop_column('extracted_at')
        batch_op.drop_column('extraction_error')
        batch_op.drop_column('extraction_status')
        batch_op.drop_column('study_only')
        batch_op.drop_column('target_group_id')

    with op.batch_alter_table('requirement', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_requirement_skill_id'))
        batch_op.drop_index(batch_op.f('ix_requirement_job_id'))

    op.drop_table('requirement')
    with op.batch_alter_table('skill_event', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_skill_event_skill_id'))

    op.drop_table('skill_event')
    op.drop_table('skill')
    op.drop_table('role_group')
