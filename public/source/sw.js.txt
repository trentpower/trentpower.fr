/*! trentpower.fr · /sw.js · generated · signed via /integrity.json */

var CACHE = 'tp-2026-06-10.f9f41383-09aa7227-edition-2026-05-17-editorial-cohesion-rev1';

// Critical precache — pages, core CSS/JS, manifest, favicon. Failure
// to cache any of these aborts install: an offline visit could not
// render a coherent page without them.
var CRITICAL_PRECACHE = [
  '/',
  '/en-au/',
  '/fr/',
  '/en-au/privacy/',
  '/fr/confidentialite/',
  '/en-au/security/',
  '/fr/securite/',
  '/en-au/security/acknowledgments/',
  '/fr/securite/remerciements/',
  '/en-au/integrity/',
  '/fr/integrite/',
  '/en-au/integrity/releases/',
  '/fr/integrite/archives/',
  '/en-au/integrity/verify-locally/',
  '/fr/integrite/verifier-localement/',
  '/en-au/verify/',
  '/fr/verifier/',
  '/en-au/source/',
  '/fr/source/',
  '/en-au/source/view/',
  '/fr/source/voir/',
  '/en-au/403.html',
  '/en-au/404.html',
  '/en-au/500.html',
  '/en-au/maintenance.html',
  '/fr/403.html',
  '/fr/404.html',
  '/fr/500.html',
  '/fr/maintenance.html',
  '/403.html',
  '/404.html',
  '/500.html',
  '/maintenance.html',
  '/local/',
  '/styles.css',
  '/print.css',
  '/fonts-full.css',
  '/js/theme.js',
  '/sw-register.js',
  '/js/reveal.js',
  '/js/verify-modal.js',
  '/js/copy.js',
  '/js/edition.js',
  '/js/fonts.js',
  '/js/overlay.js',
  '/js/micro-interactions.js',
  '/js/local.js',
  '/verify/verify.js',
  '/verify/verification-data.js',
  '/manifest.webmanifest',
  '/favicon.svg'
];

// Optional precache — fonts, platform icons (apple-touch / 192 / 512),
// architecture diagrams, QR codes. Failure to cache any of these is
// logged but never breaks install. Pages render with the CSS fallback
// stack if fonts are absent; missing platform icons only affect
// install/share UI, not the site itself.
var OPTIONAL_PRECACHE = [
  '/fonts/subsets/signifier-light-hero.woff2',
  '/fonts/subsets/soehne-kraftig-nav.woff2',
  '/fonts/subsets/soehne-mono-buch-labels.woff2',
  '/fonts/signifier-light.woff2',
  '/fonts/signifier-light-italic.woff2',
  '/fonts/signifier-regular.woff2',
  '/fonts/signifier-regular-italic.woff2',
  '/fonts/soehne-buch.woff2',
  '/fonts/soehne-kraftig.woff2',
  '/fonts/soehne-mono-buch.woff2',
  '/fonts/soehne-mono-kraftig.woff2',
  '/favicon.ico',
  '/apple-touch-icon.png',
  '/icon-192.png',
  '/icon-512.png',
  '/images/architecture/architecture.svg',
  '/images/architecture/architecture-mobile.svg',
  '/images/qr/print-qr-trentpower.svg',
  '/images/qr/qr-home.svg',
  '/images/qr/qr-privacy.svg',
  '/images/qr/qr-integrity.svg',
  '/images/qr/qr-security.svg',
  '/images/qr/qr-source.svg',
  '/images/qr/qr-verify.svg',
  '/images/qr/qr-releases.svg',
  '/images/qr/qr-acknowledgments.svg',
  '/images/qr/qr-release-2026-05-09.svg',
  '/images/qr/qr-verify-locally.svg',
  '/images/qr/qr-sw-reset.svg',
  '/images/qr/qr-maintenance.svg'
];

// Combined surface — install · activate · fetch
var PRECACHE = CRITICAL_PRECACHE.concat(OPTIONAL_PRECACHE);

var NEVER_CACHE = [
  '/integrity.json',
  '/integrity.json.sig',
  '/site-metadata.json',
  '/llms.txt',
  '/local/',
  '/local/index.html'
];

var NEVER_CACHE_PREFIX = [
  '/.well-known/'
];

function canonicalPath(pathname) {
  if (pathname === '/') return '/';
  if (pathname.indexOf('.') === -1 && pathname.charAt(pathname.length - 1) !== '/') {
    return pathname + '/';
  }
  return pathname;
}

function isNeverCache(pathname) {
  if (NEVER_CACHE.indexOf(pathname) !== -1) return true;
  for (var i = 0; i < NEVER_CACHE_PREFIX.length; i++) {
    if (pathname.indexOf(NEVER_CACHE_PREFIX[i]) === 0) return true;
  }
  return false;
}

// Install — two-tier precache.
// CRITICAL: fail loud. A single missing URL aborts install. Pages,
// core CSS/JS, manifest, favicon — without these the offline
// experience is incoherent.
// OPTIONAL: best-effort. Each URL caches independently; failures are
// logged via console.warn but never reject the install promise.
// Fonts / platform icons / diagrams / QR codes — pages render
// without them.
function _putReload(cache, u) {
  return fetch(u, { cache: 'reload', credentials: 'same-origin' })
    .then(function (r) {
      if (!r.ok) {
        throw new Error('precache failed: ' + u + ' (' + r.status + ')');
      }
      return cache.put(u, r);
    });
}

// _notifyClients — broadcast a small event to every controlled
// client so the in-page register listener can write tp-sw-meta to
// localStorage (install / activate / first cache rev). a clientless
// install (every client navigated away mid-precache) is fine — the
// next page load will read meta.lastCheckedAt from the diagnostics
// page and recompute. message is { type, at: Date.now() }; no
// payload beyond a millisecond epoch.
function _notifyClients(type) {
  try {
    return self.clients.matchAll({ includeUncontrolled: true }).then(function (cs) {
      var at = Date.now();
      (cs || []).forEach(function (c) {
        try { c.postMessage({ type: type, at: at }); } catch (_) {}
      });
    });
  } catch (_) { return Promise.resolve(); }
}

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (cache) {
      // Critical first — Promise.all rejects on any single failure.
      return Promise.all(CRITICAL_PRECACHE.map(function (u) {
        return _putReload(cache, u);
      })).then(function () {
        // Optional second — each URL gets its own catch so optional
        // failures never reject the outer promise. Promise.all here
        // resolves once all optional fetches have either succeeded
        // or quietly failed.
        return Promise.all(OPTIONAL_PRECACHE.map(function (u) {
          return _putReload(cache, u).catch(function (err) {
            console.warn('[sw] optional precache skipped:', u, err && err.message);
            return null;
          });
        }));
      });
    })
    .then(function () { return _notifyClients('tp-sw-installed'); })
    .then(function () { return self.skipWaiting(); })
  );
});

// SKIP_WAITING — the /local/ device console asks the waiting worker
// to take over when the reader presses "Skip waiting and reload".
// the message is fire-and-forget; the page reloads on the next tick.
self.addEventListener('message', function (e) {
  if (e.data && e.data.type === 'SKIP_WAITING') self.skipWaiting();
});

// Activate — drop old caches, claim clients immediately so the next
// navigation is served by this generation. record activated_at via
// postMessage to controlled clients so /local/ can show when the
// current SW edition took over on this device.
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(
        names.filter(function (n) { return n !== CACHE; })
             .map(function (n) { return caches.delete(n); })
      );
    })
    .then(function () { return self.clients.claim(); })
    .then(function () { return _notifyClients('tp-sw-activated'); })
  );
});

// Fetch — route by request type.
self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);

  if (e.request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;

  // Frozen archive assets: cache-first, immutable.
  if (/^\/integrity\/releases\/\d{4}-\d{2}\/assets\//.test(url.pathname)) {
    e.respondWith(
      caches.match(e.request, { ignoreSearch: true }).then(function (cached) {
        return cached || fetch(e.request).then(function (response) {
          var clone = response.clone();
          caches.open(CACHE).then(function (cache) { cache.put(e.request, clone); });
          return response;
        });
      })
    );
    return;
  }

  // Network-only: identity + signed manifest + .well-known.
  if (isNeverCache(url.pathname)) return;

  // Navigation: network-first, fallback to cached canonical, then '/'.
  if (e.request.mode === 'navigate') {
    var cacheKey = canonicalPath(url.pathname);
    e.respondWith(
      fetch(e.request).then(function (response) {
        var clone = response.clone();
        caches.open(CACHE).then(function (cache) { cache.put(cacheKey, clone); });
        return response;
      }).catch(function () {
        return caches.match(cacheKey, { ignoreSearch: true }).then(function (cached) {
          return cached || caches.match('/', { ignoreSearch: true });
        });
      })
    );
    return;
  }

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
  var fetchOpts = hasVersion ? { cache: 'no-store' } : {};
  e.respondWith(
    fetch(e.request, fetchOpts).then(function (response) {
      var clone = response.clone();
      caches.open(CACHE).then(function (cache) { cache.put(e.request, clone); });
      return response;
    }).catch(function () {
      if (hasVersion) {
        // Exact-URL match only — never serve a stale ?v=OLD entry
        // against a ?v=NEW request; the SRI would mismatch.
        return caches.match(e.request);
      }
      return caches.match(e.request, { ignoreSearch: true });
    })
  );
});
