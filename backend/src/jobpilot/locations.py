"""Istanbul districts by side. The UI keeps the same list in frontend/src/locations.ts."""

from enum import StrEnum

ISTANBUL = "Istanbul"


class Side(StrEnum):
    ANADOLU = "anadolu"
    AVRUPA = "avrupa"


DISTRICTS: dict[Side, list[str]] = {
    Side.ANADOLU: [
        "Adalar", "Ataşehir", "Beykoz", "Çekmeköy", "Kadıköy", "Kartal", "Maltepe",
        "Pendik", "Sancaktepe", "Sultanbeyli", "Şile", "Tuzla", "Ümraniye", "Üsküdar",
    ],
    Side.AVRUPA: [
        "Arnavutköy", "Avcılar", "Bağcılar", "Bahçelievler", "Bakırköy", "Başakşehir", "Bayrampaşa",
        "Beşiktaş", "Beylikdüzü", "Beyoğlu", "Büyükçekmece", "Çatalca", "Esenler", "Esenyurt",
        "Eyüpsultan", "Fatih", "Gaziosmanpaşa", "Güngören", "Kağıthane", "Küçükçekmece", "Sarıyer",
        "Silivri", "Sultangazi", "Şişli", "Zeytinburnu",
    ],
}

SIDE_OF: dict[str, Side] = {d: side for side, districts in DISTRICTS.items() for d in districts}


def normalize_location(city: str | None, side: Side | str | None, district: str | None):
    """Keep city/side/district consistent: side and district only exist for Istanbul,
    and a known district always implies its side."""
    if city != ISTANBUL:
        return city, None, None
    if district in SIDE_OF:
        return city, SIDE_OF[district], district
    return city, (Side(side) if side else None), district
