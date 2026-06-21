/*! trentpower.fr · /js/verify-modal.js · generated · signed via /integrity.json */
(function () {
'use strict';
var EDITION = '2026-06-21';
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
function sourceHref() {
return '/source/view/?path=' + encodeURIComponent(normalisePath(location.pathname || '/'));
}
function verifyPageHref() {
var base = getLang() === 'fr' ? '/fr/verifier/' : '/en-au/verify/';
return base + '?path=' + encodeURIComponent(normalisePath(location.pathname || '/'));
}
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
function fallbackCitation() {
return 'Trent Power. ' + pageTitle() + '. ' +
tt('cite.site_label', 'Personal Site') + '. ' +
tt('cite.edition_label', 'Edition') + ' ' + EDITION + '. ' +
canonicalUrl();
}
function citationPreview() {
return tt('cite.edition_label', 'Edition') + ' ' + EDITION;
}
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
var modal = null;
function buildModal() {
var rec = currentRecord();
var citation = (rec && rec.citation) || fallbackCitation();
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
var nav = el('nav', {
'class': 'menu',
'aria-label': tt('verify_modal.menu_label', 'Page verification actions')
});
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
var sourceMeta = el('span', { 'class': 'meta' });
sourceMeta.appendChild(el('span', { 'class': 'meta-keyboard' },
tt('verify_modal.row.source_meta', 'Cmd + U')));
sourceMeta.appendChild(el('span', { 'class': 'meta-touch' },
tt('verify_modal.row.source_meta_touch', 'Source mirror · HTML edition')));
rowSource.appendChild(sourceMeta);
nav.appendChild(rowSource);
var rowCopy = el('button', {
type: 'button',
'class': 'row',
'data-copy': 'citation',
'data-citation': citation,
'data-verify-row': 'copy'
});
rowCopy.appendChild(el('span', { 'class': 'verb' },
tt('verify_modal.row.copy_verb', 'Copy citation')));
rowCopy.appendChild(el('span', { 'class': 'meta' }, citationPreview()));
rowCopy.appendChild(el('span', { 'class': 'copied', 'aria-live': 'polite' },
tt('verify_modal.row.copy_copied', 'Copied to clipboard')));
nav.appendChild(rowCopy);
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
modal.addEventListener('click', function (e) {
if (e.target === modal) {
if (window.TP_OVERLAY && window.TP_OVERLAY.close) window.TP_OVERLAY.close();
}
});
shell.addEventListener('click', handleRowClick);
}
function copyToClipboard(text) {
if (navigator.clipboard && navigator.clipboard.writeText) {
try {
return navigator.clipboard.writeText(text).then(
function () { return true; },
function () { return execCopy(text); }
);
} catch (_) { }
}
return Promise.resolve(execCopy(text));
}
function execCopy(text) {
var ta = document.createElement('textarea');
ta.value = text; ta.setAttribute('readonly', '');
ta.className = 'tp-copy-fallback';
document.body.appendChild(ta); ta.select();
var ok;
try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
document.body.removeChild(ta);
return ok;
}
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
document.dispatchEvent(new CustomEvent('verify:print'));
window.print();
if (window.TP_OVERLAY && window.TP_OVERLAY.close) window.TP_OVERLAY.close();
return;
}
}
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
var hash = window.location.hash;
if (hash === '#verify' || hash === '#cite') {
setTimeout(function () { openModal(null, triggers[0]); }, 0);
}
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
})();
