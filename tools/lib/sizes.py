"""
sizes.py · single source of truth for byte-count formatting.

every generator that needs to render a filesize uses humanise_bytes().
the byte count itself is the canonical value; the formatted label is
a pure function of the byte count and the locale.

unit convention: 1024-based (kibibytes), labelled "KB"/"MB" colloquially
in english and "Ko"/"Mo" in french. this matches the historical formatter
output across generate_source_view.py, generate_verification_map.py and
generate_site.py, so adopting this helper does not silently rewrite any
existing displayed number outside known rounding edges.
"""

from __future__ import annotations

_KB = 1024
_MB = 1024 * 1024

_UNITS = {
    "en": {"b_one": "byte", "b_many": "bytes", "kb": "KB", "mb": "MB"},
    "fr": {"b_one": "octet", "b_many": "octets", "kb": "Ko", "mb": "Mo"},
}


def humanise_bytes(n: int, *, lang: str = "en") -> str:
    """format a non-negative byte count as a localised human label.

    < 1024 bytes     → "842 bytes" / "842 octets"
    < 1 MiB          → "27.0 KB" / "27,0 Ko" (one decimal, comma in french)
    ≥ 1 MiB          → "1.4 MB" / "1,4 Mo"

    edge case for sub-kilobyte singular is handled in english only
    ("1 byte"); french uses "octets" uniformly per usage convention.
    """
    if n < 0:
        raise ValueError(f"humanise_bytes: negative byte count {n}")
    units = _UNITS.get(lang, _UNITS["en"])
    if n < _KB:
        label = units["b_one"] if (lang == "en" and n == 1) else units["b_many"]
        return f"{n} {label}"
    if n < _MB:
        value = n / _KB
        return _format_decimal(value, lang) + " " + units["kb"]
    value = n / _MB
    return _format_decimal(value, lang) + " " + units["mb"]


def _format_decimal(value: float, lang: str) -> str:
    """one decimal place; french uses comma as decimal separator."""
    formatted = f"{value:.1f}"
    if lang == "fr":
        formatted = formatted.replace(".", ",")
    return formatted


__all__ = ["humanise_bytes"]
