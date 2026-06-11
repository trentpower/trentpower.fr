/*! trentpower.fr · /js/edition.js · generated · loaded after first paint · signed via /integrity.json */
(function () {
'use strict';
var AGE_COPY = {
en: {
today: 'Published today',
yesterday: 'Published yesterday',
days: function (n) { return 'Published ' + n + ' days ago'; },
weeks: function (n) { return 'Published ' + n + ' week' + (n === 1 ? '' : 's') + ' ago'; },
months: function (n) { return 'Published ' + n + ' month' + (n === 1 ? '' : 's') + ' ago'; },
years: function (n) { return 'Published ' + n + ' year' + (n === 1 ? '' : 's') + ' ago'; }
},
fr: {
today: 'Publiée aujourd’hui',
yesterday: 'Publiée hier',
days: function (n) { return 'Publiée il y a ' + n + ' jours'; },
weeks: function (n) { return 'Publiée il y a ' + n + ' semaine' + (n === 1 ? '' : 's'); },
months: function (n) { return 'Publiée il y a ' + n + ' mois'; },
years: function (n) { return 'Publiée il y a ' + n + (n === 1 ? ' an' : ' ans'); }
}
};
function lang() {
var d = (document.documentElement.lang || 'en').toLowerCase();
return d.indexOf('fr') === 0 ? 'fr' : 'en';
}
function parseLocalDate(value) {
var p = String(value || '').split('-');
if (p.length !== 3) return null;
var y = Number(p[0]);
var m = Number(p[1]);
var d = Number(p[2]);
if (!y || !m || !d) return null;
return new Date(y, m - 1, d);
}
function diffDays(from, to) {
var a = new Date(from.getFullYear(), from.getMonth(), from.getDate());
var b = new Date(to.getFullYear(), to.getMonth(), to.getDate());
return Math.max(0, Math.floor((b - a) / 86400000));
}
function compute(ed) {
var date = parseLocalDate(ed);
if (!date) return null;
var days = diffDays(date, new Date());
var copy = AGE_COPY[lang()];
if (days === 0) return copy.today;
if (days === 1) return copy.yesterday;
if (days < 7) return copy.days(days);
if (days < 31) return copy.weeks(Math.max(1, Math.floor(days / 7)));
if (days < 365) return copy.months(Math.max(1, Math.floor(days / 30.4375)));
return copy.years(Math.max(1, Math.floor(days / 365.25)));
}
function run() {
var ed = document.body && document.body.getAttribute('data-edition');
if (!ed) return;
var text = compute(ed);
if (!text) return;
var nodes = document.querySelectorAll('[data-edition-age]');
for (var i = 0; i < nodes.length; i++) {
nodes[i].textContent = text;
}
}
var DISCLOSURE_KEY = 'tp-fr-disclosure-seen';
function reconcileDisclosure() {
var disc = document.querySelector('[data-translation-disclosure]');
if (!disc) return;
var age = null;
var parent = disc.parentNode;
if (parent) age = parent.querySelector('[data-edition-age]');
var seen = null;
try { seen = localStorage.getItem(DISCLOSURE_KEY); } catch (_) {}
if (seen) {
disc.hidden = true;
if (age) age.hidden = false;
} else {
try {
var today = new Date().toISOString().slice(0, 10);
localStorage.setItem(DISCLOSURE_KEY, today);
} catch (_) {}
}
}
function boot() {
reconcileDisclosure();
run();
}
if (document.readyState === 'loading') {
document.addEventListener('DOMContentLoaded', boot);
} else {
boot();
}
document.addEventListener('tp:edition-swapped', boot);
})();
(function () {
'use strict';
var STORAGE_KEY = 'tp-last-edition';
function editionFromHref(href) {
try {
var u = new URL(href, window.location.origin);
if (u.origin !== window.location.origin) return null;
var p = u.pathname;
if (p.indexOf('/en-au/') === 0) return 'en-au';
if (p.indexOf('/fr/') === 0) return 'fr';
return null;
} catch (_) { return null; }
}
function currentEdition() {
var p = window.location.pathname;
if (p.indexOf('/en-au/') === 0) return 'en-au';
if (p.indexOf('/fr/') === 0) return 'fr';
return null;
}
function reducedMotion() {
return !!(window.matchMedia &&
window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}
function applySwap(doc, url, target) {
var newMain = doc.querySelector('main');
var newFooter = doc.querySelector('footer');
if (!newMain) throw new Error('no <main> in fetched edition');
var oldMain = document.querySelector('main');
var oldFooter = document.querySelector('footer');
if (oldMain) oldMain.replaceWith(newMain);
if (oldFooter && newFooter) oldFooter.replaceWith(newFooter);
var newTitle = doc.querySelector('title');
if (newTitle) document.title = newTitle.textContent;
var newLang = doc.documentElement.getAttribute('lang');
if (newLang) document.documentElement.setAttribute('lang', newLang);
var oldCan = document.querySelector('link[rel="canonical"]');
var newCan = doc.querySelector('link[rel="canonical"]');
if (oldCan && newCan) oldCan.setAttribute('href', newCan.getAttribute('href'));
var oldAlts = document.querySelectorAll('link[rel="alternate"][hreflang]');
for (var i = oldAlts.length - 1; i >= 0; i--) {
oldAlts[i].parentNode.removeChild(oldAlts[i]);
}
var newAlts = doc.querySelectorAll('link[rel="alternate"][hreflang]');
var anchor = oldCan || document.head.lastChild;
for (var j = 0; j < newAlts.length; j++) {
var clone = newAlts[j].cloneNode(true);
anchor.parentNode.insertBefore(clone, anchor.nextSibling);
anchor = clone;
}
var oldLd = document.querySelectorAll('script[type="application/ld+json"]');
var newLd = doc.querySelectorAll('script[type="application/ld+json"]');
if (oldLd.length === newLd.length) {
for (var k = 0; k < oldLd.length; k++) {
oldLd[k].textContent = newLd[k].textContent;
}
}
var nb = doc.body;
if (nb) {
document.body.className = nb.className;
var attrs = nb.attributes;
for (var a = 0; a < attrs.length; a++) {
var nm = attrs[a].name;
if (nm.indexOf('data-') === 0) {
document.body.setAttribute(nm, attrs[a].value);
}
}
}
if (window.location.pathname !== url) {
history.pushState({ edition: target }, '', url);
}
document.documentElement.classList.add('hero-static');
try {
document.dispatchEvent(new CustomEvent('tp:edition-swapped', {
detail: { edition: target, url: url }
}));
} catch (_) {}
}
function swapTo(href, target) {
return fetch(href, { credentials: 'same-origin' })
.then(function (r) {
if (!r.ok) throw new Error('HTTP ' + r.status);
return r.text();
})
.then(function (text) {
var doc = new DOMParser().parseFromString(text, 'text/html');
var url = new URL(href, window.location.origin).pathname;
var run = function () { applySwap(doc, url, target); };
if (typeof document.startViewTransition === 'function' &&
!reducedMotion()) {
document.startViewTransition(run);
} else {
run();
}
});
}
function onClick(event) {
var link = event.currentTarget;
var href = link.getAttribute('href');
var target = editionFromHref(href);
if (!target) return;
if (target === currentEdition()) return;
event.preventDefault();
try { localStorage.setItem(STORAGE_KEY, target); } catch (_) {}
swapTo(href, target).catch(function () {
window.location.assign(href);
});
}
function wire() {
var links = document.querySelectorAll(
'.site-footer__language a[href]'
);
for (var i = 0; i < links.length; i++) {
var href = links[i].getAttribute('href');
if (editionFromHref(href)) {
links[i].addEventListener('click', onClick);
}
}
}
if (document.readyState === 'loading') {
document.addEventListener('DOMContentLoaded', wire);
} else {
wire();
}
document.addEventListener('tp:edition-swapped', wire);
})();
