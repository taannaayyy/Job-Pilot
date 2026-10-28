"""company website and city district

Revision ID: 78178a8c7016
Revises: 763b6336e788
Create Date: 2026-10-29 00:15:15.265896
"""
from alembic import op
import sqlalchemy as sa


revision = '78178a8c7016'
down_revision = '763b6336e788'
branch_labels = None
depends_on = None

# Frozen copy of the district list at the time of this migration.
ISTANBUL_DISTRICTS = [
    "Adalar", "Ataşehir", "Beykoz", "Çekmeköy", "Kadıköy", "Kartal", "Maltepe", "Pendik",
    "Sancaktepe", "Sultanbeyli", "Şile", "Tuzla", "Ümraniye", "Üsküdar",
    "Arnavutköy", "Avcılar", "Bağcılar", "Bahçelievler", "Bakırköy", "Başakşehir", "Bayrampaşa",
    "Beşiktaş", "Beylikdüzü", "Beyoğlu", "Büyükçekmece", "Çatalca", "Esenler", "Esenyurt",
    "Eyüpsultan", "Fatih", "Gaziosmanpaşa", "Güngören", "Kağıthane", "Küçükçekmece", "Sarıyer",
    "Silivri", "Sultangazi", "Şişli", "Zeytinburnu",
]


def _fold(text: str) -> str:
    """Case- and accent-insensitive key, so 'kadikoy' and 'KADIKÖY' match 'Kadıköy'."""
    table = str.maketrans("ıİçÇğĞöÖşŞüÜ", "iiccggoossuu")
    return text.translate(table).casefold().replace("̇", "").strip()


def _split_location(location: str) -> tuple[str | None, str | None]:
    """'Istanbul, Pendik' -> ('Istanbul', 'Pendik'); 'Ankara' -> ('Ankara', None)."""
    districts = {_fold(d): d for d in ISTANBUL_DISTRICTS}
    parts = [p.strip() for p in location.replace("/", ",").split(",") if p.strip()]
    district = next((districts[_fold(p)] for p in parts if _fold(p) in districts), None)
    is_istanbul = district is not None or any(_fold(p) == "istanbul" for p in parts)
    if is_istanbul:
        return "Istanbul", district
    return (location.strip() or None), None


def upgrade() -> None:
    with op.batch_alter_table('company', schema=None) as batch_op:
        batch_op.add_column(sa.Column('website', sa.String(length=300), nullable=True))

    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('city', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('district', sa.String(length=100), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, location FROM job WHERE location IS NOT NULL")).fetchall()
    for job_id, location in rows:
        city, district = _split_location(location)
        conn.execute(
            sa.text("UPDATE job SET city = :city, district = :district WHERE id = :id"),
            {"city": city, "district": district, "id": job_id},
        )

    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('location')


def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location', sa.VARCHAR(length=200), nullable=True))

    op.execute(
        "UPDATE job SET location = CASE WHEN district IS NOT NULL THEN city || ', ' || district ELSE city END"
    )

    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('district')
        batch_op.drop_column('city')

    with op.batch_alter_table('company', schema=None) as batch_op:
        batch_op.drop_column('website')
