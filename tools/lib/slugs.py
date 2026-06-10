"""
slugs.py · single source of the i18n key slug discipline.

shared by the source registry (generate_source_view.py) and the source
reader (generate_source_reader.py), so `source.files.<slug>.description`
keys resolve identically on both surfaces — en + fr translations populate
the registry rows and the reader page from one key set.
"""

from __future__ import annotations


def i18n_slug(name: str) -> str:
    """convert a mirror name to a stable i18n key slug.

    collapses every non-alphanumeric character to a single
    underscore, lowercases, and trims edge underscores. the
    full name (including any `.txt` mirror suffix) is preserved
    so that the readable mirror and the live canonical file are
    distinguishable as separate keys — e.g. `sitemap.xml.sha256`
    (live verification artefact) vs `sitemap.xml.sha256.txt`
    (its readable source mirror) slugify to different keys.

    examples:
      index.html.txt              → index_html_txt
      .well-known/person.json.txt → well_known_person_json_txt
      i18n/it.js.txt              → i18n_it_js_txt
      htaccess.txt                → htaccess_txt
      integrity.json              → integrity_json
      SHA256SUMS                  → sha256sums
    """
    out: list[str] = []
    last_under = True
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
            last_under = False
        elif not last_under:
            out.append("_")
            last_under = True
    return "".join(out).strip("_")
