"""skill tree

Revision ID: 9b7a0e3aed61
Revises: 5d0da09ff390
Create Date: 2026-10-30 02:13:27.539534
"""
from alembic import op
import sqlalchemy as sa


revision = '9b7a0e3aed61'
down_revision = '5d0da09ff390'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('skill_group',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=50), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('position', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['skill_group.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    with op.batch_alter_table('skill_group', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_skill_group_parent_id'), ['parent_id'], unique=False)

    with op.batch_alter_table('requirement', schema=None) as batch_op:
        batch_op.add_column(sa.Column('min_years', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('max_years', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('detail', sa.String(length=500), nullable=True))

    with op.batch_alter_table('skill', schema=None) as batch_op:
        batch_op.add_column(sa.Column('group_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('group_locked', sa.Boolean(), server_default='0', nullable=False))
        batch_op.create_index(batch_op.f('ix_skill_group_id'), ['group_id'], unique=False)
        batch_op.create_foreign_key('fk_skill_parent_id', 'skill', ['parent_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_skill_group_id', 'skill_group', ['group_id'], ['id'], ondelete='SET NULL')

    # The starting groups were seeded here; the tree is now made of skills (b5e9d2c4a7f1).


def downgrade() -> None:
    with op.batch_alter_table('skill', schema=None) as batch_op:
        batch_op.drop_constraint('fk_skill_group_id', type_='foreignkey')
        batch_op.drop_constraint('fk_skill_parent_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_skill_group_id'))
        batch_op.drop_column('group_locked')
        batch_op.drop_column('parent_id')
        batch_op.drop_column('group_id')

    with op.batch_alter_table('requirement', schema=None) as batch_op:
        batch_op.drop_column('detail')
        batch_op.drop_column('max_years')
        batch_op.drop_column('min_years')

    with op.batch_alter_table('skill_group', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_skill_group_parent_id'))

    op.drop_table('skill_group')
