/*
  trentpower.fr
  theme + enhancement flags

  Role:
  the footer light / system / dark theme toggle, plus the html.js
  and html.enhanced flag classes the css reveal cascade is gated on.

  the inline <head> bootstrap already stamps html.js and the stored
  data-theme before first paint; this file adds the runtime toggle
  and re-asserts the flags defensively if that inline script was
  blocked.

  Source:
  edited here as theme.template.js; compiled to theme.js by
  generate_site.py (minified, no substitution).

  Constraints:
  - no fetch, no inline handlers, no third-party scripts
  - enhancement only: with this absent the page keeps the OS theme
    via prefers-color-scheme and renders every section at rest
*/

(function () {
  'use strict';

  // belt-and-braces · ensure html.js is set even if the inline
  // bootstrap was blocked (csp, parse error, anything else).
  try { document.documentElement.classList.add('js'); } catch (_) {}

  // once the dom is ready, mark <html> as enhanced so css can run the
  // hero reveal cascade (gated by `html.enhanced .hero-*`). no-JS
  // users never get the class and see the resting hero immediately.
  function _markEnhanced() {
    try { document.documentElement.classList.add('enhanced'); } catch (_) {}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _markEnhanced, { once: true });
  } else {
    _markEnhanced();
  }

  // theme toggle · localStorage key tp-theme · values light/system/dark.
  // dom contract: data-theme on <html>; "system" removes the attribute.
  var root = document.documentElement;

  function applyTheme(value) {
    if (value === 'light' || value === 'dark') {
      root.setAttribute('data-theme', value);
    } else {
      root.removeAttribute('data-theme');
    }
    try { localStorage.setItem('tp-theme', value); } catch (_) {}
    document.querySelectorAll('.site-footer__theme button[data-theme]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-theme') === value ? 'true' : 'false');
    });
  }

  function bootTheme() {
    var stored;
    try { stored = localStorage.getItem('tp-theme'); } catch (_) { stored = null; }
    var value = (stored === 'light' || stored === 'dark') ? stored : 'system';
    document.querySelectorAll('.site-footer__theme button[data-theme]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.getAttribute('data-theme') === value ? 'true' : 'false');
    });
  }
  bootTheme();

  document.addEventListener('click', function (event) {
    if (!event.target || !event.target.closest) return;
    var btn = event.target.closest('.site-footer__theme button[data-theme]');
    if (!btn) return;
    event.preventDefault();
    applyTheme(btn.getAttribute('data-theme'));
  });

})();
