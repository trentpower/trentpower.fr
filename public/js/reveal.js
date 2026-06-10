/*! trentpower.fr · /js/reveal.js · generated · signed via /integrity.json */
(function () {
'use strict';
var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function _reveal() {
var revealGroups = ['.principle', '.trajectory-item', '.project-card'];
var allRevealEls = document.querySelectorAll(revealGroups.join(', '));
if (!prefersReducedMotion && 'IntersectionObserver' in window) {
var observer = new IntersectionObserver(function (entries) {
entries.forEach(function (entry) {
if (entry.isIntersecting) {
entry.target.classList.add('visible');
observer.unobserve(entry.target);
}
});
}, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
revealGroups.forEach(function (sel) {
document.querySelectorAll(sel).forEach(function (el, i) {
el.setAttribute('data-reveal-index', Math.min(i, 15));
observer.observe(el);
});
});
} else {
allRevealEls.forEach(function (el) {
el.classList.add('visible');
});
}
}
function whenFontsReady(fn) {
var root = document.documentElement;
if (root.classList.contains('fonts-ready')) { fn(); return; }
var done = false;
var fire = function () { if (done) return; done = true; fn(); };
if (document.fonts && document.fonts.ready && typeof document.fonts.ready.then === 'function') {
document.fonts.ready.then(fire, fire);
}
setTimeout(fire, 1500);
}
function _schedule() {
if ('requestIdleCallback' in window) {
requestIdleCallback(_reveal, { timeout: 2000 });
} else {
setTimeout(_reveal, 200);
}
}
if (prefersReducedMotion) {
_schedule();
} else {
whenFontsReady(_schedule);
}
})();
