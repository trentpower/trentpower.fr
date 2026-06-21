#!/usr/bin/env python3
"""validate_verification_map_dates.py — every record in
verify/verification-data.js must carry a `validated` date no more than
VERIFICATION_MAP_MAX_AGE_DAYS old (and not in the future) relative to today UTC.

Visitors expect the validated stamp to reflect a recent build; the window
absorbs the build-vs-CI day boundary without going stale. Re-stamping in CI is
not an option — verification-data.js is hashed inside the signed integrity.json,
so a fresh stamp would need the signing key in CI.

Shape (deep module, small interface). Two injected seams — `Repo(root)` for the
filesystem and a `now` instant for the clock — so the gate is exercised through
`evaluate(text, present, now)` over a fixture at a frozen instant, no
monkeypatching. `main()` is the only adapter that prints/exits. Byte-identical
to the former inline_checks.check_verification_map_dates.

Exit 0 = every stamp is fresh (or the file is absent — skip).
Exit 1 = at least one stale or future stamp.
"""

from __future__ import annotations

import datetime
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

VERIFICATION_DATA_REL = "public/verify/verification-data.js"

# the tolerance window: the stamp is never more than two weeks stale.
VERIFICATION_MAP_MAX_AGE_DAYS = 14

_VALIDATED_RE = re.compile(r'"validated":\s*"(\d{4}-\d{2}-\d{2})"')


@dataclass
class Result:
    fails: list[str] = field(default_factory=list)
    seen: int = 0
    present: bool = True
    today_str: str = ""

    @property
    def ok(self) -> bool:
        return not self.fails


def load(repo: Repo) -> tuple[str, bool]:
    """Return (text, present). Absent file is a legitimate skip, not an error."""
    present = repo.is_file(VERIFICATION_DATA_REL)
    return (repo.read(VERIFICATION_DATA_REL) if present else ""), present


def evaluate(text: str, present: bool, now: datetime.datetime) -> Result:
    today = now.date()
    today_str = today.isoformat()
    r = Result(present=present, today_str=today_str)
    if not present:
        return r
    for m in _VALIDATED_RE.finditer(text):
        r.seen += 1
        try:
            validated = datetime.date.fromisoformat(m.group(1))
        except ValueError:
            line = text.count("\n", 0, m.start()) + 1
            r.fails.append(
                f"verify/verification-data.js:{line} validated={m.group(1)} is not a valid ISO date"
            )
            continue
        age = (today - validated).days
        if age < 0:
            line = text.count("\n", 0, m.start()) + 1
            r.fails.append(
                f"verify/verification-data.js:{line} validated={m.group(1)} "
                f"is in the future (today UTC {today_str})"
            )
        elif age > VERIFICATION_MAP_MAX_AGE_DAYS:
            line = text.count("\n", 0, m.start()) + 1
            r.fails.append(
                f"verify/verification-data.js:{line} validated={m.group(1)} "
                f"is {age} days old (max {VERIFICATION_MAP_MAX_AGE_DAYS}; today UTC "
                f"{today_str}) — rebuild to refresh"
            )
    return r


def main(repo_root: Path = REPO_ROOT, now: datetime.datetime | None = None) -> int:
    repo = Repo(repo_root)
    now = now or datetime.datetime.now(datetime.UTC)
    text, present = load(repo)
    r = evaluate(text, present, now)

    if not r.present:
        print("  OK: verify/verification-data.js absent — skipping")
        return 0
    if r.fails:
        print(f"  FAIL: {len(r.fails)} stale verification-map date(s) (today UTC {r.today_str}):")
        for f in r.fails[:20]:
            print(f"    {f}")
        if len(r.fails) > 20:
            print(f"    … and {len(r.fails) - 20} more")
        return 1
    if r.seen == 0:
        print("  OK: verify/verification-data.js has no validated entries — skipping")
    else:
        print(
            f"  OK: {r.seen} verification-map record(s) validated within "
            f"{VERIFICATION_MAP_MAX_AGE_DAYS}d (today UTC {r.today_str})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
