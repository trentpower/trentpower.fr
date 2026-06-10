/*
 * language-gate.js — root language vestibule, local preference only.
 *
 * The vestibule at / is the modal-shell language-choice page. The page
 * is server-rendered visible and works with no JavaScript: the two
 * choices are ordinary <a href="/en-au/"> / <a href="/fr/"> links, and
 * the display language is fixed pre-paint by the inline head script
 * (html[data-preferred-lang], html[data-returning]).
 *
 * Gate v2 — same-page swap.
 * Dismissal no longer reloads the document. Instead it lifts the gate
 * off the publication via the View Transitions API, fetches the chosen
 * edition's <main>, swaps it in place, and pushes the new URL with
 * history.pushState. From the visitor's perspective the hero — which
 * was already rendered behind the scrim — is uncovered. Address bar
 * quietly updates to /en-au/ or /fr/. Same-edition swaps look like a
 * pure dismissal; cross-edition swaps cross-fade visibly.
 *
 * Local-storage vocabulary
 *   tp-last-edition  · 'en-au' | 'fr', written on every explicit choice.
 *                      Read pre-paint by the inline boot script to set
 *                      data-preferred-lang and data-returning so the
 *                      gate paints in the correct variant.
 *   tp-last-read:/en-au/, tp-last-read:/fr/
 *                    · YYYY-MM-DD of the last explicit choice of that
 *                      edition. Day-precision only — never hours or
 *                      minutes; never network-side. Read pre-paint by
 *                      the inline boot script (in language-gate.html)
 *                      to drive the bucketed welcome-back line. Written
 *                      here on every explicit choice.
 *   tp-welcomed:YYYY-MM-DD (sessionStorage)
 *                    · per-day session sentinel. Present means the
 *                      welcome line has already shown this session.
 *                      The inline boot sets it once it decides to
 *                      surface the welcome line; cleared automatically
 *                      when the session ends.
 *   tp-skip-hero-anim · session flag kept for the legacy full-navigation
 *                       fallback path (when View Transitions / fetch
 *                       fails). The same-page swap path never re-paints
 *                       the hero, so it doesn't need the flag.
 *   tp-show-gate     · session flag set by the bfcache fallback path on
 *                       an edition page; the inline boot script reads it
 *                       and we use html[data-gate-restored] here to skip
 *                       the 80ms tap acknowledgement on restoration.
 *
 * Fallbacks (any of these triggers a plain location.assign):
 *   · document.startViewTransition unavailable (older Safari, older FF)
 *   · fetch() rejects (offline; SW will serve cached edition on full nav)
 *   · DOMParser misparses the edition (defensive)
 *
 * No cookies, no telemetry, no third-party scripts. Storage access is
 * wrapped in try/catch; readers with storage disabled get Variant 1 on
 * every visit and a clean full-navigation dismissal.
 */
(function () {
  "use strict";

  var STORAGE_KEY     = "tp-last-edition";
  var SKIP_ANIM_KEY   = "tp-skip-hero-anim";
  var GATE_RESTORED   = "gateRestored";
  var ROUTES          = { "en-au": "/en-au/", "fr": "/fr/" };
  var DEFAULT_EDITION = "en-au";

  var html    = document.documentElement;
  var overlay = document.getElementById("lang-gate");
  var scrim   = document.getElementById("lang-gate-scrim");
  if (!overlay || !scrim) return;

  // ─── welcome line · paint the human interval the boot script
  //     computed on this visit (window.__tpWelcome). The boot script
  //     already set html[data-welcome] before paint, so the [data-when]
  //     reveal has already chosen the welcome branch; here we only
  //     fill in the per-language interval string into the two
  //     [data-tp-last-read] spans. No DOM writes if no welcome state.
  (function () {
    var w = (typeof window !== "undefined") ? window.__tpWelcome : null;
    if (!w) return;
    var slots = overlay.querySelectorAll("[data-tp-last-read]");
    for (var i = 0; i < slots.length; i++) {
      var slot = slots[i];
      // each slot is a child of a [data-gate="en"|"fr"] wrapper; the
      // wrapper handles the language reveal, so we set both spans
      // verbatim with the matching string for that branch.
      var wrap = slot.closest("[data-gate]");
      var lang = wrap && wrap.getAttribute("data-gate");
      slot.textContent = (lang === "fr") ? w.fr : w.en;
    }
  })();

  // ─── storage helpers ──────────────────────────────────────────
  function readEdition() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return (v === "en-au" || v === "fr") ? v : null;
    } catch (_) { return null; }
  }
  function writeEdition(v) {
    try {
      localStorage.setItem(STORAGE_KEY, v);
      // day-precision timestamp for the bucketed welcome line on the
      // next visit. matches the key the inline boot reads.
      var today = new Date().toISOString().slice(0, 10);
      localStorage.setItem("tp-last-read:/" + v + "/", today);
    } catch (_) {}
  }
  function markSkipHeroAnim() {
    try { sessionStorage.setItem(SKIP_ANIM_KEY, "1"); } catch (_) {}
  }

  // ─── dismissal target resolution ──────────────────────────────
  // "dismiss" (×, Esc, scrim click) routes to the stored edition, or
  // to the currently-painted variant: if data-preferred-lang is 'fr'
  // the gate is in Variant 3, so dismissing without an explicit choice
  // means "stay French". Otherwise default to en-au.
  function dismissTarget() {
    var s = readEdition();
    if (s) return s;
    return html.dataset.preferredLang === "fr" ? "fr" : DEFAULT_EDITION;
  }

  // ─── reduced motion ───────────────────────────────────────────
  function reducedMotion() {
    return !!(window.matchMedia &&
              window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  // ─── same-page swap ───────────────────────────────────────────
  // Fetch the target edition's HTML, parse it, and replace the current
  // document's <main>, footer, title, <html lang>, canonical, hreflang
  // links, JSON-LD blocks and body class/data attributes. Wrap in
  // document.startViewTransition where supported so the cross-fade
  // reads as part of the gate's motion vocabulary.
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
    // <main> — the visible body region. The gate's existing <main>
    // doesn't exist on the vestibule (the gate is .modal-shell-scrim
    // overlaying .gate-background). The destination edition page DOES
    // have a real <main>; we insert it just before .modal-shell-scrim,
    // hide the .gate-background, then dismiss the gate normally.
    var oldMain = document.querySelector("main");
    if (oldMain) {
      oldMain.replaceWith(newMain);
    } else {
      // First swap from the gate — insert <main> before the scrim and
      // hide the .gate-background slice (we no longer need it).
      var bg = document.querySelector(".gate-background");
      if (bg) bg.remove();
      var scrimEl = document.getElementById("lang-gate-scrim");
      if (scrimEl && scrimEl.parentNode) {
        scrimEl.parentNode.insertBefore(newMain, scrimEl);
      } else {
        document.body.appendChild(newMain);
      }
    }

    // footer — pulled in alongside <main> so the publication seal lands
    // on the gate document. The vestibule has no footer of its own.
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

    // document identity — title, lang, canonical, hreflang, JSON-LD.
    var newTitle = doc.querySelector("title");
    if (newTitle) document.title = newTitle.textContent;

    var newHtmlLang = doc.documentElement.getAttribute("lang");
    if (newHtmlLang) html.setAttribute("lang", newHtmlLang);

    // canonical link
    var newCanonical = doc.querySelector('link[rel="canonical"]');
    var oldCanonical = document.querySelector('link[rel="canonical"]');
    if (newCanonical && oldCanonical) {
      oldCanonical.setAttribute("href", newCanonical.getAttribute("href"));
    }

    // hreflang cluster — replace the old set with the new set in place.
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

    // JSON-LD — replace text content of existing blocks with the
    // destination's. If counts differ, replace all in bulk.
    var oldJsonLd = document.querySelectorAll('script[type="application/ld+json"]');
    var newJsonLd = doc.querySelectorAll('script[type="application/ld+json"]');
    if (oldJsonLd.length === newJsonLd.length) {
      for (var k = 0; k < oldJsonLd.length; k++) {
        oldJsonLd[k].textContent = newJsonLd[k].textContent;
      }
    }

    // body class + data-attributes — language-gate body becomes the
    // edition page's body for styling purposes (data-page, data-surface).
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

    // history — push the new URL. Use replaceState if we're already
    // on the right URL (the View Transitions branch can fire twice
    // under brittle network conditions; defensive).
    if (location.pathname !== url) {
      history.pushState({ edition: target }, "", url);
    }

    // hero — the destination's hero should paint at rest (it already
    // played behind the scrim during gate v1; with the v2 swap it
    // arrives via DOM and never animates anyway). Force hero-static
    // so any inherited .hero-line settle pins resting on first paint.
    html.classList.add("hero-static");

    // notify other scripts loaded on the gate page (edition.js's
    // footer-switcher + age-localiser) so they can re-wire against
    // the freshly-grafted DOM. delegation-based scripts (theme.js,
    // copy.js) don't need this event; init-based scripts that aren't
    // loaded on the gate (verify-modal.js, reveal.js, overlay.js)
    // would need a more elaborate re-init story, which is out of
    // scope for v2 — those features wait for the next full navigation.
    try {
      document.dispatchEvent(new CustomEvent("tp:edition-swapped", {
        detail: { edition: target, url: url }
      }));
    } catch (_) {}
  }

  // ─── gate dismissal choreography ──────────────────────────────
  // 80ms tap-acknowledgement (choice only) → 400ms scrim+panel exit
  // → swap completes during the View Transitions callback. The gate
  // DOM stays in place; we hide it via [data-gate-exiting] on the
  // scrim and leave it hidden once the transition resolves.
  function dismissToEdition(target, source) {
    var animate = !reducedMotion();
    var restored = html.dataset[GATE_RESTORED] === "true";
    var holdMs = (source === "choice" && animate && !restored) ? 80 : 0;

    function startSwap() {
      // Mark the legacy hero-static handoff defensively — if View
      // Transitions / fetch fails midway and we fall back to full
      // navigation, the destination boot script reads this flag.
      markSkipHeroAnim();

      // Signal the .construction-rail (and any other dismiss-aware
      // element) that the gate is leaving. CSS selector
      // body[data-gate-dismissed] .construction-rail { opacity:0 }
      // runs its 460ms fade concurrently with the scrim/shell exit,
      // finishing ~60ms after the scrim — a soft trailing close.
      // Set on the same dismiss path for all four entry points
      // (choice / × / scrim click / Escape) because they all reach
      // this function. (Historical class name was .home-ribbon.)
      document.body.dataset.gateDismissed = "true";

      // Begin the visual exit immediately so the scrim has started
      // fading before the fetch resolves; the swap happens inside
      // the View Transition's callback, so the cross-fade is atomic.
      if (animate) {
        scrim.setAttribute("data-gate-exiting", "");
      } else {
        // Reduced motion: hide the gate synchronously.
        // phase 96 · native `hidden` instead of inline style.display
        // (csp style-src-attr 'none').
        scrim.hidden = true;
      }

      swapToEdition(target).then(function () {
        if (animate) {
          // After the View Transition resolves the scrim is already
          // visually gone. Detach it from layout to free pointer
          // events and AT focus.
          scrim.hidden = true;
        }
        var bg = document.querySelector(".gate-background");
        if (bg) bg.remove();
      }).catch(function () {
        // Anything went wrong — fetch rejected, parsing failed, the
        // View Transitions API misbehaved. Fall back to plain
        // navigation; SW will serve cached editions if offline.
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

  // ─── popstate / pageshow restoration ──────────────────────────
  // After a same-page swap we're sitting on the / document with
  // /en-au/ or /fr/ in the URL. Browser back popstate brings us
  // back to / — re-show the gate.
  function restoreGate() {
    // Bring the scrim back to active state.
    scrim.removeAttribute("data-gate-exiting");
    // phase 96 · native `hidden = false` instead of inline style.
    scrim.hidden = false;
    scrim.classList.add("is-active");
    // Clear the dismiss flag so the bottom ribbon fades back in (CSS
    // transitions the inverse direction at the same 460ms cubic).
    delete document.body.dataset.gateDismissed;
    // Mark restoration so dismissToEdition skips the 80ms hold.
    html.dataset[GATE_RESTORED] = "true";
    // We don't restore the original /-edition <main>; the visitor
    // can pick again. If we wanted to be tidy we'd re-fetch / and
    // re-insert the original .gate-background, but that's a future
    // refinement — the gate over a now-empty backdrop is fine.
  }

  window.addEventListener("popstate", function (_ev) {
    if (location.pathname === "/") restoreGate();
  });

  // bfcache restore path (legacy full-navigation fallback).
  window.addEventListener("pageshow", function (ev) {
    if (!ev.persisted) return;
    if (location.pathname === "/") restoreGate();
  });

  // ─── × close button ──────────────────────────────────────────
  var closeBtn = document.getElementById("lang-close");
  if (closeBtn) {
    closeBtn.addEventListener("click", function () {
      dismissToEdition(dismissTarget(), "dismiss");
    });
  }

  // ─── Esc key ─────────────────────────────────────────────────
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" || event.key === "Esc") {
      // Only act if the gate is currently visible.
      if (scrim.classList.contains("is-active") &&
          !scrim.hasAttribute("data-gate-exiting")) {
        dismissToEdition(dismissTarget(), "dismiss");
      }
    }
  });

  // ─── scrim click (outside the shell) ─────────────────────────
  scrim.addEventListener("click", function (event) {
    if (event.target === scrim) {
      dismissToEdition(dismissTarget(), "dismiss");
    }
  });

  // ─── choice click ────────────────────────────────────────────
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

  // ─── focus trap ──────────────────────────────────────────────
  // Tab cycles inside the modal; Shift+Tab wraps. Escape is bound
  // separately above (it dismisses).
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

    // Move focus into the modal once the document is interactive.
    window.requestAnimationFrame(function () {
      try { first.focus({ preventScroll: true }); }
      catch (_) { first.focus(); }
    });
  }

  // [data-inert-default] · nu html checker doesn't recognise the
  // `inert` attribute yet, so the gate-background ships without it
  // and we graft it on at boot. the publication backdrop stays
  // visually present but inert to keyboard / pointer.
  if ('inert' in document.documentElement) {
    var inertNodes = document.querySelectorAll('[data-inert-default]');
    for (var i = 0; i < inertNodes.length; i++) {
      inertNodes[i].inert = true;
    }
  }
})();
