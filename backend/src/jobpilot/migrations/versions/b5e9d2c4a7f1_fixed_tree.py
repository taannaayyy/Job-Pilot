"""a fixed skill tree the user designs: every node is a skill

Revision ID: b5e9d2c4a7f1
Revises: f2a6c8e1b4d9
Create Date: 2026-10-31 20:00:00.000000

Groups, tags and the shelves the app filed skills on are gone. The tree is made of skills
(parent_id, position) and starts as taxonomy.TREE; a skill already in it keeps its id, so the
postings that ask for it still count. Everything else waits in Unsorted (placed = 0) until the user
places it or the next reading maps it onto the tree.
"""
from alembic import op
import sqlalchemy as sa

from jobpilot.skills import skill_key
from jobpilot.taxonomy import nodes


revision = 'b5e9d2c4a7f1'
down_revision = 'f2a6c8e1b4d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('skill') as batch_op:
        batch_op.drop_constraint('fk_skill_group_id', type_='foreignkey')
        batch_op.drop_index('ix_skill_group_id')
        batch_op.drop_column('group_id')
        batch_op.drop_column('group_locked')
        batch_op.drop_column('tag')
        batch_op.drop_column('category')
        batch_op.add_column(sa.Column('position', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('placed', sa.Boolean(), server_default='0', nullable=False))
    op.drop_table('skill_group')
    seed(op.get_bind())


def seed(conn) -> None:
    conn.execute(sa.text("UPDATE skill SET parent_id = NULL, placed = 0, position = 0"))
    ids: dict[str, int] = {}
    for name, parent, position, _ in nodes():
        key = skill_key(name)
        row = conn.execute(sa.text("SELECT id FROM skill WHERE key = :key OR old_keys LIKE :old"),
                           {"key": key, "old": f"%\n{key}\n%"}).first()
        values = {"name": name, "parent": ids.get(parent), "position": position}
        if row:
            conn.execute(sa.text("UPDATE skill SET parent_id = :parent, position = :position, placed = 1 WHERE id = :id"),
                         {**values, "id": row[0]})
            ids[name] = row[0]
        else:
            ids[name] = conn.execute(sa.text(
                "INSERT INTO skill (name, key, parent_id, position, placed, plan_note, description, old_keys, created_at) "
                "VALUES (:name, :key, :parent, :position, 1, '', '', '', CURRENT_TIMESTAMP) RETURNING id"
            ), {**values, "key": key}).scalar_one()


def downgrade() -> None:
    raise NotImplementedError("The fixed tree can't be turned back into groups")
