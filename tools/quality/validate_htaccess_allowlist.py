#!/usr/bin/env python3
"""validate_htaccess_allowlist.py — simulate the .htaccess rewrite gate
in python and prove every public file passes the allow-list.

The validate_public_exposure.py gate proves manifest <-> disk <-> html
consistency. This script closes the third leg: manifest <-> .htaccess.
Parses the rewrite gate block from public/.htaccess, compiles every
RewriteRule pattern to a python regex, then evaluates each url under
public/ against the rules in source order, applying [f,l] (deny) and
[l] (allow) semantics. Any url that falls through to the final
fallback deny is a missing allow rule.

Exit 0 = every public file passes through an allow rule.
Exit 1 = at least one file would be denied by .htaccess.

Shape (deep module, small interface). The external interface is `main() -> int`
plus the text contract. The filesystem is the injected `Repo(root)` seam, so the
whole gate runs through `evaluate(repo, ctx) -> Result` over a fixture repo. The
per-url rule simulation stays a pure function (`classify`). Compute is separate
from render (`main`).
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

HTACCESS_REL = "public/.htaccess"
MANIFEST_REL = "tools/config/public-exposure.json"

# the rewrite gate block sits between the BEGIN/END PUBLIC EXPOSURE
# markers emitted by tools/generate_htaccess.py.
GATE_OPEN = re.compile(r"#\s*BEGIN PUBLIC EXPOSURE")
GATE_CLOSE = re.compile(r"#\s*END PUBLIC EXPOSURE")

RULE_RE = re.compile(
    r"""^\s*RewriteRule\s+(\S+)\s+-\s+\[([A-Z,]+)\]\s*$""",
    re.MULTILINE,
)


def parse_rules(gate_text: str) -> tuple[list[tuple[re.Pattern, str]], list[str]]:
    """compile every RewriteRule in the gate block. returns (rules, errors);
    a bad pattern becomes an error string rather than a process exit."""
    rules: list[tuple[re.Pattern, str]] = []
    errors: list[str] = []
    for m in RULE_RE.finditer(gate_text):
        pat_raw = m.group(1)
        flags = m.group(2)
        # skip rules nested behind comments (line starts with #).
        line_start = gate_text.rfind("\n", 0, m.start()) + 1
        if gate_text[line_start : m.start()].lstrip().startswith("#"):
            continue
        try:
            pat = re.compile(pat_raw)
        except re.error as e:
            errors.append(f"invalid regex in .htaccess: {pat_raw!r} ({e})")
            continue
        rules.append((pat, flags))
    return rules, errors


def classify(url: str, rules: list[tuple[re.Pattern, str]]) -> str:
    """pure per-url rule simulation: 'allow' | 'deny' | 'fallthrough'."""
    # mod_rewrite in .htaccess context drops the leading slash from
    # the request URI before matching against RewriteRule patterns.
    rel = url.lstrip("/")
    for pat, flags in rules:
        if pat.search(rel):
            if "F" in flags.split(","):
                return "deny"
            if "L" in flags.split(","):
                return "allow"
    return "fallthrough"


def _glob_to_regex(pattern: str) -> str:
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        if c in r".+()[]{}|^$\\":
            out.append("\\" + c)
            i += 1
            continue
        out.append(c)
        i += 1
    return "^" + "".join(out) + "$"


def walk_public_urls(repo: Repo, deploy_excluded: list[str]) -> list[str]:
    """mirror validate_public_exposure.py walking semantics."""
    deploy_re = [re.compile(_glob_to_regex(g)) for g in deploy_excluded]
    prefix = "public/"
    urls: list[str] = []
    for repo_rel in repo.glob("public/**/*"):
        rel = repo_rel[len(prefix):]
        if rel == ".htaccess":
            continue
        url = "/" + rel
        if any(p.match(url) for p in deploy_re):
            continue
        urls.append(url)
    # also include the directory-form url for any index.html, so we test
    # that mod_dir's subrequest resolution would succeed.
    dir_urls = [u[: -len("index.html")] for u in urls if u.endswith("/index.html")]
    return urls + dir_urls


@dataclass(frozen=True)
class Ctx:
    rules: list[tuple[re.Pattern, str]]
    deploy_excluded: list[str]


@dataclass
class Result:
    rule_count: int = 0
    allowed: int = 0
    denied: list[str] = field(default_factory=list)
    fallthrough: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.denied and not self.fallthrough


def load(repo: Repo) -> tuple[Ctx | None, list[str]]:
    if not repo.is_file(HTACCESS_REL):
        return None, ["could not read public/.htaccess"]
    text = repo.read(HTACCESS_REL)
    open_m = GATE_OPEN.search(text)
    close_m = GATE_CLOSE.search(text)
    if not open_m or not close_m:
        return None, ["could not locate the rewrite gate block in .htaccess"]
    gate_text = text[open_m.end() : close_m.start()]
    rules, errors = parse_rules(gate_text)
    if errors:
        return None, errors
    if not rules:
        return None, ["no RewriteRule directives parsed from the gate block"]
    deploy_excluded: list[str] = []
    if repo.is_file(MANIFEST_REL):
        data = json.loads(repo.read(MANIFEST_REL))
        deploy_excluded = list(data.get("deploy_excluded_globs", []))
    return Ctx(rules=rules, deploy_excluded=deploy_excluded), []


def evaluate(repo: Repo, ctx: Ctx) -> Result:
    result = Result(rule_count=len(ctx.rules))
    for url in walk_public_urls(repo, ctx.deploy_excluded):
        verdict = classify(url, ctx.rules)
        if verdict == "allow":
            result.allowed += 1
        elif verdict == "deny":
            result.denied.append(url)
        else:
            result.fallthrough.append(url)
    return result


def main(repo_root: Path = REPO_ROOT) -> int:
    repo = Repo(repo_root)
    ctx, errors = load(repo)
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1

    print(f"  parsed {len(ctx.rules)} RewriteRule directives from .htaccess")
    result = evaluate(repo, ctx)

    if result.denied:
        print(f"FAIL: {len(result.denied)} public file(s) are explicitly denied by the gate:")
        for u in result.denied[:50]:
            print(f"  DENIED: {u}")
        if len(result.denied) > 50:
            print(f"  ... and {len(result.denied) - 50} more")
        return 1

    if result.fallthrough:
        print(f"FAIL: {len(result.fallthrough)} public file(s) fall through to the final deny:")
        for u in result.fallthrough[:50]:
            print(f"  FALLTHROUGH: {u}")
        if len(result.fallthrough) > 50:
            print(f"  ... and {len(result.fallthrough) - 50} more")
        return 1

    print(f"OK: every public url passes through an allow rule ({result.allowed} urls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
