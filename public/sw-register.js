/*! trentpower.fr · /sw-register.js · generated · signed via /integrity.json */
(function () {
'use strict';
function _safeScriptURL(s) {
if (s !== '/sw.js') {
throw new Error('tp-app: script URL not allowed: ' + s);
}
return s;
}
var ttPolicy = (typeof window !== 'undefined' && window.trustedTypes &&
typeof window.trustedTypes.createPolicy === 'function')
? window.trustedTypes.createPolicy('tp-app', { createScriptURL: _safeScriptURL })
: null;
function trustedScriptURL(value) {
return ttPolicy ? ttPolicy.createScriptURL(value) : value;
}
function _recordSwMeta(field, when) {
try {
var raw = localStorage.getItem('tp-sw-meta');
var meta = raw ? JSON.parse(raw) : {};
meta[field] = new Date(when || Date.now()).toISOString();
localStorage.setItem('tp-sw-meta', JSON.stringify(meta));
} catch (_) { }
}
if ('serviceWorker' in navigator) {
try {
navigator.serviceWorker.addEventListener('message', function (ev) {
if (!ev || !ev.data) return;
if (ev.data.type === 'tp-sw-installed') _recordSwMeta('installedAt', ev.data.at);
else if (ev.data.type === 'tp-sw-activated') _recordSwMeta('activatedAt', ev.data.at);
});
} catch (_) {}
}
if ('serviceWorker' in navigator && location.protocol === 'https:') {
var swDebug = location.search.indexOf('debug-sw=1') !== -1;
window.addEventListener('load', function () {
try {
navigator.serviceWorker.register(trustedScriptURL('/sw.js'), { scope: '/' })
.then(function (reg) {
if (swDebug) {
try { console.info('[tp] service worker registered', reg && reg.scope); } catch (_) {}
}
})
.catch(function (err) {
if (swDebug) {
try { console.warn('[tp] service worker registration skipped', err); } catch (_) {}
}
});
} catch (err) {
if (swDebug) {
try { console.warn('[tp] service worker registration unavailable', err); } catch (_) {}
}
}
}, { once: true });
}
})();
