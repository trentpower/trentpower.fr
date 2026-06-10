/*! trentpower.fr · /verify/verify.js · authored · signed via /integrity.json */
(function () {
  'use strict';

  var MAP = (typeof window !== 'undefined' && window.TP_VERIFICATION_MAP) || {};

  function getLang() {
    var t = document.documentElement.lang || 'en';
    return (typeof window.I18N === 'object' && window.I18N[t]) ? t : 'en';
  }
  function t(key, fallback) {
    var lang = getLang();
    var ref = (window.I18N && window.I18N[lang]) || {};
    var parts = key.split('.');
    for (var i = 0; i < parts.length; i++) {
      if (ref == null || typeof ref !== 'object') return fallback || '';
      ref = ref[parts[i]];
    }
    return (typeof ref === 'string') ? ref : (fallback || '');
  }

  function normalisePath(raw) {
    if (!raw) return '/';
    raw = String(raw).trim();
    if (!raw) return '/';
    if (raw.indexOf('//') !== -1) {
      try {
        var u = new URL(raw, location.origin);
        if (u.origin !== location.origin) return null;
        raw = u.pathname || '/';
      } catch (_) { return null; }
    }
    if (raw.charAt(0) !== '/') raw = '/' + raw;
    raw = raw.replace(/\/index\.html$/, '/');
    if (raw.indexOf('.') === -1 && raw.charAt(raw.length - 1) !== '/') raw += '/';
    return raw;
  }

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) n.setAttribute(k, attrs[k]);
    }
    if (text != null) n.textContent = text;
    return n;
  }

  function safeHref(path) {
    if (!path) return '#';
    if (path.charAt(0) === '/') return path;
    try {
      var u = new URL(path, location.origin);
      if (u.origin !== location.origin) return '#';
      return u.pathname + (u.search || '');
    } catch (_) { return '#'; }
  }

  // The "Verify locally" command blocks were removed by design: command-
  // line release verification belongs on /integrity/, where the full
  // signed-manifest workflow is already documented. /verify/ stays
  // purely a per-page record. The Connected records strip below points
  // visitors at /integrity.json and the release archive when they want
  // to drop into the command-line flow.

  // ─── Section: Page record ──────────────────────────────
  // Editorial dossier, not a metadata table. Each group is a small
  // mono label + value: Citation (serif body, the emotional centre)
  // followed by Location, Evidence, Fingerprint, Archive in mono.
  // Hairlines separate groups, not rows. Actions sit at the bottom
  // as quiet utility-link mono.

  // ─── micro-grid row helper (phase 33 rewrite) ──────────────────────────
  // emits one row of the record-grid:
  //   <div class="record-grid__row">
  //     <dt>LABEL</dt>
  //     <dd>VALUE</dd>
  //   </div>
  // value can be a string, a single dom node, or an array of nodes/strings
  // (joined with <br> for the multi-line evidence row). all paths/hashes
  // wrap cleanly via the css `overflow-wrap: anywhere; word-break: break-
  // word` rules on `.record-grid code`.
  function buildRecordRow(labelKey, labelFallback, valueNode) {
    var row = el('div', { 'class': 'record-grid__row' });
    row.appendChild(el('dt', null, t(labelKey, labelFallback)));
    var dd = el('dd');
    if (typeof valueNode === 'string') {
      dd.textContent = valueNode;
    } else if (Array.isArray(valueNode)) {
      valueNode.forEach(function (n, i) {
        if (i > 0) dd.appendChild(el('br'));
        if (typeof n === 'string') dd.appendChild(document.createTextNode(n));
        else                       dd.appendChild(n);
      });
    } else if (valueNode) {
      dd.appendChild(valueNode);
    }
    row.appendChild(dd);
    return row;
  }
  function recordLink(href, label) {
    var a = el('a', { href: safeHref(href) });
    a.appendChild(el('code', null, label));
    return a;
  }
  function recordCode(text) {
    return el('code', null, text);
  }
  // parse a "sha256-…" / "sha256:…" hash into its algorithm label and body.
  // shared by the page fingerprint and the per-edition history rows so the
  // parsing lives in exactly one place.
  function formatHash(raw) {
    var rawHash = String(raw || '');
    var algoMatch = rawHash.match(/^([a-z0-9]+)[-:]/i);
    return {
      raw: rawHash,
      algo: algoMatch ? algoMatch[1].toLowerCase() : 'sha256',
      body: algoMatch ? rawHash.slice(algoMatch[0].length) : rawHash,
    };
  }

  function buildThisPage(record) {
    // phase 33 · micro-grid record system. the card now reads as a
    // signed technical certificate: header (eyebrow + title +
    // status) above a definition-list of metadata rows (citation,
    // location, evidence, fingerprint, archive) below a hairline
    // actions strip. inspired by swiss archival records, museum
    // object labels, and printed release ledgers.
    // phase 51 · semantic upgrades — <section> → <article>, inner
    // <div class="verify-card__header"> → <header>. local var names
    // ('section', 'header') keep the diff minimal.
    var section = el('article', {
      'class': 'verify-card',
      'aria-labelledby': 'verify-record-title',
    });

    // ── header ── eyebrow + title + status line ─────────────────────
    var header = el('header', { 'class': 'verify-card__header' });
    header.appendChild(el('p', { 'class': 'eyebrow' },
      t('verify.thispage.kicker', 'Page record')));
    header.appendChild(el('h2', { 'id': 'verify-record-title' },
      record.title || ''));

    var statusBits = [];
    if (record.manifest_status === 'found') {
      statusBits.push(t('verify.thispage.status.short.signed', 'Signed'));
    }
    if (record.source) {
      statusBits.push(t('verify.thispage.status.short.source', 'Source'));
    }
    if (record.release) {
      statusBits.push(t('verify.thispage.status.short.archived', 'Archived'));
    }
    if (statusBits.length) {
      header.appendChild(el('p', { 'class': 'verify-status' },
        statusBits.join(' · ')));
    }
    section.appendChild(header);

    // ── record-grid ── one row per field ────────────────────────────
    var grid = el('dl', { 'class': 'record-grid' });

    if (record.citation) {
      var citeRow = buildRecordRow(
        'verify.thispage.group.citation', 'Citation',
        record.citation);
      // micro-int #10 · mark the citation <dd> so micro-interactions.js
      // can flash it italic→roman→italic on the 'tp:citation-copied'
      // event dispatched by copy.template.js. no floating pill —
      // the in-place "Cited · Edition …" label on the trigger keeps
      // doing the primary confirmation work.
      var citeDd = citeRow.querySelector('dd');
      if (citeDd) citeDd.classList.add('tp-citation');
      grid.appendChild(citeRow);
    }

    // phase 94 · trust-layer reorder. brief order:
    //   citation → source mirror → page fingerprint → canonical
    //   location → actions → release archive (collapsed).
    // citation is already emitted above; source mirror, fingerprint
    // and location follow here in that order. release archive moves
    // out of the grid and is appended as a <details> beneath the
    // actions strip (see below).

    // evidence · `<a><code>/source/…</code></a>` on line 1; meta
    // ("HTML · 26 KB · Validated 2026-05-11") as a `<span class=
    // "record-meta">` block below. `.record-meta` carries the
    // smaller mono / fg3 styling so the supporting bytes/date sit
    // visibly under the primary file path.
    if (record.source || record.file_type || record.size_label || record.validated) {
      var evDd = el('div');
      if (record.source) {
        // source mirror row points at the raw .txt mirror directly.
        // the polished source viewer is reached via the "view source
        // code" action below the card.
        evDd.appendChild(recordLink(record.source, record.source));
      }
      var metaBits = [];
      if (record.file_type)  metaBits.push(record.file_type);
      if (record.size_label) metaBits.push(record.size_label);
      if (record.validated) {
        var validatedPrefix = t('verify.thispage.validated_prefix', 'Validated');
        metaBits.push(validatedPrefix + ' ' + record.validated);
      }
      if (metaBits.length) {
        evDd.appendChild(el('span', { 'class': 'record-meta' },
          metaBits.join(' · ')));
      }
      grid.appendChild(buildRecordRow(
        'verify.thispage.group.evidence', 'Source mirror',
        evDd));
    }

    // fingerprint · quiet two-part rendering. a small mono kicker
    // ("sha256") sits above the hash itself in a <samp> with a bdi
    // wrapper for directional isolation and natural wrap rules from
    // the .page-hash + .record-grid samp rules. title + aria-label
    // keep the full string exposed for assistive tech and for the
    // copy-fingerprint action below. the algorithm prefix is no
    // longer crammed into the hash string — it reads as an archival
    // attribution, not a forensic blob. phase 67.
    if (record.sha256 && record.sha256 !== '(missing)') {
      var fpWrap = el('div', { 'class': 'record-fingerprint-block' });
      var fp = formatHash(record.sha256);
      // wrap the algo prefix in <abbr> so screen readers and hover
      // expand the acronym to its full meaning.
      var algoSpan = el('span', { 'class': 'record-fingerprint-algo' });
      algoSpan.appendChild(el('abbr', { 'title': 'Secure Hash Algorithm, 256-bit' }, fp.algo));
      fpWrap.appendChild(algoSpan);
      var fpCode = el('samp', {
        'class': 'record-fingerprint page-hash',
        'title': fp.raw,
        'aria-label': fp.raw,
      });
      fpCode.appendChild(el('bdi', {}, fp.body));
      fpWrap.appendChild(fpCode);
      grid.appendChild(buildRecordRow(
        'verify.thispage.group.fingerprint', 'Page fingerprint',
        fpWrap));
    }

    // canonical url (with route as a quiet second line when the page
    // canonical and route differ). reordered to follow fingerprint
    // per phase-94 trust-layer hierarchy.
    if (record.canonical || record.route || record.path) {
      var locParts = [];
      if (record.canonical) {
        locParts.push(recordLink(record.canonical, record.canonical));
      }
      var routeStr = record.route || record.path;
      if (routeStr && routeStr !== '/') {
        locParts.push(recordCode(routeStr));
      }
      if (locParts.length) {
        grid.appendChild(buildRecordRow(
          'verify.thispage.group.location', 'Canonical location',
          locParts));
      }
    }

    section.appendChild(grid);

    // ── actions strip ── copy citation / copy fingerprint /
    //    view source code (reader) / raw source mirror.
    var hasCitation    = !!record.citation;
    var hasFingerprint = !!(record.sha256 && record.sha256 !== '(missing)');
    var hasReader      = !!record.reader;
    var hasSource      = !!record.source;
    if (hasCitation || hasFingerprint || hasReader || hasSource) {
      var actions = el('nav', {
        'class': 'record-tools',
        'aria-label': t('verify.thispage.actions_label', 'Page record actions'),
      });
      if (hasCitation) {
        // the shared /copy.js delegated listener handles the click via
        // these data-copy-* attributes. citation copies opt into the
        // in-place confirmation (data-copy-mode="cite") — the button's
        // own label becomes "Cited · Edition YYYY-MM-DD" for ~1 s on
        // successful copy, then restores. aria-live still announces
        // "Citation copied" via the cite.overlay translation key.
        actions.appendChild(el('button', {
          type: 'button', 'class': 'record-inline-action',
          'data-copy-text': record.citation,
          'data-copy-feedback': t('cite.overlay.toast.citation_copied', 'Citation copied'),
          'data-copy-mode': 'cite'
        }, t('cite.overlay.action.copy_citation', 'Copy citation')));
      }
      if (hasFingerprint) {
        // fingerprint copy keeps the legacy textContent swap — the
        // button label is a verb ("Copy fingerprint") that reads well
        // as "Copied". the in-place inscription is reserved for
        // citation copies (where the edition matters).
        actions.appendChild(el('button', {
          type: 'button', 'class': 'record-inline-action',
          'aria-live': 'polite', 'aria-atomic': 'true',
          'data-copy-text': record.sha256,
          'data-copy-feedback': t('verify.action.copied', 'Copied')
        }, t('verify.action.copy_fingerprint', 'Copy fingerprint')));
      }
      if (hasReader) {
        actions.appendChild(el('a', { 'href': safeHref(record.reader), 'class': 'record-inline-action' },
          t('verify.action.view_source_code', 'View source code')));
      }
      if (hasSource && !hasReader) {
        // fallback for routes without a reader (e.g. /source/ itself has no .txt mirror)
        actions.appendChild(el('a', { 'href': safeHref(record.source), 'class': 'record-inline-action' },
          t('verify.action.open_source_mirror', 'Plain text')));
      }
      section.appendChild(actions);
    }

    // phase 95 · page availability history · collapsed dossier
    // beneath the page record. native <details> handles the toggle —
    // no js animation, keyboard + screen-reader behaviour comes for
    // free. when record.history is present the body renders a
    // newest-first list of editions with edition stamp, current
    // marker, short sha256 (full hash in title), and a link to
    // /integrity/releases/<edition>/. when only record.release is
    // present (legacy fallback) the body collapses to a single link
    // — same shape as before.
    // one archive <details> element, built by whichever branch applies
    // (full per-edition history, or the legacy single-release fallback).
    var archive;
    if (record.history && record.history.length) {
      archive = el('details', { 'class': 'verify-card__archive' });
      archive.appendChild(el('summary', { 'class': 'verify-card__archive-summary' },
        t('verify.thispage.history.heading', 'This page appears in')));

      // summary line · "First archived YYYY-MM-DD · Current in YYYY-MM-DD".
      // skipped when first_archived equals current edition (the prefix
      // would read as duplicate metadata against the current row).
      if (record.first_archived && record.edition &&
          record.first_archived !== record.edition) {
        var summary = el('p', { 'class': 'verify-card__history-summary' });
        summary.appendChild(document.createTextNode(
          t('verify.thispage.history.first_archived_prefix', 'First archived') +
          ' ' + record.first_archived + ' · ' +
          t('verify.thispage.history.current_in_prefix', 'Current in') +
          ' ' + record.edition
        ));
        archive.appendChild(summary);
      }

      // change status line · quiet italic-serif factual note.
      if (record.change_status) {
        var statusKey = 'verify.thispage.history.status.' + record.change_status;
        var statusFallback = (
          record.change_status === 'first'     ? 'First archived in this edition'   :
          record.change_status === 'unchanged' ? 'Unchanged since previous edition' :
          record.change_status === 'changed'   ? 'Changed since previous edition'   :
          ''
        );
        if (statusFallback) {
          archive.appendChild(el('p', { 'class': 'verify-card__history-status' },
            t(statusKey, statusFallback)));
        }
      }

      // history list · one row per edition, newest first.
      var list = el('ul', { 'class': 'verify-card__history' });
      for (var hi = 0; hi < record.history.length; hi++) {
        var entry = record.history[hi];
        var row = el('li', { 'class': 'verify-card__history-row' });

        var stampLabel =
          (t('verify.thispage.history.edition_prefix', 'Edition') + ' ' + entry.edition_date)
          .toUpperCase();
        row.appendChild(el('span', { 'class': 'he-edition' }, stampLabel));

        if (entry.current) {
          row.appendChild(el('span', { 'class': 'he-current' },
            t('verify.thispage.history.current_label', 'current')));
        }

        // short sha (algo prefix + first 8 chars). full hash + algo
        // exposed via title + aria-label for copy / screen-reader use.
        var hfp = formatHash(entry.sha256);
        var shortHash = hfp.body.length > 8 ? hfp.body.slice(0, 8) + '…' : hfp.body;
        var shaCode = el('code', {
          'class':      'he-sha',
          'title':      hfp.raw,
          'aria-label': hfp.raw,
        }, hfp.algo + ' ' + shortHash);
        row.appendChild(shaCode);

        row.appendChild(el('a', { 'class': 'he-link', 'href': safeHref(entry.release_path) },
          t('verify.thispage.history.view_release', 'View release')));

        list.appendChild(row);
      }
      archive.appendChild(list);

      section.appendChild(archive);

    } else if (record.release) {
      // legacy fallback · just the current release link (used when no
      // archived history is available, e.g. for pages that aren't yet
      // in any signed release manifest).
      archive = el('details', { 'class': 'verify-card__archive' });
      archive.appendChild(el('summary', { 'class': 'verify-card__archive-summary' },
        t('verify.thispage.group.archive', 'Release archive')));
      var archiveBody = el('p', { 'class': 'verify-card__archive-body' });
      archiveBody.appendChild(recordLink(record.release, record.release));
      archive.appendChild(archiveBody);
      section.appendChild(archive);
    }

    return section;
  }

  // Renderers
  // The h1 ("Verify this page") is i18n-bound and stays static. The
  // selected page is identified inside the page record card; the
  // hero never carries a contextual title.

  function renderSelected(record) {
    var root = document.getElementById('verify-root');
    if (!root) return;
    while (root.firstChild) root.removeChild(root.firstChild);

    // phase 33 · buildThisPage now emits its own `.verify-card`
    // section (the micro-grid certificate). no outer wrapper —
    // the page-record card is the only object on the page.
    // phase 95 · the decorative slip-stamp was dropped (it read as
    // gimmicky and competed with the new availability-history
    // dossier beneath the card). nothing to move out of the
    // template into #verify-root anymore.
    var card = buildThisPage(record);
    root.appendChild(card);
  }

  // renderGeneral was used when /verify/ was visited with no path. The
  // page now defaults to the homepage record instead, so a fresh visit
  // to /verify/ feels useful rather than empty. init() handles the
  // fallback chain , if the homepage record were ever missing from the
  // map (it shouldn't be), renderUnknown takes over.

  function renderUnknown(rawPath) {
    var root = document.getElementById('verify-root');
    if (!root) return;
    while (root.firstChild) root.removeChild(root.firstChild);

    // Calm notice for routes not in the verification map.
    var notice = el('section', { 'class': 'verify-unknown' });
    notice.appendChild(el('h2', { 'class': 'verify-section-heading' },
      t('verify.unknown.title', 'Route not in the verification map')));
    if (rawPath) {
      notice.appendChild(el('p', { 'class': 'verify-unknown-path' }, rawPath));
    }
    notice.appendChild(el('p', { 'class': 'verify-section-intro' },
      t('verify.unknown.body',
        'The published manifest only lists the canonical pages of trentpower.fr. Use the records below to inspect the manifest, signature and release archives directly.')));

    // Compact actions strip , Source · Integrity manifest · Release archive.
    // Mirrors .verify-thispage-actions so the fallback never reads as broken.
    var actions = el('p', { 'class': 'verify-unknown-actions' });
    function unknownLink(href, key, fallback) {
      var a = el('a', { 'class': 'verify-unknown-action', 'href': href },
        t(key, fallback));
      return a;
    }
    function unknownSep() {
      return el('span', { 'class': 'verify-unknown-actions-sep', 'aria-hidden': 'true' }, ' · ');
    }
    actions.appendChild(unknownLink('/source/',
      'verify.unknown.action.source', 'Source'));
    actions.appendChild(unknownSep());
    actions.appendChild(unknownLink('/integrity.json',
      'verify.unknown.action.manifest', 'Integrity manifest'));
    actions.appendChild(unknownSep());
    actions.appendChild(unknownLink('/integrity/releases/',
      'verify.unknown.action.releases', 'Release archive'));
    notice.appendChild(actions);

    root.appendChild(notice);
  }

  function init() {
    var qs = new URLSearchParams(location.search);
    var raw = qs.get('path');
    // Default to the homepage record when no ?path= is supplied , a
    // fresh visit to /verify/ should land on a real public record, not
    // an empty page. The homepage is the canonical default.
    var norm = raw ? normalisePath(raw) : '/';
    if (norm === null) { renderUnknown(String(raw).slice(0, 80)); return; }
    var record = MAP[norm];
    if (record) renderSelected(record);
    else        renderUnknown(norm);
  }

  // Re-render when the language switcher fires (lang attribute changes).
  var observer = new MutationObserver(function (mutations) {
    for (var i = 0; i < mutations.length; i++) {
      if (mutations[i].attributeName === 'lang') { init(); break; }
    }
  });
  observer.observe(document.documentElement, { attributes: true });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

/* phase 95 · the slip-stamp bfcache suppressor was removed alongside
   the stamp itself. nothing currently needs a pageshow hook; this
   file no longer registers one. */
