/*! trentpower.fr · /js/micro-interactions.js · generated · loaded after first paint · signed via /integrity.json */
(function () {
'use strict';
var REDUCED = window.matchMedia &&
window.matchMedia('(prefers-reduced-motion: reduce)').matches;
var bfcacheRestored = false;
window.addEventListener('pageshow', function (ev) {
if (ev.persisted) bfcacheRestored = true;
});
var io = null;
function getObserver() {
if (io) return io;
if (typeof IntersectionObserver !== 'function') return null;
io = new IntersectionObserver(function (entries) {
entries.forEach(function (entry) {
if (!entry.isIntersecting) return;
var el = entry.target;
if (el.classList.contains('tp-rule')) {
el.classList.add('is-settled');
} else if (el.classList.contains('section-label')) {
el.classList.add('is-revealed');
} else if (el.classList.contains('tp-tick')) {
tickNumber(el);
}
io.unobserve(el);
});
}, { threshold: 0.4 });
return io;
}
function tickNumber(el) {
var raw = el.getAttribute('value');
var target = parseFloat(raw);
if (isNaN(target)) return;
var text = el.textContent;
var suffix = text.replace(/^[\d.,\s]+/, '');
var dotMatch = text.match(/\.(\d+)/);
var decimals = dotMatch ? dotMatch[1].length : 0;
var finalText = target.toFixed(decimals) + suffix;
if (REDUCED) {
el.textContent = finalText;
return;
}
var duration = 600;
var start = performance.now();
function frame(now) {
var t = Math.min(1, (now - start) / duration);
var eased = 1 - Math.pow(1 - t, 3);
el.textContent = (target * eased).toFixed(decimals) + suffix;
if (t < 1) requestAnimationFrame(frame);
else el.textContent = finalText;
}
el.textContent = (0).toFixed(decimals) + suffix;
requestAnimationFrame(frame);
}
function setupReadingProgress() {
if (REDUCED) return;
if (document.documentElement.scrollHeight <= window.innerHeight * 2) return;
var bar = document.createElement('div');
bar.className = 'tp-progress';
bar.setAttribute('aria-hidden', 'true');
document.body.insertBefore(bar, document.body.firstChild);
var firstViewport = window.innerHeight;
function update() {
if (window.scrollY > firstViewport) bar.classList.add('is-visible');
else bar.classList.remove('is-visible');
}
window.addEventListener('scroll', update, { passive: true });
window.addEventListener('resize', function () {
firstViewport = window.innerHeight;
update();
}, { passive: true });
update();
}
function setupFooterTypewriter() {
if (REDUCED) return;
var key = 'tp-typed-' + location.pathname;
try { if (sessionStorage.getItem(key)) return; } catch (_) {}
try { sessionStorage.setItem(key, '1'); } catch (_) {}
var el = document.querySelector('[data-edition-age]');
if (!el) return;
setTimeout(function () {
var text = el.textContent;
if (!text) return;
var duration = 800;
var charDelay = Math.max(20, Math.floor(duration / text.length));
el.textContent = '';
var i = 0;
function tick() {
if (i > text.length) return;
el.textContent = text.slice(0, i);
i++;
if (i <= text.length) setTimeout(tick, charDelay);
}
tick();
}, 1500);
}
function setupCitationFlash() {
document.addEventListener('tp:citation-copied', function () {
if (REDUCED) return;
var cite = document.querySelector('.tp-citation');
if (!cite) return;
cite.classList.add('is-acknowledging');
setTimeout(function () {
cite.classList.remove('is-acknowledging');
}, 200);
});
}
function init() {
if (bfcacheRestored) {
setupCitationFlash();
return;
}
if (REDUCED) {
document.querySelectorAll('.tp-rule')
.forEach(function (el) { el.classList.add('is-settled'); });
document.querySelectorAll('.section-label')
.forEach(function (el) { el.classList.add('is-revealed'); });
setupCitationFlash();
return;
}
var observer = getObserver();
if (observer) {
document.querySelectorAll('.tp-rule, .section-label, .tp-tick')
.forEach(function (el) { observer.observe(el); });
} else {
document.querySelectorAll('.tp-rule')
.forEach(function (el) { el.classList.add('is-settled'); });
document.querySelectorAll('.section-label')
.forEach(function (el) { el.classList.add('is-revealed'); });
}
setupReadingProgress();
setupFooterTypewriter();
setupCitationFlash();
}
if (document.readyState === 'loading') {
document.addEventListener('DOMContentLoaded', init);
} else {
init();
}
})();
