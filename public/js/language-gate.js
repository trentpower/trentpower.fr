/*! trentpower.fr · /js/language-gate.js · generated · signed via /integrity.json */
(function () {
"use strict";
var STORAGE_KEY = "tp-last-edition";
var SKIP_ANIM_KEY = "tp-skip-hero-anim";
var GATE_RESTORED = "gateRestored";
var ROUTES = { "en-au": "/en-au/", "fr": "/fr/" };
var DEFAULT_EDITION = "en-au";
var html = document.documentElement;
var overlay = document.getElementById("lang-gate");
var scrim = document.getElementById("lang-gate-scrim");
if (!overlay || !scrim) return;
(function () {
var w = (typeof window !== "undefined") ? window.__tpWelcome : null;
if (!w) return;
var slots = overlay.querySelectorAll("[data-tp-last-read]");
for (var i = 0; i < slots.length; i++) {
var slot = slots[i];
var wrap = slot.closest("[data-gate]");
var lang = wrap && wrap.getAttribute("data-gate");
slot.textContent = (lang === "fr") ? w.fr : w.en;
}
})();
function readEdition() {
try {
var v = localStorage.getItem(STORAGE_KEY);
return (v === "en-au" || v === "fr") ? v : null;
} catch (_) { return null; }
}
function writeEdition(v) {
try {
localStorage.setItem(STORAGE_KEY, v);
var today = new Date().toISOString().slice(0, 10);
localStorage.setItem("tp-last-read:/" + v + "/", today);
} catch (_) {}
}
function markSkipHeroAnim() {
try { sessionStorage.setItem(SKIP_ANIM_KEY, "1"); } catch (_) {}
}
function dismissTarget() {
var s = readEdition();
if (s) return s;
return html.dataset.preferredLang === "fr" ? "fr" : DEFAULT_EDITION;
}
function reducedMotion() {
return !!(window.matchMedia &&
window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}
function swapToEdition(target) {
var url = ROUTES[target];
return fetch(url, { credentials: "same-origin" })
.then(function (r) {
if (!r.ok) throw new Error("HTTP " + r.status);
return r.text();
})
.then(function (text) {
var doc = new DOMParser().parseFromString(text, "text/html");
var newMain = doc.querySelector("main");
if (!newMain) throw new Error("no <main> in fetched edition");
var run = function () { applySwap(doc, newMain, target, url); };
if (typeof document.startViewTransition === "function" &&
!reducedMotion()) {
document.startViewTransition(run);
} else {
run();
}
});
}
function applySwap(doc, newMain, target, url) {
var oldMain = document.querySelector("main");
if (oldMain) {
oldMain.replaceWith(newMain);
} else {
var bg = document.querySelector(".gate-background");
if (bg) bg.remove();
var scrimEl = document.getElementById("lang-gate-scrim");
if (scrimEl && scrimEl.parentNode) {
scrimEl.parentNode.insertBefore(newMain, scrimEl);
} else {
document.body.appendChild(newMain);
}
}
var newFooter = doc.querySelector("footer");
var oldFooter = document.querySelector("footer");
if (newFooter) {
if (oldFooter) {
oldFooter.replaceWith(newFooter);
} else {
var scrimEl2 = document.getElementById("lang-gate-scrim");
if (scrimEl2 && scrimEl2.parentNode) {
scrimEl2.parentNode.insertBefore(newFooter, scrimEl2);
} else {
document.body.appendChild(newFooter);
}
}
}
var newTitle = doc.querySelector("title");
if (newTitle) document.title = newTitle.textContent;
var newHtmlLang = doc.documentElement.getAttribute("lang");
if (newHtmlLang) html.setAttribute("lang", newHtmlLang);
var newCanonical = doc.querySelector('link[rel="canonical"]');
var oldCanonical = document.querySelector('link[rel="canonical"]');
if (newCanonical && oldCanonical) {
oldCanonical.setAttribute("href", newCanonical.getAttribute("href"));
}
var oldAlts = document.querySelectorAll('link[rel="alternate"][hreflang]');
for (var i = oldAlts.length - 1; i >= 0; i--) {
oldAlts[i].parentNode.removeChild(oldAlts[i]);
}
var newAlts = doc.querySelectorAll('link[rel="alternate"][hreflang]');
var anchor = oldCanonical || document.head.lastChild;
for (var j = 0; j < newAlts.length; j++) {
var clone = newAlts[j].cloneNode(true);
anchor.parentNode.insertBefore(clone, anchor.nextSibling);
anchor = clone;
}
var oldJsonLd = document.querySelectorAll('script[type="application/ld+json"]');
var newJsonLd = doc.querySelectorAll('script[type="application/ld+json"]');
if (oldJsonLd.length === newJsonLd.length) {
for (var k = 0; k < oldJsonLd.length; k++) {
oldJsonLd[k].textContent = newJsonLd[k].textContent;
}
}
var newBody = doc.body;
if (newBody) {
document.body.className = newBody.className;
var attrs = newBody.attributes;
for (var a = 0; a < attrs.length; a++) {
var nm = attrs[a].name;
if (nm.indexOf("data-") === 0) {
document.body.setAttribute(nm, attrs[a].value);
}
}
}
if (location.pathname !== url) {
history.pushState({ edition: target }, "", url);
}
html.classList.add("hero-static");
try {
document.dispatchEvent(new CustomEvent("tp:edition-swapped", {
detail: { edition: target, url: url }
}));
} catch (_) {}
}
function dismissToEdition(target, source) {
var animate = !reducedMotion();
var restored = html.dataset[GATE_RESTORED] === "true";
var holdMs = (source === "choice" && animate && !restored) ? 80 : 0;
function startSwap() {
markSkipHeroAnim();
document.body.dataset.gateDismissed = "true";
if (animate) {
scrim.setAttribute("data-gate-exiting", "");
} else {
scrim.hidden = true;
}
swapToEdition(target).then(function () {
if (animate) {
scrim.hidden = true;
}
var bg = document.querySelector(".gate-background");
if (bg) bg.remove();
}).catch(function () {
window.location.assign(ROUTES[target]);
});
}
var chosen = source === "choice"
? overlay.querySelector('.lang-cell[data-lang-choice="' +
(target === "fr" ? "fr" : "en") + '"]')
: null;
if (chosen && holdMs) chosen.setAttribute("data-tap-ack", "");
if (holdMs) {
window.setTimeout(startSwap, holdMs);
} else {
startSwap();
}
}
function restoreGate() {
scrim.removeAttribute("data-gate-exiting");
scrim.hidden = false;
scrim.classList.add("is-active");
delete document.body.dataset.gateDismissed;
html.dataset[GATE_RESTORED] = "true";
}
window.addEventListener("popstate", function (_ev) {
if (location.pathname === "/") restoreGate();
});
window.addEventListener("pageshow", function (ev) {
if (!ev.persisted) return;
if (location.pathname === "/") restoreGate();
});
var closeBtn = document.getElementById("lang-close");
if (closeBtn) {
closeBtn.addEventListener("click", function () {
dismissToEdition(dismissTarget(), "dismiss");
});
}
document.addEventListener("keydown", function (event) {
if (event.key === "Escape" || event.key === "Esc") {
if (scrim.classList.contains("is-active") &&
!scrim.hasAttribute("data-gate-exiting")) {
dismissToEdition(dismissTarget(), "dismiss");
}
}
});
scrim.addEventListener("click", function (event) {
if (event.target === scrim) {
dismissToEdition(dismissTarget(), "dismiss");
}
});
var choices = overlay.querySelectorAll("a[data-lang-choice]");
Array.prototype.forEach.call(choices, function (link) {
link.addEventListener("click", function (event) {
var lang = link.getAttribute("data-lang-choice");
var target = lang === "fr" ? "fr" : DEFAULT_EDITION;
writeEdition(target);
event.preventDefault();
dismissToEdition(target, "choice");
});
});
var focusable = overlay.querySelectorAll(
"a[href], button, [tabindex]:not([tabindex='-1'])"
);
if (focusable.length) {
var first = focusable[0];
var last = focusable[focusable.length - 1];
overlay.addEventListener("keydown", function (event) {
if (event.key !== "Tab") return;
if (event.shiftKey && document.activeElement === first) {
event.preventDefault();
last.focus();
} else if (!event.shiftKey && document.activeElement === last) {
event.preventDefault();
first.focus();
}
});
window.requestAnimationFrame(function () {
try { first.focus({ preventScroll: true }); }
catch (_) { first.focus(); }
});
}
if ('inert' in document.documentElement) {
var inertNodes = document.querySelectorAll('[data-inert-default]');
for (var i = 0; i < inertNodes.length; i++) {
inertNodes[i].inert = true;
}
}
})();
