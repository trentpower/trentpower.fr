#!/usr/bin/env python3
"""Site-specific content-consistency anchors.

Checks editorial invariants unique to trentpower.fr: the footer colophon links to
the language's verify page, the edition string is consistent across meta/footer/
body and matches /site-metadata.json, the Under Construction rail is present, the
French machine-translation disclosure is present on /fr/, and /local/ is noindex.
Per-target; category content_consistency (tool name avoids the content_integrity
collision while sharing the matrix column).
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import lib
from bs4 import BeautifulSoup

TOOL = "content_anchors"
CATEGORY = "content_consistency"

_CACHE = {}


def _origin(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _edition(origin, cfg, http):
    if ("edition", origin) not in _CACHE:
        try:
            r = lib.fetch(http, origin + "/site-metadata.json", cfg)
            ed = (r.json().get("edition") or {}).get("id") if r.status_code == 200 else None
        except Exception:
            ed = None
        _CACHE[("edition", origin)] = ed
    return _CACHE[("edition", origin)]


def _local_noindex(origin, cfg, http):
    if ("local", origin) not in _CACHE:
        try:
            r = lib.fetch(http, origin + "/local/", cfg, allow_redirects=True)
            soup = BeautifulSoup(r.text, "lxml")
            tag = soup.find("meta", attrs={"name": "robots"})
            _CACHE[("local", origin)] = bool(
                tag and "noindex" in (tag.get("content") or "").lower()
            )
        except Exception:
            _CACHE[("local", origin)] = None
    return _CACHE[("local", origin)]


def _lang(path):
    seg = [s for s in path.split("/") if s]
    return seg[0] if seg else "root"


def run(target_url, cfg, http):
    origin = _origin(target_url)
    path = lib.path_of(target_url)
    lang = _lang(path)
    resp = lib.fetch(http, target_url, cfg, allow_redirects=True)
    soup = BeautifulSoup(resp.text, "lxml")
    edition = _edition(origin, cfg, http)

    # verify link (editions only; root gate is vacuously satisfied)
    if lang in ("en-au", "fr"):
        verify_present = any(
            (a.get("href") or "").startswith(f"/{lang}/")
            and ("verify" in a.get("href") or "verifier" in a.get("href"))
            for a in soup.find_all("a", href=True)
        )
    else:
        verify_present = True

    # edition consistency across markers vs site-metadata
    # Authoritative edition markers only - NOT arbitrary <time> elements (the
    # page carries biographical dates like 1997 that are not the edition).
    markers = []
    meta_ed = soup.find("meta", attrs={"name": "document-edition"})
    if meta_ed and meta_ed.get("content"):
        markers.append(meta_ed["content"].strip())
    body = soup.find("body")
    if body and body.get("data-edition"):
        markers.append(body["data-edition"].strip())
    colo = soup.select_one(".site-footer__colophon-link time[datetime]")
    if colo and colo.get("datetime"):
        markers.append(colo["datetime"].strip())
    found_edition = markers[0] if markers else None
    if edition and markers:
        edition_consistent = all(m == edition for m in markers)
    elif markers:
        edition_consistent = len(set(markers)) == 1
    else:
        edition_consistent = True  # vacuous (gate page may carry no edition marker)

    rail = bool(soup.select_one("[data-construction-rail]"))
    if lang == "fr":
        fr_disclosure = bool(soup.select_one("[data-translation-disclosure]"))
    else:
        fr_disclosure = True  # vacuous off /fr/

    measurements = [
        lib.measurement(CATEGORY, "content_anchors.verify_link_present", value_bool=verify_present),
        lib.measurement(
            CATEGORY, "content_anchors.edition_consistent", value_bool=edition_consistent
        ),
        lib.measurement(CATEGORY, "content_anchors.construction_rail_present", value_bool=rail),
        lib.measurement(
            CATEGORY, "content_anchors.fr_disclosure_present", value_bool=fr_disclosure
        ),
    ]
    if found_edition:
        measurements.append(
            lib.measurement(CATEGORY, "content_anchors.edition.text", value_text=found_edition)
        )
    # /local/ noindex is site-level; emit on root only
    if path == "/":
        ln = _local_noindex(origin, cfg, http)
        if ln is not None:
            measurements.append(
                lib.measurement(CATEGORY, "content_anchors.local_noindex", value_bool=ln)
            )

    observations = []
    if not verify_present:
        observations.append(
            lib.observation(
                metric="content_anchors.verify_link_present",
                severity="error",
                observation_type="content",
                code="VERIFY_LINK_MISSING",
                title=f"{path} footer has no verify link",
                message="expected a /<lang>/verify link",
                url=target_url,
                fingerprint=f"content:verify-link:{path}",
            )
        )
    if not edition_consistent:
        observations.append(
            lib.observation(
                metric="content_anchors.edition_consistent",
                severity="error",
                observation_type="content",
                code="EDITION_INCONSISTENT",
                title=f"{path} edition markers inconsistent",
                message=f"markers={markers} site-metadata={edition}",
                url=target_url,
                fingerprint=f"content:edition:{path}",
                evidence=[
                    lib.evidence("list", "markers", ", ".join(markers)),
                    lib.evidence("text", "site-metadata", edition or "-"),
                ],
            )
        )
    if not rail:
        observations.append(
            lib.observation(
                metric="content_anchors.construction_rail_present",
                severity="warning",
                observation_type="content",
                code="CONSTRUCTION_RAIL_MISSING",
                title=f"{path} Under Construction rail absent",
                message="[data-construction-rail] not found",
                url=target_url,
                fingerprint=f"content:rail:{path}",
            )
        )
    if lang == "fr" and not fr_disclosure:
        observations.append(
            lib.observation(
                metric="content_anchors.fr_disclosure_present",
                severity="error",
                observation_type="content",
                code="FR_DISCLOSURE_MISSING",
                title="/fr/ machine-translation disclosure absent",
                message="[data-translation-disclosure] not found on /fr/",
                url=target_url,
                fingerprint="content:fr-disclosure:/fr/",
            )
        )

    status = (
        "error"
        if any(o["severity"] == "error" for o in observations)
        else ("warning" if observations else "ok")
    )
    return lib.result(
        target_url,
        TOOL,
        status,
        measurements=measurements,
        observations=observations,
        raw_json={
            "lang": lang,
            "edition": edition,
            "markers": markers,
            "verify_present": verify_present,
            "rail": rail,
        },
    )
