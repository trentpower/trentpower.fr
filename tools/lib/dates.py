"""
dates.py · single source of truth for the human edition-date forms.

the edition date appears on public surfaces as "2 May 2026" (en) and
"2 mai 2026" (fr). the month tables and the rendering rule were copied
into six tools; they live here now so the written form and its
validators can never disagree.

human_date() accepts either a date/datetime or the canonical
"YYYY-MM-DD" edition string, since callers hold both shapes.
"""

from __future__ import annotations

import datetime as _dt

LOCALE_MONTHS = {
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "fr": [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ],
}


def human_date(value, *, lang: str = "en") -> str:
    """render an edition date in the locale's human form.

    en → "2 May 2026" · fr → "2 mai 2026". `value` is a date,
    a datetime, or the canonical "YYYY-MM-DD" string. None → "".
    """
    if value is None:
        return ""
    if isinstance(value, str):
        y, m, d = (int(part) for part in value.split("-"))
        value = _dt.date(y, m, d)
    months = LOCALE_MONTHS.get(lang, LOCALE_MONTHS["en"])
    return f"{value.day} {months[value.month - 1]} {value.year}"


__all__ = ["LOCALE_MONTHS", "human_date"]
