#!/usr/bin/env python3
"""Structured-data validator: parse JSON-LD blocks locally, report schema types."""

from __future__ import annotations

import json

import lib
from bs4 import BeautifulSoup

TOOL = "structured_data"
CATEGORY = "structured_data"


def _collect_types(node, out):
    """Recursively gather @type values from a JSON-LD node."""
    if isinstance(node, dict):
        t = node.get("@type")
        if isinstance(t, str):
            out.add(t)
        elif isinstance(t, list):
            out.update(x for x in t if isinstance(x, str))
        for v in node.values():
            _collect_types(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_types(v, out)


def run(target_url, cfg, http):
    resp = lib.fetch(http, target_url, cfg, allow_redirects=True)
    soup = BeautifulSoup(resp.text, "lxml")
    blocks = soup.find_all("script", attrs={"type": "application/ld+json"})

    path = lib.path_of(target_url)
    types = set()
    error_count = 0
    observations = []
    for i, b in enumerate(blocks):
        text = b.string or b.get_text() or ""
        try:
            data = json.loads(text)
            _collect_types(data, types)
        except json.JSONDecodeError as e:
            error_count += 1
            observations.append(
                lib.observation(
                    metric="structured_data.jsonld.error_count",
                    severity="error",
                    observation_type="parse_error",
                    code="JSONLD_PARSE",
                    title=f"JSON-LD block #{i + 1} failed to parse",
                    message=str(e),
                    line=getattr(e, "lineno", None),
                    column=getattr(e, "colno", None),
                    url=target_url,
                    fingerprint=f"structured_data:jsonld-parse:{i}:{path}",
                    evidence=[
                        lib.evidence(
                            "excerpt",
                            "Excerpt",
                            text[:200],
                            excerpt=text[:500],
                            source_url=target_url,
                        )
                    ],
                )
            )

    valid = error_count == 0
    types_lower = {t.lower() for t in types}

    measurements = [
        lib.measurement(CATEGORY, "structured_data.jsonld.valid", value_bool=valid),
        lib.measurement(CATEGORY, "structured_data.jsonld.error_count", value_numeric=error_count),
        lib.measurement(CATEGORY, "structured_data.schema_type.count", value_numeric=len(types)),
        lib.measurement(
            CATEGORY, "structured_data.person.present", value_bool="person" in types_lower
        ),
        lib.measurement(
            CATEGORY, "structured_data.website.present", value_bool="website" in types_lower
        ),
        lib.measurement(
            CATEGORY, "structured_data.imageobject.present", value_bool="imageobject" in types_lower
        ),
    ]

    if types:
        observations.append(
            lib.observation(
                metric="structured_data.schema_type.count",
                severity="info",
                observation_type="detected",
                code="SCHEMA_TYPES",
                title=f"{len(types)} schema type(s) detected",
                message=", ".join(sorted(types)),
                url=target_url,
                fingerprint=f"structured_data:types:{path}",
                evidence=[
                    lib.evidence("list", "Types", ", ".join(sorted(types)), source_url=target_url)
                ],
            )
        )

    raw = {"types": sorted(types), "block_count": len(blocks), "error_count": error_count}
    status = "error" if error_count else "ok"
    return lib.result(
        target_url, TOOL, status, measurements=measurements, observations=observations, raw_json=raw
    )
