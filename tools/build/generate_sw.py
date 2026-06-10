#!/usr/bin/env python3
"""generate_sw.py — Generate sw.js from the public inventory.

The PRECACHE list is derived from tools/public_inventory.py (the
single source of truth shared with the gate's sw-precache check in
inline_checks.py). The cache name
carries (a) the asset_version (JS+CSS bundle hash, written by
generate_site.py) and (b) a precache_hash of every precached file's
bytes — so any change to a font, icon, page or svg busts the cache for
returning visitors automatically.

Invoked by tools/build.sh after generate_site.py. The script resolves
its own absolute paths via _TOOLS_DIR/public — runnable from any cwd.
"""

import hashlib
import importlib.util
import json
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
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
from paths import PUBLIC_DIR as _PATHS_PUBLIC_DIR  # noqa: E402
from paths import TOOLS_DIR as _PATHS_TOOLS_DIR  # noqa: E402

ROOT = str(_PATHS_PUBLIC_DIR)
os.chdir(ROOT)

# import the shared inventory module — public_inventory.py lives in
# tools/ alongside this script (was scripts/ pre-reorg).
_inv_path = _PATHS_TOOLS_DIR / "lib" / "public_inventory.py"
_spec = importlib.util.spec_from_file_location("public_inventory", _inv_path)
inventory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inventory)

# ─── release identity ────────────────────────────────────────
# the cache name has three parts:
#   tp-{asset_version}-{precache_hash[:8]}-{RELEASE_TAG}
# asset_version covers the js+css bundle; precache_hash covers fonts,
# icons, svgs and pages too. RELEASE_TAG is a free-form name carried
# alongside, useful for grepping deploy logs.
RELEASE_TAG = "edition-2026-05-17-editorial-cohesion-rev1"

_sm_path = "site-metadata.json"
if not os.path.exists(_sm_path):
    print(f"ERROR: {_sm_path} not found — run generate_site.py first", file=sys.stderr)
    sys.exit(1)
with open(_sm_path, encoding="utf-8") as _fp:
    _sm = json.load(_fp)
_asset_version = _sm.get("asset_version")
if not _asset_version:
    print(f"ERROR: {_sm_path} has no asset_version — run generate_site.py first", file=sys.stderr)
    sys.exit(1)


# ─── validate every precache file exists on disk ──────────────
# Two-tier precache: the "critical" set must install or the sw does
# not commit; the "optional" set is best-effort and never breaks
# install. the gate's sw_precache check still requires every url in
# either tier to resolve to a real file at build time — the runtime tolerance
# is for transient network errors at install, not missing build
# artefacts.
CRITICAL_PRECACHE = inventory.critical_precache_paths()
OPTIONAL_PRECACHE = inventory.optional_precache_paths()
PRECACHE = CRITICAL_PRECACHE + OPTIONAL_PRECACHE  # full surface for the gate

missing = []
for url in PRECACHE:
    disk = inventory.url_to_disk_path(url)
    if not os.path.exists(disk):
        missing.append((url, disk))
if missing:
    print(f"ERROR: {len(missing)} PRECACHE entries do not resolve on disk:", file=sys.stderr)
    for url, disk in missing:
        print(f"  {url}  →  {disk}  (missing)", file=sys.stderr)
    sys.exit(1)


# ─── precache_hash — covers every precached file's bytes ──────
# sha256 over (url\0sha256(bytes))* in deterministic order. the first
# 8 hex chars go into the cache name; any byte change to any precached
# file changes the cache name → activate cleanup runs → returning
# visitors get the fresh bundle without manual cache-bust.
#
# Self-referential exclusion: two precache entries are meta-listings
# whose bytes derive from other precached files' hashes, so including
# them would feed back into the next build's precache_hash:
#   /source/ — embeds the sha256 of every public file (including sw.js)
#   /verify/verification-data.js — embeds per-page sha256 records
# both are still precached (and serve offline); they just don't drive
# the cache-name fingerprint. the underlying file hashes are already
# captured directly via their own entries.
_HASH_EXCLUDE = {"/source/", "/verify/verification-data.js"}

_h = hashlib.sha256()
for url in PRECACHE:
    if url in _HASH_EXCLUDE:
        continue
    disk = inventory.url_to_disk_path(url)
    _h.update(url.encode("utf-8"))
    _h.update(b"\0")
    with open(disk, "rb") as fp:
        _h.update(hashlib.sha256(fp.read()).digest())
_precache_hash = _h.hexdigest()[:8]

SW_CACHE = f"tp-{_asset_version}-{_precache_hash}-{RELEASE_TAG}"


# ─── Sanity: css references the active fonts ──────────────────
# critical fonts live in styles.css; full editorial weights live in
# fonts-full.css (loaded post-lcp). check both — warn only if a
# public font appears in neither.
with open("styles.css", encoding="utf-8") as f:
    _css = f.read()
_fonts_full = ""
try:
    with open("fonts-full.css", encoding="utf-8") as f:
        _fonts_full = f.read()
except FileNotFoundError:
    pass
for font in inventory.PUBLIC_FONTS:
    base = os.path.basename(font)
    if base not in _css and base not in _fonts_full:
        print(f"WARNING: neither styles.css nor fonts-full.css references {base}", file=sys.stderr)


# ─── emit sw.js ───────────────────────────────────────────────
# - Install: per-URL fetch + cache.put. one bad url fails install
#   loudly with that url named in the console; cache.addAll's silent
#   all-or-nothing was the previous fragility.
# - Frozen-archive assets cache-first.
# - NETWORK_ONLY paths and /.well-known/ pass through untouched.
# - Navigations: network-first, fallback to cached canonical, then '/'.
# - active assets: network-first with ignoresearch on the cache lookup
#   (so ?v=… asset-version queries still resolve to the precached
#   bare entry on first offline visit).

_critical_lines = ",\n".join(f"  '{u}'" for u in CRITICAL_PRECACHE)
_optional_lines = ",\n".join(f"  '{u}'" for u in OPTIONAL_PRECACHE)
_never_cache_lines = ",\n".join(f"  '{u}'" for u in inventory.NETWORK_ONLY)
_never_prefix_lines = ",\n".join(f"  '{p}'" for p in inventory.NETWORK_ONLY_PREFIXES)

SW = f"""/*! trentpower.fr · /sw.js · generated · signed via /integrity.json */

var CACHE = '{SW_CACHE}';

// Critical precache — pages, core CSS/JS, manifest, favicon. Failure
// to cache any of these aborts install: an offline visit could not
// render a coherent page without them.
var CRITICAL_PRECACHE = [
{_critical_lines}
];

// Optional precache — fonts, platform icons (apple-touch / 192 / 512),
// architecture diagrams, QR codes. Failure to cache any of these is
// logged but never breaks install. Pages render with the CSS fallback
// stack if fonts are absent; missing platform icons only affect
// install/share UI, not the site itself.
var OPTIONAL_PRECACHE = [
{_optional_lines}
];

// Combined surface — install · activate · fetch
var PRECACHE = CRITICAL_PRECACHE.concat(OPTIONAL_PRECACHE);

var NEVER_CACHE = [
{_never_cache_lines}
];

var NEVER_CACHE_PREFIX = [
{_never_prefix_lines}
];

function canonicalPath(pathname) {{
  if (pathname === '/') return '/';
  if (pathname.indexOf('.') === -1 && pathname.charAt(pathname.length - 1) !== '/') {{
    return pathname + '/';
  }}
  return pathname;
}}

function isNeverCache(pathname) {{
  if (NEVER_CACHE.indexOf(pathname) !== -1) return true;
  for (var i = 0; i < NEVER_CACHE_PREFIX.length; i++) {{
    if (pathname.indexOf(NEVER_CACHE_PREFIX[i]) === 0) return true;
  }}
  return false;
}}

// Install — two-tier precache.
// CRITICAL: fail loud. A single missing URL aborts install. Pages,
// core CSS/JS, manifest, favicon — without these the offline
// experience is incoherent.
// OPTIONAL: best-effort. Each URL caches independently; failures are
// logged via console.warn but never reject the install promise.
// Fonts / platform icons / diagrams / QR codes — pages render
// without them.
function _putReload(cache, u) {{
  return fetch(u, {{ cache: 'reload', credentials: 'same-origin' }})
    .then(function (r) {{
      if (!r.ok) {{
        throw new Error('precache failed: ' + u + ' (' + r.status + ')');
      }}
      return cache.put(u, r);
    }});
}}

// _notifyClients — broadcast a small event to every controlled
// client so the in-page register listener can write tp-sw-meta to
// localStorage (install / activate / first cache rev). a clientless
// install (every client navigated away mid-precache) is fine — the
// next page load will read meta.lastCheckedAt from the diagnostics
// page and recompute. message is {{ type, at: Date.now() }}; no
// payload beyond a millisecond epoch.
function _notifyClients(type) {{
  try {{
    return self.clients.matchAll({{ includeUncontrolled: true }}).then(function (cs) {{
      var at = Date.now();
      (cs || []).forEach(function (c) {{
        try {{ c.postMessage({{ type: type, at: at }}); }} catch (_) {{}}
      }});
    }});
  }} catch (_) {{ return Promise.resolve(); }}
}}

self.addEventListener('install', function (e) {{
  e.waitUntil(
    caches.open(CACHE).then(function (cache) {{
      // Critical first — Promise.all rejects on any single failure.
      return Promise.all(CRITICAL_PRECACHE.map(function (u) {{
        return _putReload(cache, u);
      }})).then(function () {{
        // Optional second — each URL gets its own catch so optional
        // failures never reject the outer promise. Promise.all here
        // resolves once all optional fetches have either succeeded
        // or quietly failed.
        return Promise.all(OPTIONAL_PRECACHE.map(function (u) {{
          return _putReload(cache, u).catch(function (err) {{
            console.warn('[sw] optional precache skipped:', u, err && err.message);
            return null;
          }});
        }}));
      }});
    }})
    .then(function () {{ return _notifyClients('tp-sw-installed'); }})
    .then(function () {{ return self.skipWaiting(); }})
  );
}});

// SKIP_WAITING — the /local/ device console asks the waiting worker
// to take over when the reader presses "Skip waiting and reload".
// the message is fire-and-forget; the page reloads on the next tick.
self.addEventListener('message', function (e) {{
  if (e.data && e.data.type === 'SKIP_WAITING') self.skipWaiting();
}});

// Activate — drop old caches, claim clients immediately so the next
// navigation is served by this generation. record activated_at via
// postMessage to controlled clients so /local/ can show when the
// current SW edition took over on this device.
self.addEventListener('activate', function (e) {{
  e.waitUntil(
    caches.keys().then(function (names) {{
      return Promise.all(
        names.filter(function (n) {{ return n !== CACHE; }})
             .map(function (n) {{ return caches.delete(n); }})
      );
    }})
    .then(function () {{ return self.clients.claim(); }})
    .then(function () {{ return _notifyClients('tp-sw-activated'); }})
  );
}});

// Fetch — route by request type.
self.addEventListener('fetch', function (e) {{
  var url = new URL(e.request.url);

  if (e.request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;

  // Frozen archive assets: cache-first, immutable.
  if (/^\\/integrity\\/releases\\/\\d{{4}}-\\d{{2}}\\/assets\\//.test(url.pathname)) {{
    e.respondWith(
      caches.match(e.request, {{ ignoreSearch: true }}).then(function (cached) {{
        return cached || fetch(e.request).then(function (response) {{
          var clone = response.clone();
          caches.open(CACHE).then(function (cache) {{ cache.put(e.request, clone); }});
          return response;
        }});
      }})
    );
    return;
  }}

  // Network-only: identity + signed manifest + .well-known.
  if (isNeverCache(url.pathname)) return;

  // Navigation: network-first, fallback to cached canonical, then '/'.
  if (e.request.mode === 'navigate') {{
    var cacheKey = canonicalPath(url.pathname);
    e.respondWith(
      fetch(e.request).then(function (response) {{
        var clone = response.clone();
        caches.open(CACHE).then(function (cache) {{ cache.put(cacheKey, clone); }});
        return response;
      }}).catch(function () {{
        return caches.match(cacheKey, {{ ignoreSearch: true }}).then(function (cached) {{
          return cached || caches.match('/', {{ ignoreSearch: true }});
        }});
      }})
    );
    return;
  }}

  // Active assets: network-first.
  //
  // For ?v=... cache-bust URLs the cache fallback MUST NOT use
  // ignoreSearch — a request for ?v=NEW that misses the network
  // would otherwise return ?v=OLD's cached bytes, whose hash no
  // longer matches the new HTML's SRI and gets blocked by the
  // browser. Fresh visitors on a new build would render unstyled
  // until they cleared the SW. The fix: bypass HTTP cache entirely
  // for versioned requests, and only fall back to an EXACT-URL
  // cache match (so a missing entry returns undefined → network
  // error → no stale-version SRI mismatch).
  //
  // Unversioned requests (precache members like '/', favicons,
  // .well-known, frozen archive bytes already routed above) keep
  // the ignoreSearch fallback so the offline experience still
  // works for those.
  var hasVersion = url.search.indexOf('v=') !== -1;
  var fetchOpts = hasVersion ? {{ cache: 'no-store' }} : {{}};
  e.respondWith(
    fetch(e.request, fetchOpts).then(function (response) {{
      var clone = response.clone();
      caches.open(CACHE).then(function (cache) {{ cache.put(e.request, clone); }});
      return response;
    }}).catch(function () {{
      if (hasVersion) {{
        // Exact-URL match only — never serve a stale ?v=OLD entry
        // against a ?v=NEW request; the SRI would mismatch.
        return caches.match(e.request);
      }}
      return caches.match(e.request, {{ ignoreSearch: true }});
    }})
  );
}});
"""

with open("sw.js", "w", encoding="utf-8") as f:
    f.write(SW)

# companion machine-readable manifest. restates the sw's cache list
# in a transparent, signed-by-integrity.json artefact so external
# verifiers don't have to parse js to enumerate what the sw caches.
# the list here is the single source of truth — sw.js itself is
# generated from the same `inventory` module above.
with open("sw-cache-manifest.json", "w", encoding="utf-8") as fp:
    json.dump(
        {
            "schema": "https://trentpower.fr/sw-cache-manifest.json",
            "site": "https://trentpower.fr",
            "cache_name": SW_CACHE,
            "edition": _asset_version.split(".")[0],
            "asset_version": _asset_version,
            "release_tag": RELEASE_TAG,
            "critical": list(inventory.critical_precache_paths()),
            "optional": list(inventory.optional_precache_paths()),
            "network_only": list(inventory.NETWORK_ONLY),
            "network_only_prefixes": list(inventory.NETWORK_ONLY_PREFIXES),
            "principle": (
                "Critical assets MUST cache or install fails. Optional assets "
                "are best-effort; failures are logged via console.warn and "
                "never break SW install. Network-only paths are always fetched "
                "live (signed manifest, identity files, .well-known/*)."
            ),
        },
        fp,
        indent=2,
        ensure_ascii=False,
    )
    fp.write("\n")

print(f"✓ sw.js generated — CACHE: {SW_CACHE}")
print(f"  precache entries: {len(PRECACHE)}")
print(f"    pages:    {len(inventory.PUBLIC_PAGES)}")
print(f"    styles:   {len(inventory.PUBLIC_STYLES)}")
print(f"    scripts:  {len(inventory.PUBLIC_SCRIPTS)}")
print(f"    fonts:    {len(inventory.PUBLIC_FONTS)}")
print(f"    icons:    {len(inventory.PUBLIC_ICONS)}")
print(f"    diagrams: {len(inventory.PUBLIC_DIAGRAMS)}")
print(
    f"  network-only paths: {len(inventory.NETWORK_ONLY)} (+ {len(inventory.NETWORK_ONLY_PREFIXES)} prefix)"
)
