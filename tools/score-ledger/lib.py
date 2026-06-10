#!/usr/bin/env python3
"""Shared primitives for the trentpower.fr Score Ledger.

Holds the cross-cutting pieces every validator needs: config loading, an HTTP
session, hashing, timestamps, the standard-result builders, the enum
vocabularies, and the metric-registry lookup. Validators import this module and
never touch SQLite directly.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Enum vocabularies (the brief's required values). Validated at insert time.
# ---------------------------------------------------------------------------
STATUS = {"ok", "warning", "error", "unavailable", "skipped", "manual"}
DIRECTIONS = {"improved", "declined", "unchanged", "new", "missing", "not_comparable"}
UNITS = {
    "score_0_100",
    "count",
    "ms",
    "bytes",
    "boolean",
    "grade",
    "http_status",
    "text",
    "hash",
    "enum",
    "ratio",
    "unknown",
}
CMP_MODES = {
    "higher_better",
    "lower_better",
    "boolean_pass",
    "grade_order",
    "exact_match",
    "neutral",
}

# Grade ordering for grade_order comparisons (lower rank = better). Covers the
# +/- variants used by Mozilla Observatory and SSL Labs, plus SSL Labs' special
# T (trust issues) and M (name mismatch) grades, ranked worse than F.
GRADE_RANK = {
    "A+": 0,
    "A": 1,
    "A-": 2,
    "B+": 3,
    "B": 4,
    "B-": 5,
    "C+": 6,
    "C": 7,
    "C-": 8,
    "D+": 9,
    "D": 10,
    "D-": 11,
    "E": 12,
    "F": 13,
    "T": 14,
    "M": 15,
}


# ---------------------------------------------------------------------------
# Exceptions the validator dispatch wrapper maps to standard statuses.
# ---------------------------------------------------------------------------
class NotConfigured(Exception):
    """An integration is disabled; record a manual check instead."""

    def __init__(self, message, source_url=None):
        super().__init__(message)
        self.source_url = source_url


class ToolMissing(Exception):
    """A required local tool (e.g. lighthouse CLI) is absent -> unavailable."""


class UnregisteredMetric(Exception):
    """A metric has no resolvable comparison_mode in the registry."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass
class Config:
    site_name: str
    targets: list
    checks: dict
    integrations: dict
    network: dict
    storage: dict
    reports: dict
    trust_paths: dict
    trust_json_files: list
    taxonomy: dict
    metric_registry: dict
    metric_registry_suffix_rules: dict
    raw: dict = field(default_factory=dict)
    path: str = ""

    @property
    def sqlite_path(self):
        p = self.storage.get("sqlite_path", "data/score-ledger.sqlite")
        return p if os.path.isabs(p) else os.path.join(HERE, p)

    @property
    def reports_dir(self):
        p = self.reports.get("output_dir", "reports")
        return p if os.path.isabs(p) else os.path.join(HERE, p)

    @property
    def truncate_raw_after_chars(self):
        return int(self.storage.get("truncate_raw_after_chars", 50000) or 0)


def _deep_merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path=None) -> Config:
    path = path or os.path.join(HERE, "config.yml")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    # gitignored local overrides (secrets such as API keys live here, never in
    # the committed config.yml).
    local_path = os.path.join(os.path.dirname(path), "config.local.yml")
    if os.path.exists(local_path):
        with open(local_path, encoding="utf-8") as fh:
            _deep_merge(data, yaml.safe_load(fh) or {})
    return Config(
        site_name=data.get("site_name", "site"),
        targets=list(data.get("targets", [])),
        checks=dict(data.get("checks", {})),
        integrations=dict(data.get("integrations", {})),
        network=dict(data.get("network", {})),
        storage=dict(data.get("storage", {})),
        reports=dict(data.get("reports", {})),
        trust_paths=dict(data.get("trust_paths", {})),
        trust_json_files=list(data.get("trust_json_files", [])),
        taxonomy=dict(data.get("taxonomy", {})),
        metric_registry=dict(data.get("metric_registry", {})),
        metric_registry_suffix_rules=dict(data.get("metric_registry_suffix_rules", {})),
        raw=data,
        path=path,
    )


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def http_session(cfg: Config) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": cfg.network.get("user_agent", "score-ledger")})
    return s


def fetch(session, url, cfg, method="GET", allow_redirects=True):
    """Single request, single timeout, no retries. Returns the Response.

    Raises requests exceptions on transport failure; callers/wrapper handle them.
    """
    timeout = float(cfg.network.get("timeout_seconds", 30))
    return session.request(method, url, timeout=timeout, allow_redirects=allow_redirects)


def polite_delay(cfg: Config):
    time.sleep(float(cfg.network.get("delay_seconds", 0) or 0))


# ---------------------------------------------------------------------------
# Hashing / time helpers
# ---------------------------------------------------------------------------
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def now_utc_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def path_of(url: str) -> str:
    p = urlsplit(url).path
    return p or "/"


# Unicode formatting artifacts (non-breaking / narrow spaces, dashes, minus) that
# tools like Lighthouse embed in display strings. Normalised to ASCII so reports
# stay portable; genuine content (e.g. accented titles) is left untouched.
_ASCII_MAP = {
    "\u00a0": " ",
    "\u202f": " ",
    "\u2009": " ",
    "\u2007": " ",  # spaces
    "\u2212": "-",
    "\u2013": "-",
    "\u2014": "-",  # dashes/minus
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',  # quotes
    "\u2026": "...",  # ellipsis
}


def ascii_norm(s):
    if not s:
        return s
    for k, v in _ASCII_MAP.items():
        s = s.replace(k, v)
    return s


# ---------------------------------------------------------------------------
# Registry lookup
# ---------------------------------------------------------------------------
def registry_lookup(cfg: Config, metric: str):
    """Resolve (unit, comparison_mode) for a metric.

    Precedence: explicit metric_registry entry -> suffix rule -> raise.
    Raising (rather than guessing) lets the insert layer mark the tool_result
    unavailable instead of recording an uncomparable metric.
    """
    entry = cfg.metric_registry.get(metric)
    if entry:
        return entry.get("unit", "unknown"), entry.get("comparison_mode", "neutral")
    for suffix, rule in cfg.metric_registry_suffix_rules.items():
        if metric.endswith(suffix):
            return rule.get("unit", "unknown"), rule.get("comparison_mode", "neutral")
    raise UnregisteredMetric(metric)


# ---------------------------------------------------------------------------
# Standard-result builders. Every validator returns result(...) shaped data.
# ---------------------------------------------------------------------------
def result(
    target_url,
    tool,
    status,
    *,
    tool_version=None,
    source_url=None,
    measurements=None,
    observations=None,
    raw_json=None,
    raw_text=None,
):
    return {
        "target_url": target_url,
        "tool": tool,
        "status": status,
        "tool_version": tool_version,
        "source_url": source_url,
        "measurements": measurements or [],
        "observations": observations or [],
        "raw_json": raw_json,
        "raw_text": raw_text,
    }


def measurement(
    category,
    metric,
    *,
    value_numeric=None,
    value_text=None,
    value_bool=None,
    unit=None,
    comparison_mode=None,
    grade=None,
    normalised_score=None,
    status="ok",
):
    """A measurement. unit/comparison_mode may be omitted to inherit the
    registry value at insert time."""
    return {
        "category": category,
        "metric": metric,
        "value_numeric": value_numeric,
        "value_text": value_text,
        "value_bool": (None if value_bool is None else int(bool(value_bool))),
        "unit": unit,
        "comparison_mode": comparison_mode,
        "grade": grade,
        "normalised_score": normalised_score,
        "status": status,
    }


def observation(
    metric,
    severity,
    observation_type,
    code,
    title,
    message,
    *,
    selector=None,
    line=None,
    column=None,
    url=None,
    fingerprint=None,
    evidence=None,
):
    return {
        "metric": metric,
        "severity": severity,
        "observation_type": observation_type,
        "code": code,
        "title": title,
        "message": message,
        "selector": selector,
        "line": line,
        "column": column,
        "url": url,
        "fingerprint": fingerprint,
        "evidence": evidence or [],
    }


def evidence(evidence_type, label, value, *, excerpt=None, source_url=None, raw_fragment=None):
    return {
        "evidence_type": evidence_type,
        "label": label,
        "value": value,
        "excerpt": excerpt,
        "source_url": source_url,
        "raw_fragment": raw_fragment,
    }
