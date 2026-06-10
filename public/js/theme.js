/*! trentpower.fr · /js/theme.js · generated · signed via /integrity.json */
(function () {
'use strict';
try { document.documentElement.classList.add('js'); } catch (_) {}
function _markEnhanced() {
try { document.documentElement.classList.add('enhanced'); } catch (_) {}
}
if (document.readyState === 'loading') {
document.addEventListener('DOMContentLoaded', _markEnhanced, { once: true });
} else {
_markEnhanced();
}
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
