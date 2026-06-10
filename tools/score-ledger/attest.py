#!/usr/bin/env python3
"""TESTRESULTS.txt - signed release-test attestation.

Generates a plain-ASCII attestation derived from the latest run (never hand
authored), optionally GPG-signs it, and verifies signatures. The score-ledger
stays self-contained: it writes only to its own output (or --out) and PRINTS
instructions for copying into a release folder. It never modifies public/, the
release archive generators, or the predeploy baseline.

GPG usage mirrors the repo's own pattern (build_release_archives.py /
validate_release.py): sign with --local-user <fingerprint>, verify with a
throwaway keyring seeded only from public/.well-known/pgp-key.asc.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import lib
import report

PUBLISHED_FINGERPRINT = "A729591B450D3F59369498BD82991F2504AE0263"

CAVEAT = (
    "This test result records the state of the publication at release time. It is "
    "not a guarantee of future network, browser or validator behaviour. It is a "
    "signed snapshot of the checks performed against the listed targets."
)


# --- paths / key -------------------------------------------------------------
def _repo_root():
    # tools/score-ledger/ -> repo root is two levels up
    return os.path.abspath(os.path.join(lib.HERE, "..", ".."))


def pgp_key_path(cfg):
    custom = (cfg.raw.get("signing") or {}).get("gpg_key")
    if custom:
        return custom
    return os.path.join(_repo_root(), "public", ".well-known", "pgp-key.asc")


def signing_fingerprint(cfg):
    """Configured fingerprint, else derived from the published public key."""
    fpr = (cfg.raw.get("signing") or {}).get("fingerprint")
    if fpr:
        return fpr.replace(" ", "")
    key = pgp_key_path(cfg)
    if not os.path.isfile(key):
        return PUBLISHED_FINGERPRINT
    try:
        out = subprocess.run(
            ["gpg", "--batch", "--with-colons", "--import-options", "show-only", "--import", key],
            capture_output=True,
            text=True,
            timeout=20,
        )
        for line in out.stdout.splitlines():
            if line.startswith("fpr:"):
                return line.split(":")[9]
    except Exception:
        pass
    return PUBLISHED_FINGERPRINT


# --- attestation text --------------------------------------------------------
def _min_num(metrics, name):
    vals = [
        m["value_numeric"]
        for m in metrics
        if m["metric"] == name and m["value_numeric"] is not None
    ]
    return min(vals) if vals else None


def _card(data, name):
    for c in data["scorecards"]:
        if c["name"] == name:
            return c["status"]
    return "n/a"


def _summary(data):
    metrics = data["metrics"]
    targets = data["targets"]

    # local accessors over the run's stored metrics, so each summary line
    # carries the evidence already collected rather than a scorecard pointer.
    def _nums(name):
        return [
            m["value_numeric"]
            for m in metrics
            if m["metric"] == name and m["value_numeric"] is not None
        ]

    def _maxn(name):
        v = _nums(name)
        return int(max(v)) if v else None

    def _text(name):
        for m in metrics:
            if m["metric"] == name and m["value_text"]:
                return m["value_text"]
        return None

    codes = [t["status_code"] for t in targets if t["status_code"] is not None]
    availability = "PASS" if codes and all(c == 200 for c in codes) else "REVIEW"
    acc = _min_num(metrics, "lighthouse.accessibility.score")
    seo = _min_num(metrics, "lighthouse.seo.score")
    html_err = max(_nums("html.errors.count") or [0])
    html_warn = max(_nums("html.warnings.count") or [0])
    html_status = "FAIL" if html_err else ("PASS WITH WARNINGS" if html_warn else "PASS")

    # privacy - cookies / third-party / unexpected storage keys / tracking
    ck = _maxn("privacy.cookies.count")
    tp = _maxn("privacy.third_party_resources.count")
    sk = _maxn("runtime_privacy.unapproved_storage_keys.count")
    priv_bits = []
    if ck is not None:
        priv_bits.append(f"{ck} cookie{'' if ck == 1 else 's'}")
    if tp is not None:
        priv_bits.append(f"{tp} third-party resource{'' if tp == 1 else 's'}")
    if sk is not None:
        priv_bits.append(f"{sk} unexpected storage key{'' if sk == 1 else 's'}")
    if any(m["value_bool"] for m in metrics if m["metric"] == "privacy.tracking_detected"):
        priv_bits.append("tracking detected")
    priv_detail = ", ".join(priv_bits) if priv_bits else "see Privacy scorecard"

    # security - mozilla observatory + ssl labs grades
    og = _text("security.observatory.grade")
    sg = _text("tls.ssl_labs.grade")
    sec_detail = (
        f"Observatory {og or '?'}, SSL Labs {sg or '?'}" if (og or sg) else "Observatory + SSL Labs"
    )

    # trust files - concrete presence of integrity.json + signature + core set
    req = [
        "trust.integrity_json.status_code",
        "trust.integrity_json_sig.status_code",
        "trust.pgp_key.status_code",
        "trust.security_txt.status_code",
        "trust.robots_txt.status_code",
        "trust.sitemap_xml.status_code",
    ]
    present = sum(1 for k in req if _maxn(k) == 200)
    total = sum(1 for k in req if _nums(k))
    have_sig = (
        _maxn("trust.integrity_json.status_code") == 200
        and _maxn("trust.integrity_json_sig.status_code") == 200
    )
    if total and present == total and have_sig:
        trust_detail = "integrity.json + signature present, all core trust files verified"
    elif total:
        trust_detail = f"{present}/{total} core trust files present"
    else:
        trust_detail = "core trust files"

    return [
        (
            "Availability",
            availability,
            f"{len([c for c in codes if c == 200])}/{len(codes)} target URLs returned 200"
            if codes
            else "no targets",
        ),
        ("Privacy", _card(data, "Privacy"), priv_detail),
        ("Security", _card(data, "Security"), sec_detail),
        (
            "Accessibility",
            "PASS" if acc == 100 else ("REVIEW" if acc is not None else "n/a"),
            f"Lighthouse accessibility min {int(acc) if acc is not None else '-'}",
        ),
        (
            "SEO",
            "PASS" if (seo or 0) >= 90 else ("REVIEW" if seo is not None else "n/a"),
            f"Lighthouse SEO min {int(seo) if seo is not None else '-'}",
        ),
        ("HTML", html_status, f"{int(html_err)} errors, {int(html_warn)} warning(s) max/page"),
        ("Trust files", _card(data, "Trust"), trust_detail),
    ]


def _perf_by_page(data):
    """[(path, score)] in target order (not sorted), so pages map to scores."""
    by_path = {
        m["path"]: int(m["value_numeric"])
        for m in data["metrics"]
        if m["metric"] == "lighthouse.performance.score" and m["value_numeric"] is not None
    }
    return [(t["path"], by_path[t["path"]]) for t in data["targets"] if t["path"] in by_path]


def build_testresults(conn, cfg, run_id, edition):
    data = report.gather(conn, cfg, run_id)
    run = data["run"]
    L = []
    L.append(f"{cfg.site_name} TESTRESULTS")
    L.append("")
    L.append(f"Edition:     {edition or run['edition'] or '-'}")
    L.append(f"Run:         #{run['id']}  ({run['run_label'] or 'no label'})")
    L.append(f"Generated:   {lib.now_utc_iso()}")
    L.append(f"Environment: {run['environment'] or '-'}")
    L.append(f"Git commit:  {run['git_commit'] or '-'}")
    L.append("")
    L.append("Targets:")
    for t in data["targets"]:
        L.append(f"- {t['url']}")
    L.append("")
    L.append("Summary:")
    for area, status, detail in _summary(data):
        L.append(f"- {area}: {status}, {lib.ascii_norm(detail)}")
    # Performance rendered per-page (not sorted) so scores map to pages
    perf_rows = _perf_by_page(data)
    perf_status = next(
        (c["status"] for c in data["scorecards"] if c["name"] == "Performance"), "n/a"
    )
    L.append(f"- Performance: {perf_status}")
    for path, score in perf_rows:
        L.append(f"  - {path}: {score}")
    if perf_status == "REVIEW":
        L.append(
            "  Reason: edition pages remain below the preferred 90 threshold, "
            "mainly Total Blocking Time"
        )
    L.append("")
    L.append("Key observations:")
    opens = [a for a in data["actions"] if a["status"] == "open"]
    opens.sort(key=lambda a: report.RANK.get(a["impact"], 3))
    if not opens:
        L.append("- No open actions flagged this run")
    for a in opens[:8]:
        title = lib.ascii_norm(a["title"])
        rationale = lib.ascii_norm(a["rationale"]) if a["rationale"] else ""
        extra = f" ({rationale})" if rationale and rationale != title else ""
        L.append(f"- [{a['impact']}] {a['target_path']}: {title}{extra}")
    L.append("")
    # Report pointer + evidence-chain hashes
    opens = [a for a in data["actions"] if a["status"] == "open"]
    noise = [a for a in data["actions"] if a["status"] == "known_noise"]
    L.append("Report:")
    L.append(f"- Ledger run: #{run['id']}")
    L.append(f"- Run report: run-{run['id']}.html, run-{run['id']}.md")
    L.append(f"- Metrics collected: {len(data['metrics'])}")
    L.append(f"- Open actions: {len(opens)}")
    L.append(f"- Known validator noise: {len(noise)}")
    L.append("")
    art = []
    reports_dir = cfg.reports_dir
    for name in (f"run-{run['id']}.md", f"run-{run['id']}.html"):
        p = os.path.join(reports_dir, name)
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                art.append((name, lib.sha256_bytes(fh.read())))
    if art:
        L.append("Artefacts (SHA-256):")
        for name, digest in art:
            L.append(f"- {name}: {digest}")
        L.append("")
    L.append("Interpretation:")
    L.append(lib.ascii_norm(CAVEAT))
    L.append("")
    L.append("Signed by:")
    L.append("Trent Power")
    L.append(f"PGP key fingerprint: {signing_fingerprint(cfg)}")
    L.append("")
    return "\n".join(L)


# --- signing / verification --------------------------------------------------
def sign_file(cfg, path):
    """Detached ASCII-armoured signature next to `path`. Never touches `path`."""
    fpr = signing_fingerprint(cfg)
    sig = path + ".sig"
    env = os.environ.copy()
    env.pop("GNUPGHOME", None)  # use the operator's keyring
    proc = subprocess.run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--local-user",
            fpr,
            "--detach-sign",
            "--armor",
            "-o",
            sig,
            path,
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        if os.path.exists(sig):  # remove any partial signature; leave path intact
            os.remove(sig)
        raise RuntimeError(f"gpg signing failed: {proc.stderr.strip()[:300]}")
    return sig


def verify_file(cfg, path, sig):
    """Verify with a throwaway keyring seeded only from the published key."""
    key = pgp_key_path(cfg)
    if not os.path.isfile(key):
        return False, f"published key not found at {key}"
    if not (os.path.isfile(path) and os.path.isfile(sig)):
        return False, "missing file or signature"
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["GNUPGHOME"] = tmp
        env.pop("GPG_AGENT_INFO", None)
        imp = subprocess.run(
            ["gpg", "--batch", "--quiet", "--import", key], env=env, capture_output=True, text=True
        )
        if imp.returncode != 0:
            return False, "could not import published key"
        v = subprocess.run(
            ["gpg", "--batch", "--quiet", "--verify", sig, path],
            env=env,
            capture_output=True,
            text=True,
        )
        if v.returncode != 0:
            return False, v.stderr.strip()[:300]
    return True, "signature verifies against published key"
