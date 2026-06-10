#!/usr/bin/env python3
"""Metadata validator: title, description, canonical, lang, viewport, OG, hreflang."""

from __future__ import annotations

import lib
from bs4 import BeautifulSoup

TOOL = "metadata"
CATEGORY = "metadata"


def run(target_url, cfg, http):
    resp = lib.fetch(http, target_url, cfg, allow_redirects=True)
    soup = BeautifulSoup(resp.text, "lxml")

    def meta_content(name=None, prop=None):
        if name:
            tag = soup.find("meta", attrs={"name": name})
        else:
            tag = soup.find("meta", attrs={"property": prop})
        return tag.get("content").strip() if tag and tag.get("content") else None

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    description = meta_content(name="description")
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical = canonical_tag.get("href") if canonical_tag else None
    html_tag = soup.find("html")
    lang = html_tag.get("lang") if html_tag else None
    viewport = meta_content(name="viewport")
    og_title = meta_content(prop="og:title")
    og_image = meta_content(prop="og:image")
    hreflang_count = len(soup.find_all("link", attrs={"rel": "alternate", "hreflang": True}))
    jsonld_count = len(soup.find_all("script", attrs={"type": "application/ld+json"}))

    measurements = [
        lib.measurement(CATEGORY, "metadata.title.present", value_bool=bool(title)),
        lib.measurement(CATEGORY, "metadata.title.text", value_text=title),
        lib.measurement(CATEGORY, "metadata.description.present", value_bool=bool(description)),
        lib.measurement(CATEGORY, "metadata.description.text", value_text=description),
        lib.measurement(CATEGORY, "metadata.canonical.present", value_bool=bool(canonical)),
        lib.measurement(CATEGORY, "metadata.canonical.href", value_text=canonical),
        lib.measurement(CATEGORY, "metadata.lang.present", value_bool=bool(lang), value_text=lang),
        lib.measurement(CATEGORY, "metadata.viewport.present", value_bool=bool(viewport)),
        lib.measurement(CATEGORY, "metadata.og_title.present", value_bool=bool(og_title)),
        lib.measurement(CATEGORY, "metadata.og_image.present", value_bool=bool(og_image)),
        lib.measurement(CATEGORY, "metadata.hreflang.count", value_numeric=hreflang_count),
        lib.measurement(CATEGORY, "metadata.jsonld.count", value_numeric=jsonld_count),
    ]

    observations = []
    path = lib.path_of(target_url)
    for key, value, sev in [
        ("title", title, "warning"),
        ("description", description, "warning"),
        ("canonical", canonical, "warning"),
        ("lang", lang, "warning"),
        ("viewport", viewport, "info"),
        ("og_title", og_title, "info"),
        ("og_image", og_image, "info"),
    ]:
        if not value:
            observations.append(
                lib.observation(
                    metric=f"metadata.{key}.present",
                    severity=sev,
                    observation_type="missing_metadata",
                    code=f"MISSING_{key.upper()}",
                    title=f"missing {key}",
                    message=f"{key} not present on {target_url}",
                    url=target_url,
                    fingerprint=f"metadata:missing:{key}:{path}",
                )
            )

    raw = {
        "title": title,
        "description": description,
        "canonical": canonical,
        "lang": lang,
        "viewport": viewport,
        "og_title": og_title,
        "og_image": og_image,
        "hreflang_count": hreflang_count,
        "jsonld_count": jsonld_count,
    }
    status = "warning" if any(o["severity"] == "warning" for o in observations) else "ok"
    return lib.result(
        target_url, TOOL, status, measurements=measurements, observations=observations, raw_json=raw
    )
