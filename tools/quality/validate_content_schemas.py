#!/usr/bin/env python3
"""validate_content_schemas.py -- content <-> schema <-> route integrity gate.

Blocking (COR) check for the content contract:
  1. every content/<lang>/pages/*.yml validates against schemas/content/<stem>.schema.json
  2. every routes.json reference resolves (content file, schema file, template all exist)
  3. every editable route has a schema
  4. language pairs: en/fr top-level key parity per page (advisory -- reported, never fatal,
     since a parity gap does not break rendering)

Invalid content (1-3) fails the blocking gate "if it would break rendering"; parity
drift (4) surfaces as a warning. Reuses the neutral report contract:
tools/check_report.build_check_report -- each content file / reference is one "check".

Usage:
    python3 tools/validate_content_schemas.py
    python3 tools/validate_content_schemas.py --json reports/checks/last-content-schemas.json

Exit 0 = content contract holds. Exit 1 = a blocking violation.
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    import yaml
except ImportError:
    print("error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

try:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:
    print("error: jsonschema>=4.18 required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(2)

sys.path.insert(
    0,
    str(
        next(
            _a
            for _a in __import__("pathlib").Path(__file__).resolve().parents
            if _a.name == "tools"
        )
        / "lib"
    ),
)
import check_report  # noqa: E402
from paths import CONTENT_DIR, REPO_ROOT, TEMPLATES_DIR  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas" / "content"
ROUTES_JSON = CONTENT_DIR / "routes.json"
PAGES_DIRS = {"en": CONTENT_DIR / "en" / "pages", "fr": CONTENT_DIR / "fr" / "pages"}
TEMPLATE_PAGES = TEMPLATES_DIR / "pages"

# top-level content keys that legitimately differ between language editions
# and must not be flagged by the en/fr parity check.
PARITY_IGNORE_KEYS = {"translation"}


def _entry(id_, label, status, rationale, tier="blocking", detail="", files=None):
    return {
        "id": id_,
        "label": label,
        "tier": tier,
        "category": "COR",
        "status": status,
        "duration_ms": 0,
        "rationale": rationale,
        "stdout": detail,
        "stderr": "",
        "affected_files": files or [],
    }


def _registry() -> Registry:
    resources = []
    for sf in sorted(SCHEMA_DIR.glob("*.schema.json")):
        s = json.loads(sf.read_text(encoding="utf-8"))
        resources.append((s["$id"], Resource.from_contents(s)))
    return Registry().with_resources(resources)


def _validate_content(registry: Registry) -> list[dict]:
    results = []
    for lang, pages_dir in PAGES_DIRS.items():
        if not pages_dir.is_dir():
            continue
        for yml in sorted(pages_dir.glob("*.yml")):
            stem = yml.stem
            schema_path = SCHEMA_DIR / f"{stem}.schema.json"
            rel = str(yml.relative_to(REPO_ROOT))
            if not schema_path.exists():
                results.append(
                    _entry(
                        f"schema:{lang}/{stem}",
                        f"{rel} has no schema",
                        "failed",
                        "every editable content file must have a schema",
                        files=[rel],
                    )
                )
                continue
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            instance = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
            validator = Draft202012Validator(schema, registry=registry)
            errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
            if errors:
                detail = "\n".join(
                    f"  {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
                    for e in errors[:10]
                )
                results.append(
                    _entry(
                        f"content:{lang}/{stem}",
                        f"{rel} violates {stem}.schema.json",
                        "failed",
                        "content must match its page schema (would break rendering otherwise)",
                        detail=detail,
                        files=[rel],
                    )
                )
            else:
                results.append(
                    _entry(
                        f"content:{lang}/{stem}",
                        f"{rel} valid",
                        "passed",
                        "content matches its page schema",
                        files=[rel],
                    )
                )
    return results


def _validate_references() -> list[dict]:
    results = []
    if not ROUTES_JSON.exists():
        return [
            _entry(
                "routes_json",
                "content/routes.json present",
                "failed",
                "routes.json must exist — run tools/generate_routes_json.py",
            )
        ]
    data = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
    for r in data.get("routes", []):
        rid = r["id"]
        missing = []
        for field, base in (("content", REPO_ROOT), ("schema", REPO_ROOT)):
            if not (base / r[field]).exists():
                missing.append(f"{field}={r[field]}")
        tmpl = TEMPLATE_PAGES / f"{r['template']}.html"
        if not tmpl.exists():
            missing.append(f"template={tmpl.relative_to(REPO_ROOT)}")
        if missing:
            results.append(
                _entry(
                    f"ref:{rid}",
                    f"route {rid} references resolve",
                    "failed",
                    "every routes.json reference must resolve to a real file",
                    detail="  missing: " + ", ".join(missing),
                    files=[r["content"]],
                )
            )
    if not results:
        results.append(
            _entry(
                "refs",
                "all routes.json references resolve",
                "passed",
                "content / schema / template referenced by routes.json all exist",
            )
        )
    return results


def _validate_parity() -> list[dict]:
    results = []
    en_dir, fr_dir = PAGES_DIRS["en"], PAGES_DIRS["fr"]
    for yml in sorted(en_dir.glob("*.yml")):
        fr = fr_dir / yml.name
        if not fr.exists():
            continue  # en-only surfaces (e.g. local) are intentional
        en_keys = (
            set((yaml.safe_load(yml.read_text(encoding="utf-8")) or {}).keys()) - PARITY_IGNORE_KEYS
        )
        fr_keys = (
            set((yaml.safe_load(fr.read_text(encoding="utf-8")) or {}).keys()) - PARITY_IGNORE_KEYS
        )
        if en_keys != fr_keys:
            diff = []
            if en_keys - fr_keys:
                diff.append(f"missing in fr: {sorted(en_keys - fr_keys)}")
            if fr_keys - en_keys:
                diff.append(f"missing in en: {sorted(fr_keys - en_keys)}")
            results.append(
                _entry(
                    f"parity:{yml.stem}",
                    f"{yml.stem} en/fr key parity",
                    "failed",
                    "en and fr editions should carry the same top-level surfaces",
                    tier="advisory",
                    detail="  " + "; ".join(diff),
                    files=[yml.stem],
                )
            )
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="content <-> schema <-> route integrity gate")
    ap.add_argument("--json", metavar="PATH", help="write a machine-readable report to PATH")
    args = ap.parse_args(argv)

    registry = _registry()
    results = _validate_content(registry) + _validate_references() + _validate_parity()

    report = check_report.build_check_report("content_schemas", results)
    blocking_failures = [r for r in results if r["status"] == "failed" and r["tier"] == "blocking"]
    warnings = [r for r in results if r["status"] == "failed" and r["tier"] == "advisory"]

    for r in blocking_failures:
        print(f"X FAIL [{r['id']}] {r['label']}")
        if r["stdout"]:
            print(r["stdout"])
    for r in warnings:
        print(f"! WARN [{r['id']}] {r['label']}")
        if r["stdout"]:
            print(r["stdout"])

    if args.json:
        check_report.atomic_write_json(report, args.json)
        print(f"report: {args.json}")

    s = report["summary"]
    if blocking_failures:
        print(f"\nFAIL: content contract broken — {s['failed']} blocking, {s['warnings']} advisory")
        return 1
    print(
        f"\nOK: content contract holds — {s['passed']} passed, {s['warnings']} advisory warning(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
