/*! trentpower.fr · /js/overlay.js · generated · loaded after first paint · signed via /integrity.json */
(function () {
'use strict';
var siteContent = document.getElementById('main');
var supportsInert = 'inert' in document.documentElement;
function setInert(el, state) {
if (!el) return;
if (state) {
if (supportsInert) el.setAttribute('inert', '');
el.setAttribute('aria-hidden', 'true');
} else {
if (supportsInert) el.removeAttribute('inert');
el.removeAttribute('aria-hidden');
}
}
function focusableIn(el) {
return el.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])');
}
var activeOverlay = null;
var activeTrigger = null;
var pushedHistoryState = false;
function openOverlay(overlay, trigger, opts) {
if (!overlay) return;
activeOverlay = overlay;
activeTrigger = trigger || null;
overlay.setAttribute('aria-hidden', 'false');
if (supportsInert) overlay.removeAttribute('inert');
overlay.classList.add('active');
overlay.classList.add('is-active');
document.body.classList.add('modal-open');
setInert(siteContent, true);
if (trigger) trigger.setAttribute('aria-expanded', 'true');
var focusable = focusableIn(overlay);
if (focusable.length > 0) focusable[0].focus();
pushedHistoryState = false;
if (opts && opts.hash && !opts.fromPopstate &&
typeof history !== 'undefined' && typeof history.pushState === 'function') {
try {
history.pushState({ tp_overlay: opts.hash.replace(/^#/, '') }, '', opts.hash);
pushedHistoryState = true;
} catch (_) { }
}
}
function closeOverlay(opts) {
if (!activeOverlay) return;
var overlay = activeOverlay;
var trigger = activeTrigger;
overlay.classList.remove('active');
overlay.classList.remove('is-active');
overlay.setAttribute('aria-hidden', 'true');
if (supportsInert) overlay.setAttribute('inert', '');
document.body.classList.remove('modal-open');
setInert(siteContent, false);
if (trigger) {
trigger.setAttribute('aria-expanded', 'false');
trigger.focus();
}
activeOverlay = null;
activeTrigger = null;
if (pushedHistoryState && !(opts && opts.fromPopstate) &&
typeof history !== 'undefined' && typeof history.back === 'function') {
try { history.back(); } catch (_) { }
}
pushedHistoryState = false;
}
window.addEventListener('popstate', function () {
if (activeOverlay) {
var st = history.state;
var stillOpen = st && st.tp_overlay;
if (!stillOpen) closeOverlay({ fromPopstate: true });
}
});
document.addEventListener('keydown', function (e) {
if (!activeOverlay) return;
if (e.key === 'Escape') { closeOverlay(); return; }
if (e.key === 'Tab') {
var focusable = focusableIn(activeOverlay);
if (focusable.length === 0) return;
var first = focusable[0];
var last = focusable[focusable.length - 1];
if (e.shiftKey) {
if (document.activeElement === first) { e.preventDefault(); last.focus(); }
} else {
if (document.activeElement === last) { e.preventDefault(); first.focus(); }
}
}
});
window.TP_OVERLAY = { open: openOverlay, close: closeOverlay };
var modal = document.getElementById('modal');
var btn = document.getElementById('access-btn');
var closeBtn = document.getElementById('modal-close');
if (modal && btn && closeBtn) {
btn.addEventListener('click', function () { openOverlay(modal, btn); });
closeBtn.addEventListener('click', closeOverlay);
modal.addEventListener('click', function (e) {
if (e.target === modal) closeOverlay();
});
}
if (supportsInert) {
var inertNodes = document.querySelectorAll('[data-inert-default]');
for (var i = 0; i < inertNodes.length; i++) {
inertNodes[i].inert = true;
}
}
})();
