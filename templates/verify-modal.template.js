/*
  trentpower.fr
  verify modal — action menu

  Role:
  renders the four-row action menu opened by the footer "verify"
  button. handoff layer whose primary action is the dedicated /verify/
  page — the modal never duplicates that page's record. peer of the
  language gate and access modals; same `.shell` / `.shell-close` /
  `.modal-shell-scrim` family, same focus trap / esc / scrim-click
  lifecycle exposed by overlay.js as window.TP_OVERLAY.

  Hierarchy:
  verify is the user-facing trust hub; integrity is the deeper
  technical archive linked from /verify/. the modal therefore leads
  with "verify this page" (primary, hands off to /verify/) and does
  not surface /integrity/ as a peer action — that promotion would
  split the trust layer and weaken the verify destination.

  Source:
  edited here as verify-modal.template.js; compiled to
  /js/verify-modal.js by generate_site.py, which substitutes the
  edition literal so the citation string matches the active release.

  Data:
  window.TP_VERIFICATION_MAP, built by generate_verification_map.py,
  is the single record source shared with /verify/. loaded as a
  sibling script on every active html so the modal carries a full
  citation, source link and slug on every page.

  Constraints:
  - no fetch; csp connect-src 'none' is preserved
  - no inline event handlers; csp script-src 'self' plus nonces holds
  - no tracking, no third-party scripts
  - no floating toast — the row itself becomes the confirmation
*/

(function () {
  'use strict';

  var EDITION = '2026-05-02';

  // this file's own UI vocabulary, both editions. the modal is built
  // by script, so its labels live here; they are picked off the page's
  // <html lang>. no translation runtime, no window.I18N. keys not
  // listed here (e.g. per-page citation titles) fall through to the
  // caller's fallback, which resolves from the page's own title. the
  // string set must stay in sync with content/<lang>/shared.yml under
  // the `verify_modal:` block; the YAML is the editorial source of
  // truth surfaced in /editorial/editorial-copy-review/.
  var LABELS = {
    en: {
      'verify_modal.title': 'Verify, cite or read the source.',
      'verify_modal.menu_label': 'Page verification actions',
      'verify_modal.row.source_verb': 'View this page’s source',
      'verify_modal.row.source_meta': 'Cmd + U',
      'verify_modal.row.source_meta_touch': 'Source mirror · HTML edition',
      'verify_modal.row.copy_verb': 'Copy citation',
      'verify_modal.row.copy_copied': 'Copied to clipboard',
      'verify_modal.row.page_verb': 'Verify this page',
      'verify_modal.row.page_meta': 'Publication record · Verification',
      'verify_modal.row.print_verb': 'Print this page',
      'verify_modal.row.print_meta': 'Cmd + P',
      'verify_modal.row.print_meta_touch': 'Print or export PDF',
      'verify_modal.close': 'Close',
      'cite.site_label': 'Personal Site',
      'cite.edition_label': 'Edition',
      // page_title.* survives from the previous overlay so the modal
      // can present a curated per-page title in the kicker line. the
      // verification map's title is "client strategy & growth systems
      // · trent power" — too long for a single line — so each page
      // carries an editorial short title here.
      'cite.overlay.page_title.home': 'Client Strategy & Growth Systems',
      'cite.overlay.page_title.privacy': 'Privacy statement',
      'cite.overlay.page_title.security': 'Security posture',
      'cite.overlay.page_title.integrity': 'Integrity record',
      'cite.overlay.page_title.verify': 'Verify page',
      'cite.overlay.page_title.source': 'Source reader',
      'cite.overlay.page_title.source-reader': 'Source reader',
      'cite.overlay.page_title.acknowledgments': 'Security acknowledgements',
      'cite.overlay.page_title.integrity-verify-locally': 'Verify locally',
      'cite.overlay.page_title.releases': 'Release archive',
      'cite.overlay.page_title.release-archive': 'Release archive',
      'cite.overlay.page_title.forbidden': 'Access not available',
      'cite.overlay.page_title.not-found': 'Page not found',
      'cite.overlay.page_title.server-error': 'Temporary server error',
      'cite.overlay.page_title.maintenance': 'Down for maintenance',
      'cite.overlay.page_title.sw-reset': 'Service worker reset'
    },
    fr: {
      'verify_modal.title': 'Vérifier, citer ou lire la source.',
      'verify_modal.menu_label': 'Actions de vérification de la page',
      'verify_modal.row.source_verb': 'Voir la source de cette page',
      'verify_modal.row.source_meta': 'Cmd + U',
      'verify_modal.row.source_meta_touch': 'Miroir source · édition HTML',
      'verify_modal.row.copy_verb': 'Copier la citation',
      'verify_modal.row.copy_copied': 'Copié dans le presse-papiers',
      'verify_modal.row.page_verb': 'Vérifier cette page',
      'verify_modal.row.page_meta': 'Dossier de publication · vérification',
      'verify_modal.row.print_verb': 'Imprimer cette page',
      'verify_modal.row.print_meta': 'Cmd + P',
      'verify_modal.row.print_meta_touch': 'Imprimer ou exporter en PDF',
      'verify_modal.close': 'Fermer',
      'cite.site_label': 'Site personnel',
      'cite.edition_label': 'Édition',
      'cite.overlay.page_title.home': 'Stratégie client et systèmes de croissance',
      'cite.overlay.page_title.privacy': 'Notice de confidentialité',
      'cite.overlay.page_title.security': 'Posture de sécurité',
      'cite.overlay.page_title.integrity': 'Notice d’intégrité',
      'cite.overlay.page_title.verify': 'Page de vérification',
      'cite.overlay.page_title.source': 'Lecteur de code source',
      'cite.overlay.page_title.source-reader': 'Lecteur de code source',
      'cite.overlay.page_title.acknowledgments': 'Remerciements de sécurité',
      'cite.overlay.page_title.integrity-verify-locally': 'Vérifier localement',
      'cite.overlay.page_title.releases': 'Archive des versions',
      'cite.overlay.page_title.release-archive': 'Archive des versions',
      'cite.overlay.page_title.forbidden': 'Accès non disponible',
      'cite.overlay.page_title.not-found': 'Page introuvable',
      'cite.overlay.page_title.server-error': 'Erreur serveur temporaire',
      'cite.overlay.page_title.maintenance': 'Maintenance en cours',
      'cite.overlay.page_title.sw-reset': 'Réinitialisation du service worker'
    }
  };

  function getLang() {
    return document.documentElement.lang === 'fr' ? 'fr' : 'en';
  }
  function tt(key, fallback) {
    var bag = LABELS[getLang()] || LABELS.en;
    var v = bag[key];
    return (typeof v === 'string') ? v : (fallback || '');
  }

  // ─── path normalisation: same shape as /verify/'s normalisepath ────────
  function normalisePath(raw) {
    if (!raw) return '/';
    raw = String(raw).trim();
    if (!raw) return '/';
    if (raw.charAt(0) !== '/') raw = '/' + raw;
    raw = raw.replace(/\/index\.html$/, '/');
    if (raw.indexOf('.') === -1 && raw.charAt(raw.length - 1) !== '/') raw += '/';
    return raw;
  }

  function currentRecord() {
    var map = (typeof window !== 'undefined' && window.TP_VERIFICATION_MAP) || {};
    var p = normalisePath(location.pathname || '/');
    return map[p] || null;
  }

  // ─── source link + citation derivation ─────────────────────────────────
  // the source row deep-links into the navigable source reader at
  // /source/view/, which reads the directory mirror under /source/
  // and renders each page's authored source in a readable shell.
  // we pass the current page path as ?path=<encoded>, exactly as
  // the /en-au/source/ and /fr/source/ index pages do for every
  // page in their list. /source/<slug>/ directly is a 403 (no
  // directory listing) — that was the bug this fixes.
  function sourceHref() {
    return '/source/view/?path=' + encodeURIComponent(normalisePath(location.pathname || '/'));
  }
  // the dedicated /verify/ page is bilingual — route to the edition
  // matching the page the visitor is on. /verify/ (single-tree) is
  // retired in favour of /en-au/verify/ and /fr/verifier/.
  function verifyPageHref() {
    var base = getLang() === 'fr' ? '/fr/verifier/' : '/en-au/verify/';
    return base + '?path=' + encodeURIComponent(normalisePath(location.pathname || '/'));
  }
  // integrityHref() removed in the trust-hierarchy refactor; /integrity/
  // is reachable from /verify/'s related-records panel, not from this
  // modal. retained here as a comment so the omission is intentional.

  // ─── citation fallback (when route is not in the verification map) ─────
  function pageTitle() {
    var raw = document.title || '';
    if (raw.indexOf('|') !== -1) {
      return raw.replace(/^[^|]+\|\s*/, '').trim().replace(/\s*&\s*/g, ' and ');
    }
    return raw.replace(/\s*[—-]\s*Trent Power$/, '').trim();
  }
  function canonicalUrl() {
    var link = document.querySelector('link[rel="canonical"]');
    return link ? link.href : location.href;
  }
  // citation format matches the brief and the A-verify reference:
  // "trent power. {title}. personal site. edition {edition}. {url}".
  // the verification map's `citation` field carries this same string
  // baked at build time; we prefer it. fallback rebuilds it on the
  // client when the record is missing (legacy / non-mapped routes).
  function fallbackCitation() {
    return 'Trent Power. ' + pageTitle() + '. ' +
           tt('cite.site_label', 'Personal Site') + '. ' +
           tt('cite.edition_label', 'Edition') + ' ' + EDITION + '. ' +
           canonicalUrl();
  }

  // citation preview · middle-truncation that keeps the canonical
  // bookends ("trent power · …" and "· edition YYYY-MM-DD") and
  // squeezes the middle title to fit. previously the meta rendered
  // preview shows only the edition so the line fits on one desktop row.
  // the full citation continues to live in data-citation for the
  // clipboard write; only the displayed preview uses this shorter shape.
  function citationPreview() {
    return tt('cite.edition_label', 'Edition') + ' ' + EDITION;
  }

  // ─── dom helpers ───────────────────────────────────────────────────────
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k) && attrs[k] != null) {
        n.setAttribute(k, attrs[k]);
      }
    }
    if (text != null) n.textContent = text;
    return n;
  }

  // svg helper · createElementNS so the shield anchor renders as a real
  // svg subtree (createElement('svg') would emit an HTMLUnknownElement
  // that browsers refuse to paint). attrs only — no text content. used
  // for the verify-modal header anchor; no innerHTML, no trusted-types
  // policy needed.
  var SVG_NS = 'http://www.w3.org/2000/svg';
  function svgEl(tag, attrs) {
    var n = document.createElementNS(SVG_NS, tag);
    if (attrs) for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k) && attrs[k] != null) {
        n.setAttribute(k, attrs[k]);
      }
    }
    return n;
  }

  function safeHref(href) {
    if (!href) return '#';
    if (href.charAt(0) === '/' || /^https?:\/\//.test(href)) return href;
    return '#';
  }

  // ─── build modal dom lazily ────────────────────────────────────────────
  // four rows, top-down:
  //   1 · verify this page  (primary, italic oxblood, deep-links /verify/)
  //   2 · view this page's source  (handoff to /source/view/)
  //   3 · copy citation     (button, inline "copied" feedback)
  //   4 · print this page   (sync gesture, no toast)
  // each row is a real <a> or <button> so it works without JS where
  // possible. no record data inside — that lives at /verify/.
  // the integrity row was retired in the trust-hierarchy refactor:
  // verify is the user-facing destination, integrity stays linked
  // from /verify/'s "related records" panel as a secondary technical
  // archive — promoting both here split the trust layer.
  var modal = null;

  function buildModal() {
    var rec = currentRecord();
    var citation = (rec && rec.citation) || fallbackCitation();

    // scrim wraps the shell. naming `.modal-shell-scrim` to avoid
    // collision with the existing `.modal-overlay` shared infra (the
    // homepage's project modal still uses the legacy shell). a single
    // overlay.js generalisation lets both selectors flow through the
    // same focus-trap + esc + scrim-click lifecycle.
    modal = el('div', {
      'class': 'modal-shell-scrim',
      'id': 'verify-modal-scrim',
      'role': 'presentation',
      'aria-hidden': 'true'
    });

    var shell = el('section', {
      'class': 'shell',
      'id': 'verify-modal',
      'role': 'dialog',
      'aria-modal': 'true',
      'aria-labelledby': 'verify-modal-title'
    });

    var closeX = el('button', {
      type: 'button',
      'class': 'shell-close',
      'id': 'verify-modal-close',
      'data-verify-action': 'close',
      'aria-label': tt('verify_modal.close', 'Close')
    }, '×');
    shell.appendChild(closeX);

    // header pad — anchor + title. one restrained symbolic anchor
    // (hairline outline shield, muted ink) sits above the title as a
    // verification stamp; the title carries the modal's meaning. no
    // kicker, no lede, no foot, no page-name subtitle — the title
    // alone speaks.
    var pad = el('div', { 'class': 'shell-pad' });
    var anchor = el('div', { 'class': 'shell-anchor', 'aria-hidden': 'true' });
    var shield = svgEl('svg', {
      viewBox: '0 0 24 28',
      width: '20',
      height: '22',
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': '1',
      'stroke-linejoin': 'round'
    });
    shield.appendChild(svgEl('path', {
      d: 'M12 1.5 L22 5 L22 14 C22 20 17 25 12 26.5 C7 25 2 20 2 14 L2 5 Z'
    }));
    anchor.appendChild(shield);
    pad.appendChild(anchor);
    pad.appendChild(el('h2', {
      'class': 'shell-title',
      'id': 'verify-modal-title'
    }, tt('verify_modal.title', 'Verify, cite or read the source.')));
    shell.appendChild(pad);

    // nav menu — five full-bleed rows, hairline-separated.
    var nav = el('nav', {
      'class': 'menu',
      'aria-label': tt('verify_modal.menu_label', 'Page verification actions')
    });

    // 1 · primary: verify this page ↗  (hand-off to /verify/ — the
    // user-facing trust destination, anchored at the top of the menu
    // so it owns the visual + keyboard primacy.)
    var rowPage = el('a', {
      'class': 'row primary',
      'href': safeHref(verifyPageHref()),
      'data-verify-row': 'page'
    });
    var pageVerb = el('span', { 'class': 'verb' });
    pageVerb.appendChild(document.createTextNode(
      tt('verify_modal.row.page_verb', 'Verify this page') + ' '));
    pageVerb.appendChild(el('span', { 'class': 'arr', 'aria-hidden': 'true' }, '↗'));
    rowPage.appendChild(pageVerb);
    rowPage.appendChild(el('span', { 'class': 'meta' },
      tt('verify_modal.row.page_meta', 'Publication record · Verification')));
    nav.appendChild(rowPage);

    // 2 · view this page's source ↗
    var rowSource = el('a', {
      'class': 'row',
      'href': safeHref(sourceHref()),
      'data-verify-row': 'source'
    });
    var sourceVerb = el('span', { 'class': 'verb' });
    sourceVerb.appendChild(document.createTextNode(
      tt('verify_modal.row.source_verb', 'View this page’s source') + ' '));
    sourceVerb.appendChild(el('span', { 'class': 'arr', 'aria-hidden': 'true' }, '↗'));
    rowSource.appendChild(sourceVerb);
    // meta · keyboard shortcut on hover-capable devices, a
    // publication-language label on touch. css media query
    // (hover:none),(pointer:coarse) toggles which child renders.
    var sourceMeta = el('span', { 'class': 'meta' });
    sourceMeta.appendChild(el('span', { 'class': 'meta-keyboard' },
      tt('verify_modal.row.source_meta', 'Cmd + U')));
    sourceMeta.appendChild(el('span', { 'class': 'meta-touch' },
      tt('verify_modal.row.source_meta_touch', 'Source mirror · HTML edition')));
    rowSource.appendChild(sourceMeta);
    nav.appendChild(rowSource);

    // 3 · copy citation (button, in-place feedback, no toast)
    var rowCopy = el('button', {
      type: 'button',
      'class': 'row',
      'data-copy': 'citation',
      'data-citation': citation,
      'data-verify-row': 'copy'
    });
    rowCopy.appendChild(el('span', { 'class': 'verb' },
      tt('verify_modal.row.copy_verb', 'Copy citation')));
    // meta carries a middle-truncated preview: "trent power · {title} ·
    // edition YYYY-MM-DD". the full citation continues to live in
    // data-citation for the clipboard write — only the displayed
    // preview is shortened.
    rowCopy.appendChild(el('span', { 'class': 'meta' }, citationPreview()));
    rowCopy.appendChild(el('span', { 'class': 'copied', 'aria-live': 'polite' },
      tt('verify_modal.row.copy_copied', 'Copied to clipboard')));
    nav.appendChild(rowCopy);

    // 4 · print this page (button, sync gesture handler)
    var rowPrint = el('button', {
      type: 'button',
      'class': 'row',
      'data-action': 'print',
      'data-verify-row': 'print'
    });
    rowPrint.appendChild(el('span', { 'class': 'verb' },
      tt('verify_modal.row.print_verb', 'Print this page')));
    var printMeta = el('span', { 'class': 'meta' });
    printMeta.appendChild(el('span', { 'class': 'meta-keyboard' },
      tt('verify_modal.row.print_meta', 'Cmd + P')));
    printMeta.appendChild(el('span', { 'class': 'meta-touch' },
      tt('verify_modal.row.print_meta_touch', 'Print or export PDF')));
    rowPrint.appendChild(printMeta);
    nav.appendChild(rowPrint);

    shell.appendChild(nav);
    modal.appendChild(shell);
    document.body.appendChild(modal);

    // scrim-click closes (the shell stops propagation so inner clicks
    // don't dismiss). the shared overlay infra already does this for
    // `.modal-overlay`, but the new `.modal-shell-scrim` selector may
    // not be wired yet, so guard locally.
    modal.addEventListener('click', function (e) {
      if (e.target === modal) {
        if (window.TP_OVERLAY && window.TP_OVERLAY.close) window.TP_OVERLAY.close();
      }
    });
    shell.addEventListener('click', handleRowClick);
  }

  // ─── clipboard helper ──────────────────────────────────────────────────
  // brief-spec verbatim: try navigator.clipboard.writeText first, fall
  // back to a hidden textarea + document.execCommand('copy') for older
  // safari and any browser where the modern API throws (e.g. an iframe
  // without focus permission). returns a promise<boolean> so the row's
  // click handler can chain the confirmation flash off it.
  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        return navigator.clipboard.writeText(text).then(
          function () { return true; },
          function () { return execCopy(text); }
        );
      } catch (_) { /* fall through to execCommand */ }
    }
    return Promise.resolve(execCopy(text));
  }
  function execCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly', '');
    // phase 96 · class, not inline style (csp style-src-attr 'none').
    ta.className = 'tp-copy-fallback';
    document.body.appendChild(ta); ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }

  // ─── row delegated handler ─────────────────────────────────────────────
  // close × → close.  data-copy="citation" → clipboard + flash + event.
  // data-action="print" → window.print() (sync inside gesture), close,
  // event. other rows are plain <a> — the browser navigates.
  function handleRowClick(e) {
    var closeBtn = e.target && e.target.closest
      ? e.target.closest('[data-verify-action="close"]')
      : null;
    if (closeBtn) {
      if (window.TP_OVERLAY && window.TP_OVERLAY.close) window.TP_OVERLAY.close();
      return;
    }

    var copyRow = e.target && e.target.closest
      ? e.target.closest('[data-copy="citation"]')
      : null;
    if (copyRow) {
      var text = copyRow.getAttribute('data-citation') || '';
      copyToClipboard(text).then(function (ok) {
        if (!ok) return;
        copyRow.setAttribute('data-copied', 'true');
        copyRow.classList.add('is-copied');
        window.setTimeout(function () {
          copyRow.removeAttribute('data-copied');
          copyRow.classList.remove('is-copied');
        }, 1800);
        document.dispatchEvent(new CustomEvent('verify:copied', {
          detail: { kind: 'citation', text: text }
        }));
      });
      return;
    }

    var printRow = e.target && e.target.closest
      ? e.target.closest('[data-action="print"]')
      : null;
    if (printRow) {
      // ios safari requires window.print() synchronously inside the
      // gesture handler — settimeout breaks the gesture context. the
      // print stylesheet hides the modal across every data-page, so
      // calling print() with the modal still mounted is safe; the
      // close runs after to tidy on-screen state and event order so
      // the system print sheet isn't visually behind the scrim.
      document.dispatchEvent(new CustomEvent('verify:print'));
      window.print();
      if (window.TP_OVERLAY && window.TP_OVERLAY.close) window.TP_OVERLAY.close();
      return;
    }
  }

  // ─── wire the verify trigger ───────────────────────────────────────────
  // single trigger contract: anything carrying `[data-cite-open]` opens
  // the verify modal. attribute name stays for compatibility with the
  // 15 footer templates already in place — internal-only, no churn.
  // history-integrated open pushes #verify onto the url so the browser
  // back button closes the modal naturally and direct links auto-open
  // it. if the overlay infra (window.TP_OVERLAY) is missing for any
  // reason, the handler falls back to navigating to /verify/ so the
  // user is never stranded.
  function openModal(e, opener) {
    if (!opener && e && e.currentTarget) opener = e.currentTarget;
    if (!window.TP_OVERLAY || !window.TP_OVERLAY.open) {
      if (e && typeof e.preventDefault === 'function') e.preventDefault();
      try { console.warn('verify modal unavailable, falling back to /verify/'); }
      catch (_) {}
      window.location.href = verifyPageHref();
      return;
    }
    if (e && typeof e.preventDefault === 'function') e.preventDefault();
    if (!modal) buildModal();
    window.TP_OVERLAY.open(modal, opener || null, { hash: '#verify' });
  }

  function init() {
    var triggers = document.querySelectorAll('[data-cite-open]');
    if (!triggers.length) return;
    Array.prototype.forEach.call(triggers, function (trigger) {
      trigger.addEventListener('click', function (e) { openModal(e, trigger); });
    });

    // deep-link · if the page is loaded with #verify (or legacy #cite)
    // in the url (shared link, bookmark, browser-history navigation),
    // auto-open the modal after the trigger is wired. one-cycle bridge
    // for #cite: old bookmarks keep working for this edition; the next
    // release can drop the legacy hash.
    var hash = window.location.hash;
    if (hash === '#verify' || hash === '#cite') {
      // defer to the next tick so any other domcontentloaded handlers
      // finish first (notably the smooth-scroll and language-switcher
      // handlers in app.js).
      setTimeout(function () { openModal(null, triggers[0]); }, 0);
    }

    // popstate forward navigation: if we're back at #verify without an
    // active modal, open. mirrors the back-button case so forward
    // re-opens cleanly. tagged with frompopstate so the open doesn't
    // push another history entry.
    window.addEventListener('popstate', function () {
      var st = history.state;
      var h = window.location.hash;
      if ((h === '#verify' || h === '#cite') &&
          st && (st.tp_overlay === 'verify' || st.tp_overlay === 'cite') &&
          !document.querySelector('.modal-shell-scrim.active, .modal-overlay.active')) {
        if (!modal) buildModal();
        if (window.TP_OVERLAY && window.TP_OVERLAY.open) {
          window.TP_OVERLAY.open(modal, triggers[0], { hash: '#verify', fromPopstate: true });
        }
      }
    });
  }

  // defer init off the critical render path. the verify-button click
  // happens long after first paint, so building the modal shell at
  // domcontentloaded was wasted main-thread time (~50 ms long task on
  // mobile). requestidlecallback runs after the browser is idle;
  // settimeout 500 ms is the fallback for engines without it.
  function _scheduleInit() {
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(init, { timeout: 1500 });
    } else {
      window.setTimeout(init, 500);
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _scheduleInit);
  } else {
    _scheduleInit();
  }

  // the fingerprint + verify-command copy buttons (.copy-fingerprint,
  // .verify-command-copy) carry data-copy-* attributes and are handled
  // by the shared /copy.js delegated listener — no wiring needed here.

})();
