/*
 * trentpower.fr · /js/local.js — local device console diagnostics.
 *
 * progressive-enhancement script for /local/. reads the browser's
 * service-worker registration, cache storage, storage estimate, and
 * the site-owned localStorage / sessionStorage keys; populates the
 * [data-local-field] placeholders authored in the local page template;
 * wires the [data-local-action] buttons.
 *
 * nothing on this page is transmitted. validator links are plain
 * <a target="_blank" rel="noopener noreferrer"> elements; they are
 * never auto-opened, never prefetched. the diagnostics object is
 * exposed on window.TP_LOCAL_DIAGNOSTICS so a reader can copy/export
 * it locally — never sent.
 *
 * Source: edited here as the local page-script template; compiled to
 * public/js/local.js by the build pipeline (minified, no
 * substitution). do not hand-edit the generated file.
 */
(function () {
  'use strict';

  /* ─── known storage keys ─────────────────────────────────────── */

  // every site-owned localStorage / sessionStorage key. drives the
  // raw-storage view and the clear-preferences action so we never
  // call localStorage.clear() blindly.
  var LOCAL_KEYS = [
    { key: 'tp-theme',                  storage: 'local',   prefix: false },
    { key: 'tp-last-edition',           storage: 'local',   prefix: false },
    { key: 'tp-last-read:/en-au/',      storage: 'local',   prefix: false },
    { key: 'tp-last-read:/fr/',         storage: 'local',   prefix: false },
    { key: 'tp-fr-disclosure-seen',     storage: 'local',   prefix: false },
    { key: 'tp-imprint-seen:en',        storage: 'local',   prefix: false },
    { key: 'tp-imprint-seen:fr',        storage: 'local',   prefix: false },
    { key: 'tp-sw-meta',                storage: 'local',   prefix: false },
    { key: 'tp-welcomed:',              storage: 'session', prefix: true  },
    { key: 'tp-typed-',                 storage: 'session', prefix: true  },
    { key: 'tp-skip-hero-anim',         storage: 'session', prefix: false },
    { key: 'tp-show-gate',              storage: 'session', prefix: false }
  ];

  /* ─── small helpers ──────────────────────────────────────────── */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function field(name) { return $('[data-local-field="' + name + '"]'); }

  function setField(name, value) {
    var el = field(name);
    if (!el) return;
    var code = el.querySelector('code');
    var target = code || el;
    target.textContent = value;
  }

  function safeStorage(kind) {
    try { return kind === 'session' ? window.sessionStorage : window.localStorage; }
    catch (_) { return null; }
  }

  function readJSON(storage, key) {
    if (!storage) return null;
    try { var raw = storage.getItem(key); return raw ? JSON.parse(raw) : null; }
    catch (_) { return null; }
  }

  function formatDate(ts) {
    if (!ts) return null;
    try {
      var d = new Date(ts);
      if (isNaN(d.getTime())) return null;
      var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
      return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate())
        + ' ' + pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()) + ' UTC';
    } catch (_) { return null; }
  }

  function formatDay(ts) {
    if (!ts) return null;
    try {
      var d = new Date(ts);
      if (isNaN(d.getTime())) return null;
      var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
      return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate());
    } catch (_) { return null; }
  }

  function formatBytes(n) {
    if (typeof n !== 'number' || !isFinite(n) || n < 0) return '—';
    var u = ['B', 'KB', 'MB', 'GB'];
    var i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return n.toFixed(i === 0 ? 0 : 1) + ' ' + u[i];
  }

  function parseEditionFromCacheName(name) {
    if (!name) return null;
    var m = String(name).match(/-edition-(\d{4}-\d{2}-\d{2})/) || String(name).match(/(\d{4}-\d{2}-\d{2})/);
    return m ? m[1] : null;
  }

  function parseBuildFromCacheName(name) {
    if (!name) return null;
    var m = String(name).match(/^tp-(\d{4}-\d{2}-\d{2}\.[0-9a-f]+)/);
    return m ? m[1] : null;
  }

  function languageLabel(value) {
    if (value === 'en-au') return 'English';
    if (value === 'fr')    return 'Français';
    return 'Not set (gate on next visit)';
  }

  function appearanceLabel(value) {
    if (value === 'light') return 'Light';
    if (value === 'dark')  return 'Dark';
    return 'Auto (system)';
  }

  /* ─── state ──────────────────────────────────────────────────── */

  var state = {
    sw: null,
    caches: [],
    cachedEdition: null,
    cachedBuild: null,
    storageEstimate: null,
    prefs: [],
    lastCheckedAt: null
  };

  function classifyPubStatus(live, cached) {
    if (!cached) return 'none';
    if (!live)   return 'unavailable';
    if (live === cached) return 'match';
    return live > cached ? 'older' : 'newer';
  }

  /* ─── diagnostics object ─────────────────────────────────────── */

  function buildDiagnostics() {
    var live = document.body.dataset.edition || null;
    var meta = readJSON(safeStorage('local'), 'tp-sw-meta') || {};
    return {
      generatedAt: new Date().toISOString(),
      page: {
        url: location.href,
        canonical: 'https://trentpower.fr/local/',
        edition: live,
        sha256Short: document.body.dataset.sourceSha256Short || null
      },
      serviceWorker: {
        state: swStateString(),
        scope: state.sw && state.sw.scope || null,
        scriptURL: state.sw && state.sw.active ? state.sw.active.scriptURL : null,
        installedAt: meta.installedAt || null,
        activatedAt: meta.activatedAt || null,
        lastCheckedAt: meta.lastCheckedAt || state.lastCheckedAt || null,
        lastUpdateCheckAt: meta.lastUpdateCheckAt || null,
        cachedEdition: state.cachedEdition,
        cachedBuild: state.cachedBuild
      },
      caches: state.caches.slice(),
      publication: {
        liveEdition: live,
        cachedEdition: state.cachedEdition,
        integrityManifestURL: '/integrity.json',
        signatureURL: '/integrity.json.sig',
        publicKeyURL: '/.well-known/pgp-key.asc',
        status: classifyPubStatus(live, state.cachedEdition)
      },
      preferences: state.prefs.slice(),
      storageEstimate: state.storageEstimate
    };
  }

  function swStateString() {
    if (!('serviceWorker' in navigator)) return 'unsupported';
    if (!state.sw) return 'unregistered';
    if (state.sw.installing) return 'installing';
    if (state.sw.waiting) return 'waiting';
    if (state.sw.active) return state.sw.active.state;
    return 'unknown';
  }

  /* ─── status strip ───────────────────────────────────────────── */

  function renderStrip() {
    var live = document.body.dataset.edition || '—';
    var s = swStateString();
    var swDisplay = (s === 'unsupported' || s === 'unregistered') ? s
                  : s === 'activated' ? 'Installed'
                  : s.charAt(0).toUpperCase() + s.slice(1);
    setField('strip.edition', 'Edition ' + live);
    setField('strip.sw', swDisplay);

    var prefsCount = countStoredPrefs();
    setField('strip.prefs', prefsCount === 1 ? '1 preference' : prefsCount + ' preferences');

    var cacheSize = state.storageEstimate && state.storageEstimate.usage
      ? formatBytes(state.storageEstimate.usage)
      : (state.caches.length ? state.caches.length + ' caches' : '—');
    setField('strip.cache', cacheSize);
  }

  function countStoredPrefs() {
    var n = 0;
    var lcl = safeStorage('local');
    if (!lcl) return 0;
    LOCAL_KEYS.forEach(function (spec) {
      if (spec.storage !== 'local') return;
      if (spec.prefix) {
        for (var i = 0; i < lcl.length; i++) {
          var k = lcl.key(i);
          if (k && k.indexOf(spec.key) === 0) n++;
        }
      } else if (lcl.getItem(spec.key) !== null) {
        n++;
      }
    });
    return n;
  }

  /* ─── publication-state card · summary + disclosures ─────────── */

  function renderPubState() {
    var live = document.body.dataset.edition || '—';
    var meta = readJSON(safeStorage('local'), 'tp-sw-meta') || {};
    var s = swStateString();

    // top summary line + pill tag
    var statusWord = s === 'activated' ? 'Installed'
                   : s === 'unregistered' ? 'Not registered'
                   : s === 'unsupported' ? 'Service workers unsupported'
                   : s.charAt(0).toUpperCase() + s.slice(1);
    var updatedDay = meta.activatedAt ? formatDay(meta.activatedAt) : (meta.installedAt ? formatDay(meta.installedAt) : '—');
    var summary = statusWord + ' · Edition ' + live + (updatedDay !== '—' ? ' · Updated ' + updatedDay : '');
    setField('pub.summary', summary);
    setField('pub.tag', statusWord);

    // SW disclosure summary + grid
    setField('sw.summary', statusWord);
    setField('sw.status', statusWord);
    setField('sw.scope', state.sw && state.sw.scope ? state.sw.scope : '—');
    setField('sw.installed_at', meta.installedAt ? formatDate(meta.installedAt) : 'Not recorded for this installation');
    setField('sw.activated_at', meta.activatedAt ? formatDate(meta.activatedAt) : 'Not recorded for this installation');
    setField('sw.version', state.cachedBuild || '—');
    setField('sw.cached_edition', state.cachedEdition || '—');
    setField('sw.cache_count', state.caches.length ? String(state.caches.length) : '—');
    setField('sw.storage_estimate',
      state.storageEstimate
        ? (formatBytes(state.storageEstimate.usage) + ' / ' + formatBytes(state.storageEstimate.quota))
        : '—');

    // toggle skip-waiting visibility
    var sw = $('.local-record [data-local-disclosure="sw"]');
    if (sw) {
      var skip = sw.querySelector('[data-local-action="skip-waiting"]');
      if (skip) skip.hidden = !(state.sw && state.sw.waiting);
    }

    // caches disclosure
    var entryTotal = state.caches.reduce(function (acc, c) { return acc + (c.count || 0); }, 0);
    var sizeText = state.storageEstimate && state.storageEstimate.usage
      ? formatBytes(state.storageEstimate.usage) : '—';
    setField('caches.summary', state.caches.length
      ? state.caches.length + ' cache · ' + entryTotal + ' entries · ' + sizeText
      : 'No caches');
    setField('caches.entries', String(entryTotal));
    setField('caches.size', sizeText);
    setField('caches.edition', state.cachedEdition || '—');
    setField('caches.cached_pages', state.caches.length ? String(state.caches[0].count) + ' (' + (state.caches[0].edition || 'unversioned') + ')' : '—');
    renderCachesInventory();

    // verification disclosure
    var sha = document.body.dataset.sourceSha256Short || '—';
    var pubStatus = classifyPubStatus(live, state.cachedEdition);
    var verifySummary =
      pubStatus === 'match'        ? 'Cached matches live · ' + live
    : pubStatus === 'older'        ? 'Cached older than live'
    : pubStatus === 'none'         ? 'No cached edition'
    : pubStatus === 'newer'        ? 'Cached newer than live'
    :                                'Verification data unavailable';
    setField('verify.summary', verifySummary);
    setField('verify.fingerprint', sha);
  }

  function renderCachesInventory() {
    var host = field('caches.list');
    if (!host) return;
    host.textContent = '';

    if (!('caches' in window)) {
      var p = document.createElement('p');
      p.className = 'local-empty';
      p.textContent = 'Cache Storage API not supported in this browser.';
      host.appendChild(p);
      return;
    }
    if (!state.caches.length) {
      var empty = document.createElement('p');
      empty.className = 'local-empty';
      empty.textContent = 'No caches found on this device.';
      host.appendChild(empty);
      return;
    }
    state.caches.forEach(function (c) {
      var card = document.createElement('details');
      card.className = 'local-cache';
      card.setAttribute('data-cache-name', c.name);

      var summary = document.createElement('summary');
      summary.className = 'local-cache__summary';
      var nameLine = document.createElement('code');
      nameLine.className = 'local-cache__name';
      nameLine.textContent = c.name;
      summary.appendChild(nameLine);
      var meta = document.createElement('span');
      meta.className = 'local-cache__meta';
      var bits = [c.count + ' entries'];
      if (c.edition) bits.push('Edition ' + c.edition);
      meta.textContent = bits.join(' · ');
      summary.appendChild(meta);
      card.appendChild(summary);

      var body = document.createElement('div');
      body.className = 'local-cache__body';
      var loading = document.createElement('p');
      loading.className = 'local-empty';
      loading.textContent = 'Reading headers…';
      loading.hidden = true;
      body.appendChild(loading);
      var ul = document.createElement('ul');
      ul.className = 'local-cache__entries';
      body.appendChild(ul);
      card.appendChild(body);

      var loaded = false;
      card.addEventListener('toggle', function () {
        if (!card.open || loaded) return;
        loaded = true;
        loading.hidden = false;
        loadCacheEntries(c.name).then(function (rows) {
          loading.hidden = true;
          rows.forEach(function (r) { ul.appendChild(r); });
        }).catch(function (err) {
          loading.textContent = 'Could not read · ' + (err && err.message || 'unknown');
        });
      });
      host.appendChild(card);
    });
  }

  function loadCacheEntries(name) {
    return caches.open(name).then(function (cache) {
      return cache.keys().then(function (reqs) {
        return Promise.all(reqs.map(function (req) {
          return cache.match(req).then(function (res) {
            var li = document.createElement('li');
            li.className = 'local-cache__entry';
            var u = document.createElement('code');
            u.className = 'local-cache__url';
            u.textContent = req.method + ' ' + req.url.replace(location.origin, '');
            li.appendChild(u);
            if (res) {
              var fields = document.createElement('span');
              fields.className = 'local-cache__fields';
              var bits = [];
              bits.push('type: ' + res.type);
              var lm = res.headers.get('last-modified');
              if (lm) bits.push('last-modified: ' + lm);
              var et = res.headers.get('etag');
              if (et) bits.push('etag: ' + et);
              var cl = res.headers.get('content-length');
              if (cl) bits.push('content-length: ' + cl);
              fields.textContent = bits.join(' · ');
              li.appendChild(fields);
            }
            return li;
          });
        }));
      });
    });
  }

  /* ─── preferences card · four fixed rows + raw view ──────────── */

  function collectPrefs() {
    var rows = [];
    var lcl = safeStorage('local');
    var sess = safeStorage('session');
    LOCAL_KEYS.forEach(function (spec) {
      var storage = spec.storage === 'session' ? sess : lcl;
      if (!storage) return;
      if (spec.prefix) {
        for (var i = 0; i < storage.length; i++) {
          var k = storage.key(i);
          if (!k || k.indexOf(spec.key) !== 0) continue;
          rows.push({ key: k, value: storage.getItem(k), storage: spec.storage });
        }
      } else {
        var v = storage.getItem(spec.key);
        if (v !== null) rows.push({ key: spec.key, value: v, storage: spec.storage });
      }
    });
    return rows;
  }

  function renderPrefs() {
    state.prefs = collectPrefs();
    var lcl = safeStorage('local');
    var lang = lcl ? (lcl.getItem('tp-last-edition') || '') : '';
    var theme = lcl ? (lcl.getItem('tp-theme') || '') : '';
    setField('pref.language', languageLabel(lang));
    setField('pref.appearance', appearanceLabel(theme));

    var meta = readJSON(lcl, 'tp-sw-meta') || {};
    var firstVisit = meta.installedAt ? formatDay(meta.installedAt) : 'No record yet';
    var lastUpdate = meta.lastCheckedAt ? formatDay(meta.lastCheckedAt) : (meta.activatedAt ? formatDay(meta.activatedAt) : 'No record yet');
    setField('pref.first_visit', firstVisit);
    setField('pref.last_update', lastUpdate);

    // mark active control buttons
    $$('[data-local-set-lang]').forEach(function (b) {
      var match = b.getAttribute('data-local-set-lang') === lang;
      b.classList.toggle('is-current', match);
    });
    $$('[data-local-set-theme]').forEach(function (b) {
      var match = b.getAttribute('data-local-set-theme') === theme;
      b.classList.toggle('is-current', match);
    });

    // raw JSON view
    var raw = field('raw.json');
    if (raw) {
      var dump = {
        localStorage: {},
        sessionStorage: {},
        cacheNames: state.caches.map(function (c) { return c.name; })
      };
      state.prefs.forEach(function (r) {
        var bucket = r.storage === 'session' ? 'sessionStorage' : 'localStorage';
        dump[bucket][r.key] = r.value;
      });
      var code = raw.querySelector('code');
      (code || raw).textContent = JSON.stringify(dump, null, 2);
    }
  }

  /* ─── actions · confirm-required + handlers ──────────────────── */

  function wireConfirm(btn, run) {
    var armed = false;
    var label = btn.textContent;
    var confirmLabel = btn.getAttribute('data-confirm-label') || 'Tap again to confirm';
    var timer = null;
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      if (armed) {
        clearTimeout(timer);
        btn.textContent = label;
        armed = false;
        btn.classList.remove('is-armed');
        return run();
      }
      btn.textContent = confirmLabel;
      btn.classList.add('is-armed');
      armed = true;
      timer = setTimeout(function () {
        btn.textContent = label;
        btn.classList.remove('is-armed');
        armed = false;
      }, 4000);
    });
  }

  function actionCheckUpdate() {
    if (!state.sw || !state.sw.update) return;
    var lcl = safeStorage('local');
    state.sw.update().then(function () {
      var meta = readJSON(lcl, 'tp-sw-meta') || {};
      meta.lastUpdateCheckAt = new Date().toISOString();
      try { lcl.setItem('tp-sw-meta', JSON.stringify(meta)); } catch (_) {}
      refresh();
    }).catch(refresh);
  }

  function actionSkipWaiting() {
    if (!state.sw || !state.sw.waiting) return;
    try { state.sw.waiting.postMessage({ type: 'SKIP_WAITING' }); } catch (_) {}
    setTimeout(function () { location.reload(); }, 200);
  }

  function actionResetCache() {
    var jobs = [];
    if ('serviceWorker' in navigator) {
      jobs.push(navigator.serviceWorker.getRegistrations().then(function (rs) {
        return Promise.all((rs || []).map(function (r) { return r.unregister(); }));
      }).catch(function () { return null; }));
    }
    if ('caches' in window) {
      jobs.push(caches.keys().then(function (ns) {
        return Promise.all((ns || []).map(function (n) { return caches.delete(n); }));
      }).catch(function () { return null; }));
    }
    Promise.all(jobs).then(refresh);
  }

  function actionReload() { location.reload(); }

  function actionClearPreferences() {
    var lcl = safeStorage('local');
    var sess = safeStorage('session');
    LOCAL_KEYS.forEach(function (spec) {
      var storage = spec.storage === 'session' ? sess : lcl;
      if (!storage) return;
      if (spec.prefix) {
        var rm = [];
        for (var i = 0; i < storage.length; i++) {
          var k = storage.key(i);
          if (k && k.indexOf(spec.key) === 0) rm.push(k);
        }
        rm.forEach(function (k) { try { storage.removeItem(k); } catch (_) {} });
      } else {
        try { storage.removeItem(spec.key); } catch (_) {}
      }
    });
    try { delete document.documentElement.dataset.theme; } catch (_) {}
    refresh();
  }

  function actionFullReset() {
    actionClearPreferences();
    actionResetCache();
    setTimeout(function () { location.href = '/'; }, 400);
  }

  function actionExportJson() {
    var data = JSON.stringify(buildDiagnostics(), null, 2);
    var blob = new Blob([data], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'trentpower-local-diagnostics.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function actionCopyJson(btn) {
    var data = JSON.stringify(buildDiagnostics(), null, 2);
    copyText(btn, data);
  }

  function actionCopyFingerprint(btn) {
    var sha = document.body.dataset.sourceSha256Short || '';
    if (!sha) return;
    copyText(btn, sha);
  }

  function copyText(btn, text) {
    var label = btn.textContent;
    function done() {
      btn.textContent = 'Copied · just now';
      btn.classList.add('is-acknowledging');
      setTimeout(function () {
        btn.textContent = label;
        btn.classList.remove('is-acknowledging');
      }, 1800);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, done);
    } else {
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed'; ta.style.left = '-9999px';
        document.body.appendChild(ta); ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        done();
      } catch (_) {}
    }
  }

  function setLanguage(value) {
    var lcl = safeStorage('local');
    if (!lcl) return;
    try {
      if (value) lcl.setItem('tp-last-edition', value);
      else lcl.removeItem('tp-last-edition');
    } catch (_) {}
    flashSaved('language');
    refresh();
  }

  function setAppearance(value) {
    var lcl = safeStorage('local');
    if (!lcl) return;
    try {
      if (value) {
        lcl.setItem('tp-theme', value);
        document.documentElement.dataset.theme = value;
      } else {
        lcl.removeItem('tp-theme');
        try { delete document.documentElement.dataset.theme; } catch (_) {}
      }
    } catch (_) {}
    flashSaved('appearance');
    refresh();
  }

  function flashSaved(name) {
    var el = document.querySelector('[data-local-saved="' + name + '"]');
    if (!el) return;
    el.hidden = false;
    setTimeout(function () { el.hidden = true; }, 1800);
  }

  /* ─── collect + refresh ──────────────────────────────────────── */

  function collectCaches() {
    if (!('caches' in window)) return Promise.resolve([]);
    return caches.keys().then(function (names) {
      return Promise.all((names || []).map(function (n) {
        return caches.open(n).then(function (c) {
          return c.keys().then(function (rs) {
            return { name: n, count: rs.length, edition: parseEditionFromCacheName(n) };
          });
        }).catch(function () {
          return { name: n, count: 0, edition: parseEditionFromCacheName(n) };
        });
      }));
    }).catch(function () { return []; });
  }

  function collectSW() {
    if (!('serviceWorker' in navigator)) return Promise.resolve(null);
    return navigator.serviceWorker.getRegistration().catch(function () { return null; });
  }

  function collectEstimate() {
    if (!navigator.storage || !navigator.storage.estimate) return Promise.resolve(null);
    return navigator.storage.estimate().catch(function () { return null; });
  }

  function refresh() {
    return Promise.all([collectSW(), collectCaches(), collectEstimate()]).then(function (r) {
      state.sw = r[0];
      state.caches = r[1] || [];
      state.cachedEdition = state.caches.length ? state.caches[0].edition : null;
      state.cachedBuild = state.caches.length ? parseBuildFromCacheName(state.caches[0].name) : null;
      state.storageEstimate = r[2];
      state.lastCheckedAt = new Date().toISOString();
      var lcl = safeStorage('local');
      if (lcl) {
        try {
          var meta = readJSON(lcl, 'tp-sw-meta') || {};
          meta.lastCheckedAt = state.lastCheckedAt;
          lcl.setItem('tp-sw-meta', JSON.stringify(meta));
        } catch (_) {}
      }
      renderStrip();
      renderPubState();
      renderPrefs();
      window.TP_LOCAL_DIAGNOSTICS = buildDiagnostics();
    });
  }

  /* ─── init ───────────────────────────────────────────────────── */

  function init() {
    // confirm-required + plain actions
    $$('[data-local-action]').forEach(function (btn) {
      var act = btn.getAttribute('data-local-action');
      var handler;
      switch (act) {
        case 'check-update':      handler = actionCheckUpdate; break;
        case 'skip-waiting':      handler = actionSkipWaiting; break;
        case 'reset-cache':       handler = actionResetCache; break;
        case 'reload':            handler = actionReload; break;
        case 'clear-preferences': handler = actionClearPreferences; break;
        case 'full-reset':        handler = actionFullReset; break;
        case 'export-json':       handler = actionExportJson; break;
        case 'copy-json':         handler = function () { actionCopyJson(btn); }; break;
        case 'copy-fingerprint':  handler = function () { actionCopyFingerprint(btn); }; break;
        default: return;
      }
      if (btn.hasAttribute('data-confirm-required')) wireConfirm(btn, handler);
      else btn.addEventListener('click', function (e) { e.preventDefault(); handler(); });
    });

    // preference controls (button-based, not radios)
    $$('[data-local-set-lang]').forEach(function (b) {
      b.addEventListener('click', function (e) { e.preventDefault(); setLanguage(b.getAttribute('data-local-set-lang')); });
    });
    $$('[data-local-set-theme]').forEach(function (b) {
      b.addEventListener('click', function (e) { e.preventDefault(); setAppearance(b.getAttribute('data-local-set-theme')); });
    });

    refresh();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
