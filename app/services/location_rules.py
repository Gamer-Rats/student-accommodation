
"""Location restrictions for student accommodation listings."""

import re


ALLOWED_AREAS = frozenset({
    "st_augustine",
    "mount_hope",
})

LOCATION_ERROR = "area must be St. Augustine or Mount Hope"

AREA_ALIASES = {
    "st augustine": "st_augustine",
    "saint augustine": "st_augustine",
    "mount hope": "mount_hope",
}


def normalize_area(area: str | None) -> str | None:
    """Return a supported canonical area or None."""

    if not isinstance(area, str):
        return None

    normalized = re.sub(
        r"[\s._-]+",
        " ",
        area.casefold(),
    ).strip()

    return AREA_ALIASES.get(normalized)
