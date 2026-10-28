"""job side

Revision ID: ea5bf5b739be
Revises: 78178a8c7016
Create Date: 2026-10-29 01:18:05.338897
"""
from alembic import op
import sqlalchemy as sa


revision = 'ea5bf5b739be'
down_revision = '78178a8c7016'
branch_labels = None
depends_on = None

# Frozen copy of the district list at the time of this migration.
ANADOLU = [
    "Adalar", "Ataşehir", "Beykoz", "Çekmeköy", "Kadıköy", "Kartal", "Maltepe",
    "Pendik", "Sancaktepe", "Sultanbeyli", "Şile", "Tuzla", "Ümraniye", "Üsküdar",
]
AVRUPA = [
    "Arnavutköy", "Avcılar", "Bağcılar", "Bahçelievler", "Bakırköy", "Başakşehir", "Bayrampaşa",
    "Beşiktaş", "Beylikdüzü", "Beyoğlu", "Büyükçekmece", "Çatalca", "Esenler", "Esenyurt",
    "Eyüpsultan", "Fatih", "Gaziosmanpaşa", "Güngören", "Kağıthane", "Küçükçekmece", "Sarıyer",
    "Silivri", "Sultangazi", "Şişli", "Zeytinburnu",
]


def upgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('side', sa.String(length=10), nullable=True))

    # Existing jobs: the side follows from the district.
    job = sa.table('job', sa.column('city'), sa.column('district'), sa.column('side'))
    for side, districts in (("anadolu", ANADOLU), ("avrupa", AVRUPA)):
        op.execute(
            job.update()
            .where(job.c.city == "Istanbul", job.c.district.in_(districts))
            .values(side=side)
        )


def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('side')
