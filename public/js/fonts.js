/*! trentpower.fr · /js/fonts.js · generated · loaded after first paint · signed via /integrity.json */
(function () {
'use strict';
(function readyFlag() {
var root = document.documentElement;
var done = false;
function mark() {
if (done) return;
done = true;
try { root.classList.add('fonts-ready'); } catch (_) {}
}
try {
if (document.fonts && document.fonts.ready && typeof document.fonts.ready.then === 'function') {
document.fonts.ready.then(mark, mark);
setTimeout(mark, 1200);
} else {
mark();
}
} catch (_) {
mark();
}
})();
if (document.querySelector('link[data-tp-fonts-full]')) return;
var link = document.createElement('link');
link.rel = 'stylesheet';
link.href = '/fonts-full.css?v=2026-06-24.3aabdf6d';
link.setAttribute('data-tp-fonts-full', '');
function paintFlip() {
if (typeof requestAnimationFrame === 'function') {
requestAnimationFrame(function () {
document.documentElement.classList.add('fonts-loaded');
});
} else {
document.documentElement.classList.add('fonts-loaded');
}
}
link.addEventListener('load', function () {
if (document.fonts && document.fonts.ready && typeof document.fonts.ready.then === 'function') {
document.fonts.ready.then(paintFlip);
} else {
setTimeout(paintFlip, 1500);
}
});
document.head.appendChild(link);
})();
