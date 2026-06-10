/*! trentpower.fr · /js/copy.js · generated · signed via /integrity.json */
(function () {
'use strict';
var REVERT_MS = 1500;
var CITED_MS = 1000;
function lang() {
return document.documentElement.lang === 'fr' ? 'fr' : 'en';
}
function copiedLabel() {
return lang() === 'fr' ? 'Copié' : 'Copied';
}
function citedLabel() {
return lang() === 'fr' ? 'Citée' : 'Cited';
}
function editionWord() {
return lang() === 'fr' ? 'Édition' : 'Edition';
}
function copyFailedLabel() {
return lang() === 'fr' ? 'Échec de la copie' : 'Copy failed';
}
function copyFailedAnnounce() {
return lang() === 'fr' ? 'Échec de la copie de citation' : 'Citation copy failed';
}
function editionDate() {
var b = document.body && document.body.dataset && document.body.dataset.edition;
if (b) return b;
var m = document.querySelector('meta[name="document-edition"]');
return m ? (m.getAttribute('content') || '') : '';
}
function execCommandCopy(text) {
return new Promise(function (resolve, reject) {
try {
var ta = document.createElement('textarea');
ta.value = text;
ta.setAttribute('readonly', '');
ta.className = 'tp-copy-fallback';
document.body.appendChild(ta);
ta.select();
var ok = document.execCommand && document.execCommand('copy');
document.body.removeChild(ta);
if (ok) resolve(); else reject();
} catch (_) { reject(); }
});
}
function writeClipboard(text) {
if (navigator.clipboard && navigator.clipboard.writeText) {
return navigator.clipboard.writeText(text).catch(function () {
return execCommandCopy(text);
});
}
return execCommandCopy(text);
}
function payloadFor(trigger) {
if (trigger.hasAttribute('data-copy-text')) {
return trigger.getAttribute('data-copy-text') || '';
}
var targetId = trigger.getAttribute('data-copy-target');
var target = targetId ? document.getElementById(targetId) : null;
var raw = target ? (target.textContent || '') : '';
if (trigger.getAttribute('data-copy-collapse') === 'whitespace') {
return raw.replace(/\s+/g, ' ').trim();
}
return raw.replace(/\s+$/, '');
}
function announce(trigger, msg) {
var announceId = trigger.getAttribute('data-copy-announce');
var region = announceId ? document.getElementById(announceId) : null;
if (!region) return null;
region.textContent = '';
setTimeout(function () { region.textContent = msg; }, 0);
return region;
}
function feedback(trigger) {
if (trigger.getAttribute('data-state') === 'copied' ||
trigger.getAttribute('data-state') === 'failed') return;
var done = trigger.getAttribute('data-copy-feedback') || copiedLabel();
var region = announce(trigger, done);
if (trigger.getAttribute('data-copy-mode') === 'cite') {
var resting = trigger.textContent;
var ed = editionDate();
trigger.textContent = ed
? citedLabel() + ' · ' + editionWord() + ' ' + ed
: citedLabel();
trigger.setAttribute('data-state', 'copied');
trigger._restingLabel = resting;
if (trigger._restoreTimer) window.clearTimeout(trigger._restoreTimer);
trigger._restoreTimer = window.setTimeout(function () {
trigger.textContent = trigger._restingLabel || resting;
trigger.removeAttribute('data-state');
trigger._restingLabel = null;
trigger._restoreTimer = null;
if (region) region.textContent = '';
}, CITED_MS);
try {
document.dispatchEvent(new CustomEvent('tp:citation-copied'));
} catch (_) {}
return;
}
var resting2 = trigger.textContent;
trigger.textContent = done;
trigger.setAttribute('data-state', 'copied');
setTimeout(function () {
trigger.textContent = resting2;
trigger.removeAttribute('data-state');
if (region) region.textContent = '';
}, REVERT_MS);
}
function failure(trigger) {
if (trigger.getAttribute('data-copy-mode') !== 'cite') return;
if (trigger.getAttribute('data-state') === 'copied' ||
trigger.getAttribute('data-state') === 'failed') return;
var resting = trigger.textContent;
trigger.textContent = copyFailedLabel();
trigger.setAttribute('data-state', 'failed');
var region = announce(trigger, copyFailedAnnounce());
trigger._restingLabel = resting;
if (trigger._restoreTimer) window.clearTimeout(trigger._restoreTimer);
trigger._restoreTimer = window.setTimeout(function () {
trigger.textContent = trigger._restingLabel || resting;
trigger.removeAttribute('data-state');
trigger._restingLabel = null;
trigger._restoreTimer = null;
if (region) region.textContent = '';
}, CITED_MS);
}
document.addEventListener('click', function (e) {
var trigger = e.target && e.target.closest
? e.target.closest('[data-copy-target], [data-copy-text]')
: null;
if (!trigger) return;
var payload = payloadFor(trigger);
if (!payload) return;
e.preventDefault();
writeClipboard(payload).then(
function () { feedback(trigger); },
function () { failure(trigger); }
);
});
window.TP_COPY = {
copy: function (text) { return writeClipboard(String(text == null ? '' : text)); }
};
})();
