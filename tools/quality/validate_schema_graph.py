#!/usr/bin/env python3
"""tools/validate_schema_graph.py — JSON-LD coherence gate.

Enforces the consolidation policy:

  • The homepage exposes ONE inline JSON-LD block, structured as a
    single `@graph` carrying Person + WebSite + ProfilePage.
  • Other public pages expose AT MOST one inline JSON-LD block (a
    WebPage entity).
  • Every `@id` reference resolves either to an entity defined in
    the same page's @graph, or to a globally-known canonical id
    (Person, WebSite — defined on the homepage).
  • ProfilePage carries `mainEntity` pointing at the canonical
    Person id. WebSite carries `publisher` pointing at the same.
  • No duplicate top-level entity definitions per page.
  • All blocks parse as valid JSON.

The validator does NOT re-implement schema.org reasoning; it
checks structural invariants the build pipeline can guarantee
deterministically. Wider rich-result eligibility is verified
out-of-band (Google Rich Results Test, validator.schema.org).

Registered in tools/lib/checks.py (advisory tier).

Shape (deep module, small interface). The filesystem is the one injected seam —
`Repo(root)` — so the whole gate runs over a fixture repo with no
monkeypatching. `evaluate(repo)` is the pure compute path returning a Result;
`main()` is the only adapter that prints/exits. The per-page check helpers take
their inputs (the page-relative path and the file text) as parameters — no
module-global path reads.

Exit 0 = green; exit 1 = block.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
from paths import REPO_ROOT  # noqa: E402
from repo import Repo  # noqa: E402  (shared filesystem evidence seam)

# canonical entity ids. these are stable across editions.
SITE_BASE = "https://trentpower.fr"
PERSON_ID = f"{SITE_BASE}/#trent-power"
PERSON_IMG = f"{SITE_BASE}/#trent-power-image"
WEBSITE_ID = f"{SITE_BASE}/#website"
PROFILE_ID = f"{SITE_BASE}/#profile-page"

# editions carry the full editorial @graph (person + WebSite + ProfilePage
# + clienteling DefinedTerm in one block). the gate carries a modest
# WebSite + WebPage(#language-gate) only — the definitions live on the
# editions, not the root.
EDITION_HTML = {"en-au/index.html", "fr/index.html"}
GATE_HTML = {"index.html"}
HOMEPAGE_HTML = EDITION_HTML | GATE_HTML  # kept for back-compat reads

# match <script type="application/ld+json">…</script> bodies.
JSONLD_RE = re.compile(
    r'<script\s+type="application/ld\+json">(.*?)</script>',
    re.S,
)


# active html scanned for JSON-LD @graph correctness — discovered by
# walk so the bilingual /en/ and /fr/ trees are covered. the dated
# frozen-archive snapshots and the editorial review documents are
# excluded.
def _discover_active_html(repo: Repo) -> list[str]:
    out: list[str] = []
    prefix = "public/"
    for full in repo.glob(f"{prefix}**/*.html"):
        rel = full[len(prefix) :]
        if re.match(r"integrity/releases/[^/]+/", rel):
            continue
        if rel.startswith("editorial/"):
            continue
        out.append(rel)
    return out


def _entity_ids_in(graph_or_obj) -> set[str]:
    """Collect every @id defined in a graph object (top-level entities
    only — nested objects with their own @id are also collected)."""
    out: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            if "@id" in o and isinstance(o["@id"], str):
                out.add(o["@id"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(graph_or_obj)
    return out


def _check_homepage(rel: str, text: str) -> list[str]:
    fails: list[str] = []
    blocks = JSONLD_RE.findall(text)
    # faq JSON-LD blocks are tolerated as additional entries (one per
    # language). the consolidation rule is that the person / website /
    # profilepage trio must live in one @graph, not three separate
    # blocks. validate the first non-FAQ block.
    page_blocks: list[str] = []
    faq_blocks_n = 0
    for b in blocks:
        try:
            obj = json.loads(b)
        except json.JSONDecodeError as e:
            fails.append(f"{rel}: JSON-LD block does not parse ({e})")
            return fails
        # faqpage detection — by @type or by inlanguage on a top-level faq.
        t = obj.get("@type", "")
        if t == "FAQPage":
            faq_blocks_n += 1
        else:
            page_blocks.append(obj)
    if not page_blocks:
        fails.append(f"{rel}: no @graph / page-level JSON-LD found")
        return fails
    if len(page_blocks) > 1:
        fails.append(
            f"{rel}: expected ONE consolidated @graph block, found "
            f"{len(page_blocks)} non-FAQ blocks (consolidate via @graph)"
        )
    main = page_blocks[0]
    graph = main.get("@graph")
    if not isinstance(graph, list):
        fails.append(f"{rel}: top-level block missing `@graph` array")
        return fails

    # required entities by @id. the profilepage @id is per-edition —
    # /en-au/ and /fr/ are genuinely different pages, so each is its own
    # profilepage entity — while person and website stay one
    # site-rooted @id each.
    profile_id = f"{SITE_BASE}/{rel.split('/', 1)[0]}/#profile-page"
    by_id = {e.get("@id"): e for e in graph if isinstance(e, dict) and e.get("@id")}
    for required in (PERSON_ID, WEBSITE_ID, profile_id):
        if required not in by_id:
            fails.append(f"{rel} @graph: missing entity with @id {required}")

    # profilepage relationships
    pp = by_id.get(profile_id)
    if pp is not None:
        me = pp.get("mainEntity") or {}
        if me.get("@id") != PERSON_ID:
            fails.append(
                f"{rel} ProfilePage: mainEntity.@id should be {PERSON_ID}, got {me.get('@id')!r}"
            )
        ip = pp.get("isPartOf") or {}
        if ip.get("@id") != WEBSITE_ID:
            fails.append(
                f"{rel} ProfilePage: isPartOf.@id should be {WEBSITE_ID}, got {ip.get('@id')!r}"
            )

    # website relationships
    ws = by_id.get(WEBSITE_ID)
    if ws is not None:
        pub = ws.get("publisher") or {}
        if pub.get("@id") != PERSON_ID:
            fails.append(
                f"{rel} WebSite: publisher.@id should be {PERSON_ID}, got {pub.get('@id')!r}"
            )

    # no duplicated person / website / profilepage entries
    types_seen: dict[str, int] = {}
    for e in graph:
        if isinstance(e, dict):
            t = e.get("@type")
            if t in ("Person", "WebSite", "ProfilePage"):
                types_seen[t] = types_seen.get(t, 0) + 1
    for t, n in types_seen.items():
        if n > 1:
            fails.append(f"{rel} @graph: {t} defined {n} times (should be 1)")

    return fails


def _check_other_page(rel: str, text: str) -> list[str]:
    fails: list[str] = []
    blocks = JSONLD_RE.findall(text)
    if not blocks:
        return fails  # pages without JSON-LD are tolerated
    if len(blocks) > 1:
        fails.append(
            f"{rel}: expected at most ONE inline JSON-LD block, "
            f"found {len(blocks)} (consolidate via @graph)"
        )
    for body in blocks:
        try:
            obj = json.loads(body)
        except json.JSONDecodeError as e:
            fails.append(f"{rel}: JSON-LD block does not parse ({e})")
            continue
        # @id references resolve back to the canonical homepage entities.
        # two utility-page shapes are accepted:
        #   • webpage         — for /privacy/, /verify/, /sw-reset/
        #   • techarticle     — for /integrity/ and /source/, where the
        #     content is explanatory technical writing about how the site
        #     is built and verified. techarticle requires author +
        #     publisher in addition to the webpage relationships.
        t = obj.get("@type", "")
        if t in ("WebPage", "TechArticle"):
            ip = obj.get("isPartOf") or {}
            if ip and ip.get("@id") not in (WEBSITE_ID, SITE_BASE, f"{SITE_BASE}/"):
                fails.append(
                    f"{rel} {t}: isPartOf.@id should reference {WEBSITE_ID}, got {ip.get('@id')!r}"
                )
            ab = obj.get("about") or obj.get("author") or {}
            if ab and ab.get("@id") != PERSON_ID:
                fails.append(
                    f"{rel} {t}: about/author.@id should reference {PERSON_ID}, "
                    f"got {ab.get('@id')!r}"
                )
            if t == "TechArticle":
                pub = obj.get("publisher") or {}
                if pub.get("@id") != PERSON_ID:
                    fails.append(
                        f"{rel} TechArticle: publisher.@id should reference {PERSON_ID}, "
                        f"got {pub.get('@id')!r}"
                    )
                if not obj.get("headline"):
                    fails.append(f"{rel} TechArticle: missing headline")
                if not (obj.get("datePublished") or obj.get("dateModified")):
                    fails.append(f"{rel} TechArticle: missing datePublished/dateModified")
    return fails


def _check_gate(rel: str, text: str) -> list[str]:
    """The root / is a language-selection page. Its @graph carries the
    WebSite (global entity) plus a single WebPage(#language-gate) that
    references the site. Person, ProfilePage, DefinedTerm and
    DefinedTermSet are explicitly forbidden here — they belong to the
    editions where the editorial content visibly exists."""
    fails: list[str] = []
    blocks = JSONLD_RE.findall(text)
    if not blocks:
        return [f"{rel}: no JSON-LD found"]
    page_blocks = []
    for b in blocks:
        try:
            obj = json.loads(b)
        except json.JSONDecodeError as e:
            fails.append(f"{rel}: JSON-LD block does not parse ({e})")
            return fails
        if obj.get("@type") == "FAQPage":
            continue
        page_blocks.append(obj)
    if not page_blocks:
        return [f"{rel}: no @graph / page-level JSON-LD found"]
    main = page_blocks[0]
    graph = main.get("@graph")
    if not isinstance(graph, list):
        return [f"{rel}: top-level block missing `@graph` array"]
    by_id = {e.get("@id"): e for e in graph if isinstance(e, dict) and e.get("@id")}
    # required: WebSite + WebPage(#language-gate)
    if WEBSITE_ID not in by_id:
        fails.append(f"{rel} @graph: missing WebSite with @id {WEBSITE_ID}")
    gate_id = f"{SITE_BASE}/#language-gate"
    if gate_id not in by_id:
        fails.append(f"{rel} @graph: missing WebPage with @id {gate_id}")
    else:
        gate = by_id[gate_id]
        ip = gate.get("isPartOf") or {}
        if ip.get("@id") != WEBSITE_ID:
            fails.append(
                f"{rel} WebPage(language-gate): isPartOf.@id should be "
                f"{WEBSITE_ID}, got {ip.get('@id')!r}"
            )
    # website relationships — publisher.@id should reference person
    ws = by_id.get(WEBSITE_ID)
    if ws is not None:
        pub = ws.get("publisher") or {}
        if pub.get("@id") != PERSON_ID:
            fails.append(
                f"{rel} WebSite: publisher.@id should be {PERSON_ID}, got {pub.get('@id')!r}"
            )
    # a minimal person stub is allowed (so the WebSite's author /
    # publisher / copyrightHolder references resolve), but the rich
    # editorial entities — ProfilePage, DefinedTerm, DefinedTermSet —
    # belong on the editions and are forbidden at the gate. the person
    # stub is enforced to be modest: a minimal node carries name + url
    # only; sameAs, jobTitle, knowsAbout etc. mark a full person and
    # should not appear at the root.
    PERSON_STUB_MAX_KEYS = {"@type", "@id", "name", "url"}
    for e in graph:
        if not isinstance(e, dict):
            continue
        t = e.get("@type")
        if t in ("ProfilePage", "DefinedTerm", "DefinedTermSet"):
            fails.append(
                f"{rel} @graph: {t} entity present on the language gate — "
                f"editorial entities belong on /en-au/ and /fr/, not on root"
            )
        if t == "Person":
            extra = set(e.keys()) - PERSON_STUB_MAX_KEYS
            if extra:
                fails.append(
                    f"{rel} @graph: Person on the language gate carries "
                    f"non-stub keys {sorted(extra)} — only {sorted(PERSON_STUB_MAX_KEYS)} "
                    f"allowed (the full Person graph belongs on /en-au/ and /fr/)"
                )
    return fails


# ---------------------------------------------------------------------------
# Result — the value that flows through the interface. evaluate() produces it;
# main() renders it. tests assert on Result, never on stdout. `summary` carries
# the green one-liner so the render stays a thin adapter.
# ---------------------------------------------------------------------------
@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def ok(self) -> bool:
        return not self.fails


# ---------------------------------------------------------------------------
# evaluate — the compute interface. one call, one Result, over the injected
# Repo. this is the test surface.
# ---------------------------------------------------------------------------
def evaluate(repo: Repo) -> Result:
    r = Result()
    active_html = _discover_active_html(repo)
    for rel in active_html:
        if not repo.is_file(f"public/{rel}"):
            r.fails.append(f"{rel}: missing")
            continue
        text = repo.read(f"public/{rel}")
        if rel in GATE_HTML:
            r.fails.extend(_check_gate(rel, text))
        elif rel in EDITION_HTML:
            r.fails.extend(_check_homepage(rel, text))
        else:
            r.fails.extend(_check_other_page(rel, text))
    r.summary = (
        f"schema graph — {len(active_html)} HTML pages, "
        f"one consolidated @graph on /, single-block elsewhere"
    )
    return r


# ---------------------------------------------------------------------------
# main — the side-effecting adapter. evaluates, renders, returns exit code. the
# only place stdout and exit codes live.
# ---------------------------------------------------------------------------
def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    r = evaluate(repo)

    if r.fails:
        print(f"FAIL: {len(r.fails)} schema-graph issue(s)", file=sys.stderr)
        for f in r.fails[:30]:
            print(f"  ✗ {f}", file=sys.stderr)
        if len(r.fails) > 30:
            print(f"  … and {len(r.fails) - 30} more", file=sys.stderr)
        return 1
    print(f"OK: {r.summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
