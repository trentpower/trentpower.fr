/*! trentpower.fr · /source/view/source-view.js · authored · signed via /integrity.json */
(function () {
  'use strict';

  var MANIFEST = (typeof window !== 'undefined' && window.TP_SOURCE_VIEW_MANIFEST) || {};

  // canonical route form of a manifest live_path. /index.html and
  // /privacy/index.html collapse to /, /privacy/; non-index live paths
  // pass through unchanged. used both for the ?path= query value the
  // address bar exposes and for the internal-link rewriter that turns
  // /privacy/ inside source into an in-reader navigation.
  function canonicalPathFor(livePath) {
    if (!livePath) return '';
    return livePath.replace(/\/index\.html$/, '/');
  }

  // Build a reverse lookup once: canonical-route → manifest entry. Allows
  // ?path=/privacy/ to resolve back to the right source mirror without
  // a second fetch. Also keys each entry by its raw live_path so deep
  // internal links to /styles.css (which has no /index.html collapse)
  // still resolve.
  var MANIFEST_BY_PATH = {};
  (function () {
    for (var _k in MANIFEST) {
      if (!Object.prototype.hasOwnProperty.call(MANIFEST, _k)) continue;
      var _entry = MANIFEST[_k];
      var _lp = _entry && _entry.live_path;
      if (!_lp) continue;
      MANIFEST_BY_PATH[_lp] = _k;
      var _canon = canonicalPathFor(_lp);
      if (_canon !== _lp) MANIFEST_BY_PATH[_canon] = _k;
    }
  })();

  // Per-render state shared by the selection toolbar, raw-line copy,
  // and internal-link rewriter. populated by renderCode().
  var _reader = {
    rawLines: [],
    livePath: '',
    pathQuery: '',
    fileKey: ''
  };

  // TrustedTypes policy for tokenized code block innerHTML.
  // CSP for /source/view/ lists trusted-types tp-app tp-source-view.
  var _svPolicy = null;
  try {
    if (window.trustedTypes && typeof window.trustedTypes.createPolicy === 'function') {
      _svPolicy = window.trustedTypes.createPolicy('tp-source-view', {
        createHTML: function (s) { return s; }
      });
    }
  } catch (_) {}

  function safeHTML(el, html) {
    el.innerHTML = _svPolicy ? _svPolicy.createHTML(html) : html;
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) n.setAttribute(k, attrs[k]);
    }
    if (text != null) n.textContent = text;
    return n;
  }

  // source-reader UI vocabulary, both editions. the reader builds its
  // own chrome by script, so its labels live here; they are picked off
  // the page's <html lang>. no translation runtime, no window.I18N.
  var SR_I18N = {
    en: {"source_reader":{"title":"Source reader","loading":"Loading source…","action":{"canonical":"Canonical","verify":"Verify","plain_text":"Raw","copy_code":"Copy code","wrap_lines":"Wrap lines","unwrap_lines":"Unwrap lines","back_to_top":"Top","copied":"Copied","view_source":"Source","view_annotated":"Annotated","view_rendered_page":"View rendered page","reading_mode":"Reading mode","top":"Top","copy":"Copy","copy_link":"Copy link","clear":"Clear","count_line_one":"1 line","count_lines_many":"{n} lines","line_selected":"Line {n} selected","range_selected":"Lines {start} to {end} selected","selection_cleared":"Selection cleared","lines_copied":"{n} lines copied","link_copied":"Link copied","copy_failed":"Copy unavailable","link_copied_normalised":"Link copied — normalised to lines {start} to {end}"},"meta":{"validated":"Verified","part_of":"Related systems:","document_map":"Document map","end_of_source":"End of source mirror","intent":"This reader presents public source mirrors with structural annotations and signed publication references."},"integrity":{"canonical":"Canonical file","edition":"Edition","sha256":"SHA-256","signed_release":"Signed release"},"map_label":{"head":"Head","identity":"Identity","discovery":"Discovery","social_preview":"Social preview","assets":"Assets","structured_data":"Structured data","header":"Header","main":"Main","footer":"Footer","tokens":"Tokens","fonts":"Fonts","base":"Base","layout":"Layout","components":"Components","responsive":"Responsive","print":"Print","state":"State","i18n":"i18n","events":"Events","modals":"Modals","copy":"Copy","verification":"Verification","init":"Init","policy":"Policy","records":"Records"},"mode":{"label":"Reading mode","source":"Source","annotated":"Annotated","raw":"Raw"},"end":{"title":"End of source mirror","edition":"Edition","sha256":"SHA-256","signed_release":"Signed release"},"kind":{"html":"HyperText Markup Language","css":"Cascading Style Sheets","js":"JavaScript","json":"JavaScript Object Notation","xml":"Extensible Markup Language","text":"Plain text","apache":"Apache configuration","sig":"Detached PGP signature","asc":"ASCII-armoured PGP key"},"gloss":{"foundations":"character encoding, viewport, colour scheme.","head":"document head — metadata, no rendered content.","identity":"authorship, application name, attribution links.","document":"page title, description, canonical url.","discovery":"indexing and referrer policy.","social":"open graph and twitter card metadata.","assets":"stylesheets, scripts, icons, manifest.","icons":"platform icons and home-screen artwork.","structured":"json-ld schema, machine-readable identity.","header":"site header — wordmark and primary nav.","footer":"colophon, language switch, footer actions.","script":"site application logic.","tokens":"design tokens — colours, typography, spacing.","fonts":"font face declarations and font assets.","base":"reset and base element typography.","layout":"page-level layout grammar.","components":"reusable component styles.","responsive":"viewport-aware overrides.","print":"print stylesheet rules.","state":"application state and runtime variables.","i18n":"translation lookup and language switching.","events":"event listeners and interaction wiring.","modals":"overlay surfaces, dialogs, focus traps.","copy":"clipboard interactions.","verification":"signed-manifest and cryptographic references.","records":"editorial record entries.","init":"boot sequence — runs once on load.","policy":"declared site policies."}}},
    fr: {"source_reader":{"title":"Lecteur source","loading":"Chargement du source…","action":{"canonical":"Canonique","verify":"Vérifier","plain_text":"Brut","copy_code":"Copier le code","wrap_lines":"Retour à la ligne","unwrap_lines":"Sans retour à la ligne","back_to_top":"Haut","copied":"Copié","view_source":"Source","view_annotated":"Annoté","view_rendered_page":"Voir la page rendue","reading_mode":"Mode de lecture","top":"Haut","copy":"Copier","copy_link":"Copier le lien","clear":"Effacer","count_line_one":"1 ligne","count_lines_many":"{n} lignes","line_selected":"Ligne {n} sélectionnée","range_selected":"Lignes {start} à {end} sélectionnées","selection_cleared":"Sélection effacée","lines_copied":"{n} lignes copiées","link_copied":"Lien copié","link_copied_normalised":"Lien copié — normalisé aux lignes {start} à {end}","copy_failed":"Copie indisponible"},"meta":{"validated":"Vérifié","part_of":"Systèmes liés :","document_map":"Plan du document","end_of_source":"Fin du miroir source","intent":"Ce lecteur présente les miroirs publics du code source, avec annotations structurelles et références de publication signées."},"integrity":{"canonical":"Fichier canonique","edition":"Édition","sha256":"SHA-256","signed_release":"Publication signée"},"map_label":{"head":"Tête","identity":"Identité","discovery":"Découvrabilité","social_preview":"Aperçu social","assets":"Ressources","structured_data":"Données structurées","header":"En-tête","main":"Contenu principal","footer":"Pied de page","tokens":"Jetons","fonts":"Polices","base":"Base","layout":"Mise en page","components":"Composants","responsive":"Responsive","print":"Impression","state":"État","i18n":"i18n","events":"Événements","modals":"Modales","copy":"Copie","verification":"Vérification","init":"Initialisation","policy":"Politique","records":"Enregistrements"},"mode":{"label":"Mode de lecture","source":"Source","annotated":"Annoté","raw":"Brut"},"end":{"title":"Fin du miroir source","edition":"Édition","sha256":"SHA-256","signed_release":"Publication signée"},"kind":{"html":"Langage de balisage hypertexte","css":"Feuilles de style en cascade","js":"JavaScript","json":"Notation d'objet JavaScript","xml":"Langage de balisage extensible","text":"Texte brut","apache":"Configuration Apache","sig":"Signature PGP détachée","asc":"Clé PGP en ASCII-armor"},"gloss":{"foundations":"encodage des caractères, fenêtre d'affichage, palette.","head":"en-tête du document — métadonnées, aucun contenu rendu.","identity":"auteur, nom de l'application, liens d'attribution.","document":"titre de la page, description, URL canonique.","discovery":"politique d'indexation et de référent.","social":"métadonnées open graph et twitter card.","assets":"feuilles de style, scripts, icônes, manifeste.","icons":"icônes de plateforme et illustration d'écran d'accueil.","structured":"schéma json-ld, identité lisible par machine.","header":"en-tête du site — sigle et navigation principale.","footer":"colophon, sélecteur de langue, actions de pied de page.","script":"logique applicative du site.","tokens":"jetons de design — couleurs, typographie, espacements.","fonts":"déclarations @font-face et fichiers de police.","base":"réinitialisation et typographie des éléments de base.","layout":"grammaire de mise en page au niveau de la page.","components":"styles de composants réutilisables.","responsive":"ajustements selon la fenêtre d'affichage.","print":"règles de feuille de style pour l'impression.","state":"état applicatif et variables d'exécution.","i18n":"résolution des traductions et changement de langue.","events":"écouteurs d'événements et câblage des interactions.","modals":"surfaces superposées, dialogues, pièges de focus.","copy":"interactions avec le presse-papiers.","verification":"manifeste signé et références cryptographiques.","records":"fiches éditoriales.","init":"séquence de démarrage — exécutée une fois au chargement.","policy":"politiques déclarées du site."}}}
  };

  // i18n lookup — resolves `source_reader.*` keys against SR_I18N for
  // the page's language; returns the raw key if absent so the ui
  // never goes blank.
  function t(key) {
    var lang = document.documentElement.lang === 'fr' ? 'fr' : 'en';
    var obj = SR_I18N[lang] || SR_I18N.en;
    var parts = key.split('.');
    for (var i = 0; i < parts.length; i++) {
      if (obj == null) return key;
      obj = obj[parts[i]];
    }
    return typeof obj === 'string' ? obj : key;
  }

  // i18n with simple {placeholder} substitution. used by toolbar count
  // ("{n} lines") and the live-region announcer ("line {n} selected").
  function tf(key, vars) {
    var s = t(key);
    if (!vars) return s;
    return s.replace(/\{(\w+)\}/g, function (_, n) {
      return Object.prototype.hasOwnProperty.call(vars, n) ? String(vars[n]) : ('{' + n + '}');
    });
  }

  // clipboard writes delegate to the shared /copy.js module, exposed as
  // window.TP_COPY — one clipboard implementation for the whole site.
  // always returns a promise so callers can announce success / failure
  // through the existing aria-live region.
  function writeClipboard(text) {
    if (window.TP_COPY && window.TP_COPY.copy) {
      return window.TP_COPY.copy(text);
    }
    return Promise.reject(new Error('clipboard module unavailable'));
  }

  // ─── Tokenizer ────────────────────────────────────────────────────────────
  // Converts raw source text into an array of per-line HTML strings.
  // Escapes happen inside each handler so spans wrap safe content only.

  function span(cls, raw) {
    return '<span class="tok-' + cls + '">' + esc(raw) + '</span>';
  }

  // HTML tokenizer — processes one line with a mutable state object.
  function tokenizeHTMLLine(line, st) {
    var out = '';
    var i = 0;
    var n = line.length;

    // Carry over an open comment from a previous line.
    if (st.inComment) {
      var end = line.indexOf('-->');
      if (end === -1) { return span('comment', line); }
      out += span('comment', line.slice(0, end + 3));
      st.inComment = false;
      i = end + 3;
    }

    while (i < n) {
      // HTML comment
      if (line[i] === '<' && line.slice(i, i + 4) === '<!--') {
        var ce = line.indexOf('-->', i + 4);
        if (ce === -1) { out += span('comment', line.slice(i)); st.inComment = true; i = n; continue; }
        out += span('comment', line.slice(i, ce + 3)); i = ce + 3; continue;
      }
      // Doctype
      if (line[i] === '<' && line.slice(i, i + 9).toLowerCase() === '<!doctype') {
        var de = line.indexOf('>', i);
        if (de === -1) de = n - 1;
        out += span('keyword', line.slice(i, de + 1)); i = de + 1; continue;
      }
      // Tag
      if (line[i] === '<') {
        var te = line.indexOf('>', i);
        if (te === -1) { out += renderHTMLTag(line.slice(i)); i = n; continue; }
        out += renderHTMLTag(line.slice(i, te + 1)); i = te + 1; continue;
      }
      // Text — advance to next '<'
      var nx = line.indexOf('<', i);
      if (nx === -1) nx = n;
      out += esc(line.slice(i, nx)); i = nx;
    }
    return out;
  }

  // Semantic role classification for HTML tokens.
  // The reader teaches architecture visually: structural elements read a
  // touch sharper, metadata reads quieter, trust attributes carry a subtle
  // oxblood tint, accessibility attributes a soft highlight. All deltas are
  // restrained — colour and weight only, never size or rhythm.
  var STRUCTURAL_TAGS = {
    html:1, body:1, header:1, nav:1, main:1, article:1, section:1,
    footer:1, aside:1, figure:1, figcaption:1, dialog:1
  };
  var METADATA_TAGS = {
    head:1, meta:1, link:1, base:1, title:1, style:1, noscript:1
  };
  var TRUST_ATTRS = {
    integrity:1, crossorigin:1, referrerpolicy:1, nonce:1
  };
  var A11Y_ATTR_PREFIX = 'aria-';
  var A11Y_ATTRS = { role:1, tabindex:1 };
  var TRUST_REL_VALUES = {
    canonical:1, author:1, me:1, manifest:1, attribution:1, license:1,
    'icon':1, 'apple-touch-icon':1
  };

  function tagClass(name) {
    var key = name.toLowerCase();
    if (STRUCTURAL_TAGS[key]) return 'tok-tag tok-tag--structural';
    if (METADATA_TAGS[key])   return 'tok-tag tok-tag--metadata';
    return 'tok-tag';
  }

  function attrClass(name) {
    var key = name.toLowerCase();
    if (TRUST_ATTRS[key]) return 'tok-attr tok-attr--trust';
    if (A11Y_ATTRS[key] || key.indexOf(A11Y_ATTR_PREFIX) === 0) return 'tok-attr tok-attr--a11y';
    return 'tok-attr';
  }

  // Returns true when `rel=` carries a trust-class value (canonical author …).
  // Called only after we know the attribute name is "rel" (lowercased).
  function isTrustRelValue(rawValueWithQuotes) {
    var v = rawValueWithQuotes.replace(/^['"]|['"]$/g, '').trim().toLowerCase();
    return v.split(/\s+/).some(function (tok) { return TRUST_REL_VALUES[tok]; });
  }

  function renderHTMLTag(raw) {
    // Tokenize tag internals: < / tagname attr="value" > / />
    var out = '';
    var i = 0;
    var n = raw.length;
    // opening <
    out += '<span class="tok-punctuation">&lt;</span>'; i++;
    // optional /
    if (raw[i] === '/') { out += '<span class="tok-punctuation">/</span>'; i++; }
    // tag name — emit with semantic role class if known.
    var ne = i;
    while (ne < n && !/[\s>/]/.test(raw[ne])) ne++;
    if (ne > i) {
      var tagName = raw.slice(i, ne);
      out += '<span class="' + tagClass(tagName) + '">' + esc(tagName) + '</span>';
      i = ne;
    }
    // attributes
    while (i < n) {
      var c = raw[i];
      if (c === '>') { out += '<span class="tok-punctuation">&gt;</span>'; i++; continue; }
      if (c === '/') { out += '<span class="tok-punctuation">/</span>'; i++; continue; }
      if (/\s/.test(c)) { out += esc(c); i++; continue; }
      // attribute name — emit with trust / a11y class if applicable.
      var ae = i;
      while (ae < n && !/[\s=>/]/.test(raw[ae])) ae++;
      var attrName = raw.slice(i, ae);
      var attrCls = attrClass(attrName);
      out += '<span class="' + attrCls + '">' + esc(attrName) + '</span>';
      i = ae;
      if (raw[i] !== '=') continue;
      out += '<span class="tok-punctuation">=</span>'; i++;
      var q = raw[i];
      if (q === '"' || q === "'") {
        var qe = raw.indexOf(q, i + 1);
        if (qe === -1) qe = n;
        var rawValue = raw.slice(i, qe + 1);
        // promote rel="canonical|author|me|…" to the trust register so
        // the string itself reads as trust, not as a plain attribute
        // value. similarly, values bound to a11y attributes (aria-*,
        // role, tabindex) inherit the soft-highlight ink so name and
        // value read as one phrase.
        var valueCls = 'tok-string';
        var attrLower = attrName.toLowerCase();
        if (attrLower === 'rel' && isTrustRelValue(rawValue)) {
          valueCls = 'tok-string tok-string--trust';
        } else if (A11Y_ATTRS[attrLower] || attrLower.indexOf(A11Y_ATTR_PREFIX) === 0) {
          valueCls = 'tok-string tok-string--a11y';
        }
        out += '<span class="' + valueCls + '">' + esc(rawValue) + '</span>';
        i = qe + 1; continue;
      }
      // unquoted value
      var ve = i;
      while (ve < n && !/[\s>]/.test(raw[ve])) ve++;
      out += span('string', raw.slice(i, ve)); i = ve;
    }
    return out;
  }

  // CSS tokenizer — handles block comments (multiline) and strings.
  function tokenizeCSSLine(line, st) {
    var out = '';
    var i = 0;
    var n = line.length;

    if (st.inComment) {
      var end = line.indexOf('*/');
      if (end === -1) return span('comment', line);
      out += span('comment', line.slice(0, end + 2));
      st.inComment = false; i = end + 2;
    }

    while (i < n) {
      // Block comment open
      if (line[i] === '/' && line[i + 1] === '*') {
        var ce = line.indexOf('*/', i + 2);
        if (ce === -1) { out += span('comment', line.slice(i)); st.inComment = true; i = n; continue; }
        out += span('comment', line.slice(i, ce + 2)); i = ce + 2; continue;
      }
      // String
      var q = line[i];
      if (q === '"' || q === "'") {
        var qe = i + 1;
        while (qe < n && line[qe] !== q) { if (line[qe] === '\\') qe++; qe++; }
        out += span('string', line.slice(i, qe + 1)); i = qe + 1; continue;
      }
      // CSS token hint: property names and values (very basic)
      out += esc(line[i]); i++;
    }
    return out;
  }

  // JS tokenizer — handles comments, strings, keywords.
  var JS_KEYWORDS = /\b(var|let|const|function|return|if|else|for|while|do|switch|case|break|continue|new|this|typeof|instanceof|null|undefined|true|false|class|extends|import|export|default|try|catch|finally|throw|void|delete|in|of|async|await)\b/g;

  function tokenizeJSLine(line, st) {
    var out = '';
    var i = 0;
    var n = line.length;

    if (st.inComment) {
      var end = line.indexOf('*/');
      if (end === -1) return span('comment', line);
      out += span('comment', line.slice(0, end + 2));
      st.inComment = false; i = end + 2;
    }

    // Collect segments, then apply keyword highlighting to non-span text.
    var segments = [];
    while (i < n) {
      // Block comment
      if (line[i] === '/' && line[i + 1] === '*') {
        var ce = line.indexOf('*/', i + 2);
        if (ce === -1) { segments.push({ t: 'comment', v: line.slice(i) }); st.inComment = true; i = n; continue; }
        segments.push({ t: 'comment', v: line.slice(i, ce + 2) }); i = ce + 2; continue;
      }
      // Line comment
      if (line[i] === '/' && line[i + 1] === '/') {
        segments.push({ t: 'comment', v: line.slice(i) }); i = n; continue;
      }
      // String (', ", `)
      var q = line[i];
      if (q === '"' || q === "'" || q === '`') {
        var qe = i + 1;
        while (qe < n && line[qe] !== q) { if (line[qe] === '\\') qe++; qe++; }
        segments.push({ t: 'string', v: line.slice(i, qe + 1) }); i = qe + 1; continue;
      }
      // Accumulate plain text
      var start = i;
      while (i < n) {
        var c = line[i];
        if (c === '/' || c === '"' || c === "'" || c === '`') break;
        i++;
      }
      if (i > start) segments.push({ t: 'plain', v: line.slice(start, i) });
    }

    for (var s = 0; s < segments.length; s++) {
      var seg = segments[s];
      if (seg.t === 'comment') { out += span('comment', seg.v); continue; }
      if (seg.t === 'string')  { out += span('string',  seg.v); continue; }
      // plain — apply keyword highlighting
      out += esc(seg.v).replace(JS_KEYWORDS, function (kw) {
        return '<span class="tok-keyword">' + kw + '</span>';
      });
    }
    return out;
  }

  // JSON tokenizer — keys + string values + primitives.
  function tokenizeJSONLine(line) {
    // Quick pass: highlight string keys before ':', string values, true/false/null, numbers.
    var out = esc(line);
    // Already escaped — we're working on the escaped form (no < or > in JSON values typically).
    // Apply in order: object keys, then string values, then primitives.
    // This is intentionally simple since JSON is machine-generated in these files.
    out = out
      .replace(/(&quot;[^&]*&quot;)(\s*:)/g, '<span class="tok-attr">$1</span>$2')
      .replace(/:\s*(&quot;[^&]*&quot;)/g, function (m, s) { return ': <span class="tok-string">' + s + '</span>'; })
      .replace(/\b(true|false|null)\b/g, '<span class="tok-keyword">$1</span>')
      .replace(/\b(-?\d+\.?\d*(?:[eE][+-]?\d+)?)\b/g, '<span class="tok-number">$1</span>');
    return out;
  }

  function tokenizeAll(text, kind) {
    var lines = splitSourceLines(text);
    var st = { inComment: false };
    return lines.map(function (line) {
      if (kind === 'html')   return tokenizeHTMLLine(line, st);
      if (kind === 'css')    return tokenizeCSSLine(line, st);
      if (kind === 'js')     return tokenizeJSLine(line, st);
      if (kind === 'json')   return tokenizeJSONLine(line);
      return esc(line);
    });
  }

  // ─── DOM rendering ────────────────────────────────────────────────────────

  // ─── Section gloss map ────────────────────────────────────────────────
  // short structural explanations of common section markers. revealed only
  // in annotated view mode. one line each, never tutorial prose: each entry
  // describes what the section structurally is, not why it matters. lowercase
  // keys, matched against the lowercased first token of the marker label.
  //
  // Provenance discipline: these strings are INTERPRETIVE annotations
  // generated by the reader, not source content. They are visually marked
  // as such (italic serif, em-dash prefix) so the archival boundary between
  // canonical source and editorial gloss is never falsified.
  // Annotate ONLY when the annotation adds meaning. Generic semantic-
  // landmark glosses (main / nav / article / section) say nothing the
  // tag itself already says; they are deliberately omitted so the
  // annotated mode reads as intelligent, not exhaustive.
  var SECTION_GLOSSES = {
    foundations:  'character encoding, viewport, colour scheme.',
    head:         'document head — metadata, no rendered content.',
    identity:     'authorship, application name, attribution links.',
    document:     'page title, description, canonical url.',
    discovery:    'indexing and referrer policy.',
    social:       'open graph and twitter card metadata.',
    assets:       'stylesheets, scripts, icons, manifest.',
    icons:        'platform icons and home-screen artwork.',
    structured:   'json-ld schema, machine-readable identity.',
    header:       'site header — wordmark and primary nav.',
    footer:       'colophon, language switch, footer actions.',
    script:       'site application logic.',
    tokens:       'design tokens — colours, typography, spacing.',
    fonts:        'font face declarations and font assets.',
    base:         'reset and base element typography.',
    layout:       'page-level layout grammar.',
    components:   'reusable component styles.',
    responsive:   'viewport-aware overrides.',
    print:        'print stylesheet rules.',
    state:        'application state and runtime variables.',
    i18n:         'translation lookup and language switching.',
    events:       'event listeners and interaction wiring.',
    modals:       'overlay surfaces, dialogs, focus traps.',
    copy:         'clipboard interactions.',
    verification: 'signed-manifest and cryptographic references.',
    records:      'editorial record entries.',
    init:         'boot sequence — runs once on load.',
    policy:       'declared site policies.'
  };

  // ─── Density tiers ────────────────────────────────────────────────────
  // Section markers carry three weights:
  //   tier-1  major structural anchors (head, main, footer, structured data,
  //           body, header) — uppercase, slightly stronger presence.
  //   tier-2  architectural notes (identity, discovery, assets, social, …) —
  //           the default for most curated and author markers.
  //   tier-3  micro guidance (the gloss line itself) — quiet italic serif.
  // This hierarchy adds typographic structure without adding noise; every
  // delta is opacity or letter-spacing only, never a different colour or
  // a different size class.
  var TIER1_LABELS = {
    head:1, main:1, footer:1, body:1, header:1, structured:1
  };
  function markerTier(label) {
    var key = String(label || '').toLowerCase().split(/[\s#.]/)[0];
    return TIER1_LABELS[key] ? 1 : 2;
  }

  function classifyCommentTier(raw) {
    var text = (raw || '').trim();
    if (!text) return '';
    var bare = text
      .replace(/^\/\/+\s?/, '')
      .replace(/^#\s?/, '')
      .replace(/^\/\*+\s?/, '')
      .replace(/\*\/$/, '')
      .replace(/^<!--\s?/, '')
      .replace(/-->$/, '')
      .trim();
    var lower = bare.toLowerCase();
    if (!bare) return '';
    if (/^(generated|auto-generated|source:\s*generated|build:|checksum:|hash:|integrity:)/.test(lower)) return 'generated';
    if (/^(todo|fixme|eslint|ts-|jshint|stylelint|pragma|nolint|istanbul|cspell|@type|type:)/.test(lower)) return 'technical';
    if (/^(edition:|archival:|note:|philosophy:|provenance:|intent:)/.test(lower)) return 'editorial-prose';
    if (/[.!?]\s*$/.test(bare) || bare.split(/\s+/).length >= 8) return 'editorial-prose';
    return 'technical';
  }

  function rhythmInterval(kind, total) {
    if (total < 70) return 0;
    var mobile = !!(window.matchMedia && window.matchMedia('(max-width: 42rem)').matches);
    if (kind === 'json') return mobile ? 44 : 52;
    if (kind === 'txt' || kind === 'htaccess') return mobile ? 40 : 48;
    return mobile ? 42 : 48;
  }
  // markerMap: { lineIndex0based: { label, type: 'author'|'structure' } }
  // author markers inject a full section-divider with border;
  // structure markers inject a quieter label, no border.
  function renderLines(rawLines, htmlLines, markerMap, kind) {
    // Builds the code block HTML string — set via safeHTML (TrustedTypes).
    //
    // Output structure: markers → inert <span class="section-divider">
    // labels; every source line → a <span class="code-line"> carrying
    // its line-number anchor.
    //
    // Container choice: spans are valid phrasing content inside <pre>, so
    // the html-correctness validator accepts the markup.
    markerMap = markerMap || {};
    var parts = [];
    var prevComment = false;
    var prevEmpty = false;

    for (var i = 0; i < htmlLines.length; i++) {
      var n = i + 1;
      var h = htmlLines[i];
      var raw = rawLines[i] || '';
      var isEmpty = h.trim() === '';
      var isComment = !isEmpty && h.indexOf('tok-comment') !== -1 &&
                      h.indexOf('tok-tag') === -1 && h.indexOf('tok-attr') === -1;
      var marker = markerMap[i];
      var isMarked = !!marker;
      var lead = isComment && !isMarked && !prevComment && !prevEmpty;
      var commentTier = isComment ? classifyCommentTier(raw) : '';
      var rhythmEvery = rhythmInterval(kind, htmlLines.length);
      var hasRhythmBreak = rhythmEvery > 0 && n > 1 && (n % rhythmEvery) === 0;
      var cls = 'code-line' +
        (isMarked ? ' code-line--section-marker' : '') +
        (lead ? ' code-line--comment-lead' : '') +
        (hasRhythmBreak ? ' code-line--rhythm-break' : '') +
        (commentTier ? ' code-line--comment-' + commentTier : '');
      if (marker) {
        // tier classifies the marker's visual weight (1 = major structural
        // anchor, 2 = architectural note). type ('author' | 'structure')
        // separately records provenance — author markers originate in
        // source comments, structure markers in structural html tags.
        var tier = markerTier(marker.label);
        var divCls = 'section-divider section-divider--' + marker.type +
                     ' section-divider--tier-' + tier;
        // optional annotated gloss for known section-marker labels.
        // hidden by default; revealed under body[data-source-mode="annotated"]
        // via css. lowercase key + trim so glosses match author and
        // structural markers consistently. the gloss is INTERPRETIVE: it
        // does not appear in source mode, and when shown it carries an
        // em-dash prefix and italic-serif treatment so the archival
        // boundary between source comment and editorial annotation is
        // visible to the reader.
        var glossKey = (marker.label || '').toLowerCase().split(/[\s#.]/)[0];
        // i18n-first lookup; SECTION_GLOSSES is the english fallback
        // when no translation is registered for this key.
        var glossText = '';
        if (glossKey) {
          var glossI18nKey = 'source_reader.gloss.' + glossKey;
          var translatedGloss = t(glossI18nKey);
          if (translatedGloss && translatedGloss !== glossI18nKey) glossText = translatedGloss;
        }
        if (!glossText) glossText = SECTION_GLOSSES[glossKey] || '';
        var glossAttr = glossText ? ' data-gloss="' + esc(glossText) + '"' : '';
        var hasGloss = !!glossText;
        var divAttrs = ' aria-hidden="true"';
        var glossHtml = hasGloss
          ? '<span class="section-divider-gloss" aria-hidden="true">' +
            '<span class="section-divider-gloss-mark" aria-hidden="true">— </span>' +
            esc(glossText) +
            '</span>'
          : '';
        parts.push(
          '<span class="' + divCls + '"' + divAttrs + glossAttr + '>' +
          '<span class="section-divider-label">' + esc(marker.label) + '</span>' +
          glossHtml +
          '</span>'
        );
      }
      parts.push(
        '<span class="' + cls + '" id="L' + n + '">' +
        '<a class="line-number" href="#L' + n + '" aria-label="Line ' + n + '" aria-pressed="false">' +
        '<span class="ln-num">' + n + '</span>' +
        '<span class="ln-sym" aria-hidden="true">§</span>' +
        '</a>' +
        '<span class="line-code">' + h + '</span>' +
        '</span>'
      );
      prevComment = isComment;
      prevEmpty = isEmpty;
    }
    return parts.join('');
  }

  function renderMeta(meta, _fileKey) {
    var root = document.getElementById('source-view-root');
    if (!root) return;
    while (root.firstChild) root.removeChild(root.firstChild);

    // Default mode is raw — the literal canonical mirror. Annotated mode is
    // an opt-in editorial overlay. The body attribute drives every
    // mode-conditional CSS rule (no .source-reader-annotated class needed).
    if (!document.body.hasAttribute('data-source-mode')) {
      document.body.setAttribute('data-source-mode', 'raw');
    }

    // ── intro header ── matches the privacy / security / source / integrity
    // hero hierarchy: page-kicker → page-title.hero-stack (with hero-line) →
    // page-lede. .reader-h1 is a scoped modifier so the filename <code>
    // wraps cleanly on long paths without leaking into the global rule.
    var intro = el('header', { 'class': 'reader-intro page-hero' });
    intro.appendChild(el('p', { 'class': 'page-kicker reader-eyebrow', 'data-i18n': 'source_reader.title' }, t('source_reader.title')));
    var h1 = el('h1', { 'class': 'page-title hero-stack reader-h1 reader-h1--source' });
    var heroLine = el('span', { 'class': 'hero-line' });
    heroLine.appendChild(el('code', {}, meta.label));
    h1.appendChild(heroLine);
    intro.appendChild(h1);
    // description is the editorial one-line role for this file. the
    // manifest carries the english fallback; the i18n key (also on the
    // manifest entry) lets the active language win when it has one.
    var descText = '';
    if (meta.i18n_key) {
      var translated = t(meta.i18n_key);
      if (translated && translated !== meta.i18n_key) descText = translated;
    }
    if (!descText) descText = meta.description || '';
    if (descText) intro.appendChild(el('p', { 'class': 'page-lede reader-description' }, descText));
    // one quiet conceptual line — interpretive, so it only renders in
    // annotated mode (controlled by body[data-source-mode] in css).
    intro.appendChild(el('p', { 'class': 'reader-intent', 'data-i18n': 'source_reader.meta.intent' }, t('source_reader.meta.intent')));
    // kind + size on one line
    var metaEl = document.createElement('p');
    metaEl.className = 'reader-meta';
    var kindEl = el('abbr', { 'title': kindFullName(meta.kind) }, meta.kind.toUpperCase());
    metaEl.appendChild(kindEl);
    metaEl.appendChild(document.createTextNode(' · ' + meta.size));
    intro.appendChild(metaEl);

    // validated date — separate line for breathing room
    if (meta.modified) {
      var dateEl = document.createElement('p');
      dateEl.className = 'reader-meta-date';
      dateEl.appendChild(el('time', { 'datetime': meta.modified }, t('source_reader.meta.validated') + ' ' + formatDate(meta.modified)));
      intro.appendChild(dateEl);
    }

    root.appendChild(intro);

    // ── reading mode row ──
    // annotated mode hidden 2026-05-16 · the curated annotation
    // vocabulary isn't yet at the editorial standard the rest of
    // the site holds itself to. the underlying logic (gloss labels,
    // document map, section dividers) is preserved in the
    // codebase; only the UI toggle is suppressed. data-source-mode
    // is force-reset to "raw" so any cached annotated state from
    // an earlier session falls back gracefully.
    document.body.setAttribute('data-source-mode', 'raw');
    document.body.classList.remove('source-reader-annotated');

    var nav = el('nav', { 'class': 'reader-actions', 'aria-label': 'Reading mode' });
    var viewGroup = el('span', { 'class': 'reader-view-toggle', 'role': 'group', 'aria-label': t('source_reader.mode.label') });
    viewGroup.appendChild(el('span', { 'class': 'reader-view-toggle-label', 'data-i18n': 'source_reader.mode.label' }, t('source_reader.mode.label')));
    var srcBtn = el('button', { 'type': 'button', 'class': 'reader-view-mode is-active', 'aria-pressed': 'true', 'data-view-mode': 'source', 'data-i18n': 'source_reader.mode.source' }, t('source_reader.mode.source'));
    viewGroup.appendChild(srcBtn);
    if (meta.source_path) {
      viewGroup.appendChild(el('a', { 'href': meta.source_path, 'class': 'reader-view-mode', 'data-i18n': 'source_reader.mode.raw' }, t('source_reader.mode.raw')));
    }
    var wrapBtn = el('button', { 'type': 'button', 'class': 'reader-view-mode reader-view-mode--wrap', 'data-i18n': 'source_reader.action.wrap_lines' }, t('source_reader.action.wrap_lines'));
    wrapBtn.addEventListener('click', function () {
      var pre = document.querySelector('.code-reader');
      if (!pre) return;
      var wrapped = pre.classList.toggle('is-wrapped');
      wrapBtn.textContent = wrapped ? t('source_reader.action.unwrap_lines') : t('source_reader.action.wrap_lines');
      // wrapping reflows every line — re-anchor the floating toolbar.
      if (_selection && _selection.size > 0) positionSelectionToolbar();
    });
    viewGroup.appendChild(wrapBtn);
    var copyBtn = el('button', { 'type': 'button', 'class': 'reader-view-mode reader-view-mode--copy', 'data-action': 'copy-code', 'data-i18n': 'source_reader.action.copy_code' }, t('source_reader.action.copy_code'));
    copyBtn.addEventListener('click', function () { copyCode(copyBtn); });
    viewGroup.appendChild(copyBtn);
    nav.appendChild(viewGroup);

    root.appendChild(nav);

    // ── loading placeholder ──
    root.appendChild(el('p', { 'class': 'reader-loading', 'aria-live': 'polite', 'data-i18n': 'source_reader.loading' }, t('source_reader.loading')));
  }

  // ─── Marker extraction ───────────────────────────────────────────────────
  // Two extractions, one source of truth (rawLines):
  //
  //   extractInlineMarkers — author + structural markers used as in-code
  //   editorial dividers. unified rhythm in css; both subtle, opacity differs.
  //
  //   extractCuratedMap — curated buckets (Head · Identity · Discovery · …)
  //   used for the document map and the sticky minimap. ignores noise tokens;
  //   emits one entry per bucket if a first match is found in the source.

  function extractInlineMarkers(rawLines) {
    var authorRe = /^\s*<!--\s*([^-]{1,60}?)\s*-->\s*$/;
    var structRe = /^\s*<(html|head|body|header|nav|main|article|section|footer|script|dialog|template)(\s|>|\/)/i;
    var attrIdRe = /\sid="([^"]+)"/;
    var attrClassRe = /\sclass="([^"]+)"/;

    var result = [];
    var seenStructure = {};

    for (var i = 0; i < rawLines.length; i++) {
      var raw = rawLines[i];

      var am = authorRe.exec(raw);
      if (am) {
        result.push({ label: am[1].trim(), line: i + 1, type: 'author' });
        continue;
      }

      var sm = structRe.exec(raw);
      if (sm) {
        var tag = sm[1].toLowerCase();
        var label = tag;
        var idMatch = attrIdRe.exec(raw);
        if (idMatch) {
          label = tag + '#' + idMatch[1];
        } else {
          var classMatch = attrClassRe.exec(raw);
          if (classMatch) {
            label = tag + '.' + classMatch[1].split(/\s+/)[0];
          }
        }
        if (!seenStructure[label]) {
          seenStructure[label] = true;
          result.push({ label: label, line: i + 1, type: 'structure' });
        }
      }
    }
    return result;
  }

  // Curated bucket definitions per file kind. Bucket order is the canonical
  // reading order for the document map; only buckets whose match exists in
  // the file are emitted.
  //
  // Multilingual contract:
  //   · i18n_key — looks up the bucket's display label per language. these
  //     are EDITORIAL labels (the reader's inference about the file), so
  //     they translate.
  //   · fallback — English text used when the key is missing from I18N.
  //   · Inline section dividers do NOT use these labels; they keep the raw
  //     source text (HTML tag, author comment) untranslated, because that
  //     content is canonical source — never editorial.
  var CURATED_BUCKETS = {
    html: [
      { i18n_key: 'source_reader.map_label.html',            fallback: 'HTML',            re: /<html[\s>]/i },
      { i18n_key: 'source_reader.map_label.head',            fallback: 'Head',            re: /<head[\s>]/i },
      { i18n_key: 'source_reader.map_label.identity',        fallback: 'Identity',        re: /<!--\s*identity\b|<meta\s+name="author"|<link\s+rel="author"/i },
      { i18n_key: 'source_reader.map_label.discovery',       fallback: 'Discovery',       re: /<!--\s*discovery\b|<meta\s+name="robots"|<meta\s+name="referrer"/i },
      { i18n_key: 'source_reader.map_label.social_preview',  fallback: 'Social preview',  re: /<!--\s*social\b|<meta\s+property="og:/i },
      { i18n_key: 'source_reader.map_label.assets',          fallback: 'Assets',          re: /<!--\s*assets\b|<!--\s*icons\b|<link\s+rel="stylesheet"|<link\s+rel="manifest"/i },
      { i18n_key: 'source_reader.map_label.structured_data', fallback: 'Structured data', re: /<!--\s*structured\b|application\/ld\+json/i },
      { i18n_key: 'source_reader.map_label.header',          fallback: 'Header',          re: /<header[\s>]/i },
      { i18n_key: 'source_reader.map_label.main',            fallback: 'Main',            re: /<main[\s>]/i },
      { i18n_key: 'source_reader.map_label.footer',          fallback: 'Footer',          re: /<footer[\s>]/i }
    ],
    css: [
      { i18n_key: 'source_reader.map_label.tokens',     fallback: 'Tokens',     re: /\/\*[^*]*\btokens?\b|:root\s*\{/i },
      { i18n_key: 'source_reader.map_label.fonts',      fallback: 'Fonts',      re: /@font-face|\/\*[^*]*\bfonts?\b/i },
      { i18n_key: 'source_reader.map_label.base',       fallback: 'Base',       re: /\/\*[^*]*\b(reset|base)\b/i },
      { i18n_key: 'source_reader.map_label.layout',     fallback: 'Layout',     re: /\/\*[^*]*\blayout\b/i },
      { i18n_key: 'source_reader.map_label.components', fallback: 'Components', re: /\/\*[^*]*\bcomponents?\b/i },
      { i18n_key: 'source_reader.map_label.responsive', fallback: 'Responsive', re: /@media\s*\(/i },
      { i18n_key: 'source_reader.map_label.print',      fallback: 'Print',      re: /@media\s+print|\/\*[^*]*\bprint\b/i }
    ],
    js: [
      { i18n_key: 'source_reader.map_label.state',        fallback: 'State',        re: /\/\/[^\n]*\bstate\b|\bvar\s+state\b/i },
      { i18n_key: 'source_reader.map_label.i18n',         fallback: 'i18n',         re: /\bwindow\.I18N\b|\/\/[^\n]*\bi18n\b/i },
      { i18n_key: 'source_reader.map_label.events',       fallback: 'Events',       re: /\baddEventListener\b/i },
      { i18n_key: 'source_reader.map_label.modals',       fallback: 'Modals',       re: /\b(dialog|modal|overlay)\b/i },
      { i18n_key: 'source_reader.map_label.copy',         fallback: 'Copy',         re: /\bnavigator\.clipboard\b|\bcopyCode\b|\/\/[^\n]*\bcopy\b/i },
      { i18n_key: 'source_reader.map_label.verification', fallback: 'Verification', re: /\bverif(?:y|ication)\b/i },
      { i18n_key: 'source_reader.map_label.init',         fallback: 'Init',         re: /\bDOMContentLoaded\b|function\s+init\s*\(/i }
    ],
    json: [
      { i18n_key: 'source_reader.map_label.identity',     fallback: 'Identity',     re: /"(?:identity|author|name|@id)"\s*:/i },
      { i18n_key: 'source_reader.map_label.discovery',    fallback: 'Discovery',    re: /"(?:robots|referrer|discoverable|webfinger)"\s*:/i },
      { i18n_key: 'source_reader.map_label.policy',       fallback: 'Policy',       re: /"(?:policy|privacy|security|terms)"\s*:/i },
      { i18n_key: 'source_reader.map_label.verification', fallback: 'Verification', re: /"(?:manifest|signature|fingerprint|hash|sha256|sha384)"\s*:/i },
      { i18n_key: 'source_reader.map_label.records',      fallback: 'Records',      re: /"(?:records?|releases?|edition|entries)"\s*:/i }
    ]
  };
  // Plain text and apache config reuse the json bucket set as a reasonable
  // approximation; buckets without matches simply drop out.
  CURATED_BUCKETS.text = CURATED_BUCKETS.json;
  CURATED_BUCKETS.apache = CURATED_BUCKETS.json;

  // Translate a curated bucket label at render time. Falls back through
  // English → the bucket's hard-coded fallback string so the UI never
  // goes blank if i18n is partly populated.
  function bucketLabel(entry) {
    if (!entry) return '';
    var key = entry.i18n_key;
    var resolved = key ? t(key) : '';
    if (resolved && resolved !== key) return resolved;
    return entry.fallback || '';
  }

  function extractCuratedMap(rawLines, kind) {
    var buckets = CURATED_BUCKETS[kind];
    if (!buckets) return [];
    var matched = {};
    for (var i = 0; i < rawLines.length; i++) {
      var raw = rawLines[i];
      for (var b = 0; b < buckets.length; b++) {
        var bk = buckets[b];
        if (matched[bk.i18n_key]) continue;
        if (bk.re.test(raw)) {
          matched[bk.i18n_key] = i + 1;
        }
      }
    }
    var out = [];
    for (var k = 0; k < buckets.length; k++) {
      var bk2 = buckets[k];
      if (matched[bk2.i18n_key]) {
        out.push({ entry: bk2, line: matched[bk2.i18n_key] });
      }
    }
    return out;
  }

  // ─── Document map ────────────────────────────────────────────────────────
  // quiet nav row above the code shell: "Document map · Head · Identity · …"
  // visible on narrow screens; hidden by css when minimap sidebar takes over.
  // entries are curated buckets — not a raw token dump.

  function renderDocumentMap(mapEntries, root) {
    if (!mapEntries || mapEntries.length < 2) return;
    // markup: a small label, then a wrapped list of index-term links.
    // css renders the items as printed index terms on narrow screens
    // (wrapped, baseline-ruled, no pills) and as an inline middle-dot
    // chain on wider screens before the desktop minimap takes over.
    var nav = el('nav', { 'class': 'inspection-path', 'aria-label': 'Document sections' });
    nav.appendChild(el('p', { 'class': 'inspection-path-label', 'data-i18n': 'source_reader.meta.document_map' }, t('source_reader.meta.document_map')));
    var ul = el('ul', { 'class': 'inspection-path-list' });
    for (var i = 0; i < mapEntries.length; i++) {
      var li = el('li', { 'class': 'inspection-path-item' });
      // The label carries data-i18n so the global language-switch sweep
      // re-translates it without a re-render of the reader.
      li.appendChild(el('a', {
        'href': '#L' + mapEntries[i].line,
        'class': 'inspection-path-link',
        'data-i18n': mapEntries[i].entry.i18n_key
      }, bucketLabel(mapEntries[i].entry)));
      ul.appendChild(li);
    }
    nav.appendChild(ul);
    root.appendChild(nav);
  }

  // Files above this byte threshold skip syntax highlighting and inline
  // marker extraction. The savings keep Safari calm on the very long
  // editorial review documents (~500 KB) where the cost of running
  // regex tokenizers over every line and building thousands of spans
  // is the only thing that turns the reader into a chore.
  var LARGE_FILE_BYTES = 200 * 1024;

  function splitSourceLines(text) {
    // Preserve raw-file line semantics exactly.
    // Empty file => zero lines (not one phantom blank row).
    if (text === '') return [];
    // split('\n') yields a final empty item only when source ends with \n.
    return text.split('\n');
  }

  function renderCode(text, meta, fileKey) {
    var loading = document.querySelector('.reader-loading');
    if (loading) loading.parentNode.removeChild(loading);

    // Drop any stale selection from the previously rendered file. The
    // line IDs in the new DOM are unrelated to the old set, so without
    // this cleanup the selection state survives but the visual binding
    // breaks. clearSelection is a no-op when there was nothing selected
    // (it guards its own announce), so this is safe on first render too.
    if (_selection && _selection.size > 0) clearSelection();

    var rawLines = splitSourceLines(text);
    _reader.rawLines = rawLines;
    var isLarge = text.length >= LARGE_FILE_BYTES;
    // For oversize files, keep the reader honest: render escaped source
    // line-by-line with no highlight, no dividers, no document map, no
    // collapsible controls. The integrity block above still tells the
    // reader what they are looking at; the source itself remains intact.
    // The body attribute drives css that hides the annotated toggle in
    // this mode — the brief is explicit: annotation mode must not be
    // enabled on very large files.
    if (isLarge) {
      document.body.setAttribute('data-source-large', 'true');
      // Force raw mode on large files so the (now hidden) toggle does
      // not accidentally leave the page in annotated state from a
      // previous render of a smaller file.
      document.body.setAttribute('data-source-mode', 'raw');
    } else {
      document.body.removeAttribute('data-source-large');
    }
    var htmlLines = isLarge
      ? rawLines.map(function (line) { return esc(line); })
      : tokenizeAll(text, meta.kind);

    // Inline markers — every meaningful author/structural comment becomes
    // a quiet editorial divider in-flow. These are not the document map.
    var inlineMarkers = isLarge ? [] : extractInlineMarkers(rawLines);
    var markerMap = {};
    for (var mi = 0; mi < inlineMarkers.length; mi++) {
      markerMap[inlineMarkers[mi].line - 1] = inlineMarkers[mi];
    }

    // Document map — curated buckets, dropped on oversize files so the
    // reader does not burn additional time scanning megabytes of text
    // for bucket-matching regexes.
    var mapEntries = isLarge ? [] : extractCuratedMap(rawLines, meta.kind);

    var root = document.getElementById('source-view-root');

    // Document map — a single editorial surface rendered above the code
    // on every viewport. The previous sticky desktop sidebar version
    // was a "minimap" by name, and minimaps signal IDE chrome rather
    // than an editorial publication; the inline index-terms list keeps
    // the same information in a quieter typographic register.
    if (root && mapEntries.length && document.body.getAttribute('data-source-mode') === 'annotated') renderDocumentMap(mapEntries, root);

    var layout = el('div', { 'class': 'source-reader-layout' });

    var shell = el('div', { 'class': 'code-shell' });
    // viewport-aware default: mobile wraps; desktop preserves long lines in a
    // fixed-width reader box. matches the wrap-toggle button's initial state
    // set in renderMeta() so chrome and code agree on first paint.
    var preferWrap = window.matchMedia && window.matchMedia('(max-width: 700px)').matches;
    var pre = el('pre', {
      'class': 'code-reader' + (preferWrap ? ' is-wrapped' : ''),
      'data-lang': meta.kind || '',
      'aria-label': 'Source code for ' + fileKey,
      'tabindex': '0'
    });
    var code = el('code');
    safeHTML(code, renderLines(rawLines, htmlLines, markerMap, meta.kind));
    // Internal-link rewriter: turn every routed URL inside the rendered
    // source (href="/privacy/", https://trentpower.fr/styles.css, etc.)
    // into an in-reader anchor so clicking it opens the matching source
    // mirror instead of the live page. Same-origin, manifest-gated. The
    // tokenizer is bypassed entirely for oversize files, so the linkify
    // pass also skips them — the raw escaped text contains no <span>
    // wrappers to navigate.
    if (!isLarge) linkifyRenderedLines(code);
    pre.appendChild(code);
    shell.appendChild(pre);
    layout.appendChild(shell);

    if (root) {
      root.appendChild(layout);
      mountSelectionToolbar(root);

      // closing editorial footer — seal line + edition line + view-rendered
      // link. the per-row navigation (Canonical · Verify · Raw · Top) was
      // retired: the masthead and footer carry the same affordances.
      var footer = el('footer', { 'class': 'source-reader-footer' });
      footer.appendChild(el('p', { 'class': 'footer-end', 'data-i18n': 'source_reader.end.title' }, t('source_reader.end.title')));
      var parts = [];
      if (meta.edition) parts.push(t('source_reader.end.edition') + ' ' + meta.edition);
      if (meta.sha256) parts.push(t('source_reader.end.sha256') + ' ' + meta.sha256);
      if (meta.signed_release) parts.push(t('source_reader.end.signed_release') + ' ' + meta.signed_release);
      if (parts.length) footer.appendChild(el('p', { 'class': 'footer-edition' }, parts.join(' · ')));
      root.appendChild(footer);
    }

    // handle line anchor from url hash
    scrollToAnchor();
    window.addEventListener('hashchange', scrollToAnchor);

    // optical anchoring — as the reader scrolls past each curated map
    // marker, the matching link in the inspection path and the sticky
    // minimap subtly sharpens. not a sticky toc, not a scroll-spy ui:
    // just a single .is-current class toggled with a quiet css delta
    // (opacity / colour). degrades silently if IntersectionObserver is
    // unavailable.
    if (typeof IntersectionObserver === 'function' && mapEntries.length >= 2) {
      attachOpticalAnchoring(mapEntries);
    }

    // the mobile sticky "view rendered page ↗" strip used to surface
    // here was retired: the footer link below the closure row carries
    // the same affordance with calmer rhythm and lower noise.
  }

  function attachOpticalAnchoring(mapEntries) {
    var lineEls = [];
    var entryByLine = {};
    for (var i = 0; i < mapEntries.length; i++) {
      var line = mapEntries[i].line;
      var el2 = document.getElementById('L' + line);
      if (!el2) continue;
      lineEls.push(el2);
      entryByLine[line] = mapEntries[i];
    }
    if (!lineEls.length) return;

    var links = document.querySelectorAll('.inspection-path-link, .minimap-link');
    function setCurrentLine(line) {
      for (var k = 0; k < links.length; k++) {
        var hash = links[k].getAttribute('href') || '';
        links[k].classList.toggle('is-current', hash === '#L' + line);
      }
    }

    // top edge of the visible code column; anything above this line that is
    // also the last marker passed becomes "current". rootMargin biases the
    // intersection so the marker activates before it touches the top edge.
    var lastLine = null;
    var observer = new IntersectionObserver(function (_entries) {
      // pick the largest line number whose marker has crossed above the
      // viewport top. this keeps the active state monotonic during scroll.
      var visibleAbove = null;
      for (var i = 0; i < lineEls.length; i++) {
        var rect = lineEls[i].getBoundingClientRect();
        var lineNum = parseInt(lineEls[i].id.slice(1), 10);
        if (rect.top <= 96) {
          if (visibleAbove === null || lineNum > visibleAbove) visibleAbove = lineNum;
        }
      }
      if (visibleAbove === null) visibleAbove = parseInt(lineEls[0].id.slice(1), 10);
      if (visibleAbove !== lastLine) {
        lastLine = visibleAbove;
        setCurrentLine(visibleAbove);
      }
    }, { rootMargin: '-96px 0px -60% 0px', threshold: 0 });

    for (var j = 0; j < lineEls.length; j++) observer.observe(lineEls[j]);
    // seed initial active state so the first marker reads as current
    // before any scroll happens.
    setCurrentLine(parseInt(lineEls[0].id.slice(1), 10));
  }

  function renderError(_err) {
    var loading = document.querySelector('.reader-loading');
    if (loading) loading.parentNode.removeChild(loading);
    var root = document.getElementById('source-view-root');
    if (!root) return;
    var msg = el('p', { 'class': 'reader-error' }, 'Could not load source file. Try the raw link above.');
    root.appendChild(msg);
  }

  // Replace any existing dynamic link relations from a prior render
  // (the toggle between file views is a SPA-style change) and add the
  // canonical / alternate / up / version-history relations the
  // publication system declares. Static <link> tags placed in the
  // shell at build time are left untouched if they share a rel.
  function injectCanonicalLinks(meta, fileKey) {
    if (!document.head) return;
    function setLink(rel, href, attrs) {
      // remove any previous dynamic link we placed (data-source-view-link
      // is the marker; pre-existing shell links without it are preserved).
      var existing = document.head.querySelectorAll('link[data-source-view-link="' + rel + '"]');
      for (var i = 0; i < existing.length; i++) existing[i].parentNode.removeChild(existing[i]);
      if (!href) return;
      var lnk = document.createElement('link');
      lnk.setAttribute('rel', rel);
      lnk.setAttribute('href', href);
      lnk.setAttribute('data-source-view-link', rel);
      if (attrs) for (var k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k)) lnk.setAttribute(k, attrs[k]);
      }
      document.head.appendChild(lnk);
    }
    var base = location.origin + '/source/view/';
    var canonRoute = canonicalPathFor(meta.live_path || '');
    var pathQs = canonRoute ? ('?path=' + encodeURIComponent(canonRoute)) : ('?file=' + encodeURIComponent(fileKey));
    // canonical points at THIS file view (not the catalogue), so
    // citation tooling can quote a stable url per source file. uses the
    // clean ?path= form when the manifest carries a live_path; legacy
    // ?file= form is the fallback for entries without one.
    setLink('canonical',       base + pathQs);
    // plain-text alternate is the .txt mirror — the literal canonical
    // bytes, served as text/plain.
    setLink('alternate',       meta.source_path || '', { 'type': 'text/plain' });
    // parent / catalogue surface.
    setLink('up',              '/source/');
    // version history — each edition is a signed release in /integrity/.
    setLink('version-history', '/integrity/releases/');
  }

  function renderUnknown(fileKey) {
    var root = document.getElementById('source-view-root');
    if (!root) return;
    while (root.firstChild) root.removeChild(root.firstChild);
    var notice = el('section', { 'class': 'reader-unknown' });
    notice.appendChild(el('h1', { 'class': 'page-title' }, 'Source reader'));
    notice.appendChild(el('p', {}, fileKey ? 'File not found in source manifest: ' + fileKey : 'No file specified.'));
    notice.appendChild(el('a', { 'href': '/source/' }, 'View source catalogue'));
    root.appendChild(notice);
  }

  // ─── Utilities ────────────────────────────────────────────────────────────

  // Focus-line state — the parchment highlight is interpretive, not
  // canonical, so it never persists in the DOM longer than needed. A
  // 2s fade replaces the full highlight with a quiet persistent marker
  // (a hairline rule on the gutter side) so the reader can still locate
  // the cited range after returning from another tab without the page
  // shouting at them.
  var _focusFadeTimer = null;
  var _selectionStart = null;
  var _selection = (typeof Set === 'function') ? new Set() : null;
  var _toolbarEl = null;
  // phase 96 · cached reference to the empty <style id="sv-dyn"> sheet
  // used for cssom-mutated toolbar positioning. populated lazily on
  // first use so the template doesn't need it earlier.
  var _dynSheet = null;
  var _announcerEl = null;
  // tracked at pointerdown so the click handler knows whether the user
  // tapped with a finger (no shift key available, expect tap-tap range)
  // or clicked with a mouse (shift / ctrl / cmd modifiers reachable).
  var _inputMode = 'mouse';

  function _selectionList() {
    if (!_selection) return [];
    var arr = [];
    _selection.forEach(function (n) { arr.push(n); });
    arr.sort(function (a, b) { return a - b; });
    return arr;
  }
  function _selectionMin() {
    var list = _selectionList();
    return list.length ? list[0] : 0;
  }
  function _selectionMax() {
    var list = _selectionList();
    return list.length ? list[list.length - 1] : 0;
  }
  function _selectionIsContiguous() {
    var list = _selectionList();
    if (list.length < 2) return true;
    return (list[list.length - 1] - list[0]) === (list.length - 1);
  }

  function clearFocusState() {
    var hi = document.querySelectorAll('.code-line--range-active, .code-line--range-marked');
    for (var i = 0; i < hi.length; i++) {
      hi[i].classList.remove('code-line--range-active');
      hi[i].classList.remove('code-line--range-marked');
    }
    var pressed = document.querySelectorAll('.line-number[aria-pressed="true"]');
    for (var j = 0; j < pressed.length; j++) {
      pressed[j].setAttribute('aria-pressed', 'false');
    }
    if (_focusFadeTimer) { clearTimeout(_focusFadeTimer); _focusFadeTimer = null; }
  }

  function scheduleFocusFade(rangeEls) {
    _focusFadeTimer = setTimeout(function () {
      for (var i = 0; i < rangeEls.length; i++) {
        rangeEls[i].classList.remove('code-line--range-active');
        rangeEls[i].classList.add('code-line--range-marked');
      }
      _focusFadeTimer = null;
    }, 2000);
  }

  function scrollToAnchor() {
    var hash = location.hash;
    if (!hash) return;

    // single line: #L12 — soft parchment highlight + auto-scroll + fade.
    if (/^#L\d+$/.test(hash)) {
      clearFocusState();
      var target = document.querySelector(hash);
      if (target) {
        target.classList.add('code-line--range-active');
        setTimeout(function () { target.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, 50);
        scheduleFocusFade([target]);
      }
      return;
    }

    // range: #L12-L24 — highlights the range and scrolls to the first line.
    // After 2s the warm highlight collapses to a quiet gutter rule so the
    // citation is still locatable without the page shouting.
    var rangeMatch = /^#L(\d+)-L(\d+)$/.exec(hash);
    if (rangeMatch) {
      var from = parseInt(rangeMatch[1], 10);
      var to   = parseInt(rangeMatch[2], 10);
      if (from > to) { var tmp = from; from = to; to = tmp; }
      setTimeout(function () {
        clearFocusState();
        var lines = [];
        for (var ln = from; ln <= to; ln++) {
          var line = document.getElementById('L' + ln);
          if (line) {
            line.classList.add('code-line--range-active');
            lines.push(line);
          }
        }
        var first = document.getElementById('L' + from);
        if (first) first.scrollIntoView({ block: 'center', behavior: 'smooth' });
        scheduleFocusFade(lines);
      }, 50);
    }
  }

  function copyCode(btn) {
    var lines = document.querySelectorAll('.line-code');
    var text = Array.prototype.map.call(lines, function (l) { return l.textContent; }).join('\n');
    writeClipboard(text).then(function () {
      btn.textContent = t('source_reader.action.copied');
      btn.disabled = true;
      setTimeout(function () { btn.textContent = t('source_reader.action.copy_code'); btn.disabled = false; }, 1500);
      announce(t('source_reader.action.copied'));
    }).catch(function () {
      announce(t('source_reader.action.copy_failed'));
    });
  }

  function kindFullName(kind) {
    // i18n key first; the english map is the fallback when no
    // translation is provided.
    var key = 'source_reader.kind.' + kind;
    var translated = t(key);
    if (translated && translated !== key) return translated;
    var map = { html: 'HyperText Markup Language', css: 'Cascading Style Sheets', js: 'JavaScript', json: 'JavaScript Object Notation', text: 'Plain text', apache: 'Apache configuration' };
    return map[kind] || kind;
  }

  function formatDate(iso) {
    if (!iso) return '';
    // browser-native localisation via Intl.DateTimeFormat picks up the
    // active document language and emits the right month name (mai
    // vs may, etc.) without per-locale month tables in this file.
    try {
      var lang = document.documentElement.getAttribute('data-lang') ||
                 document.documentElement.lang || 'en';
      // parse yyyy-mm-dd as a local date — calling new Date('2026-05-09')
      // is utc in some engines and produces an off-by-one for the
      // visible day, so split first.
      var parts = iso.split('-');
      if (parts.length !== 3) return iso;
      var dt = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
      if (isNaN(dt.getTime())) return iso;
      return new Intl.DateTimeFormat(lang, { day: 'numeric', month: 'short', year: 'numeric' }).format(dt);
    } catch (_) {
      return iso;
    }
  }

  // ─── Init ─────────────────────────────────────────────────────────────────

  function init() {
    var qs = new URLSearchParams(location.search);
    var pathParam = qs.get('path');
    var fileKey = qs.get('file');
    var incomingHash = location.hash || '';

    // Resolve the request via either the new ?path= form (canonical
    // live route) or the legacy ?file= form (raw mirror name). The new
    // form is the user-facing one; the legacy form is accepted on
    // arrival and the URL is replaced in place so the .txt extension
    // never persists in the address bar.
    var resolvedKey = '';
    var resolvedPath = '';
    if (pathParam) {
      // ?path=/privacy/ → look up via the canonical-route reverse index.
      var key = MANIFEST_BY_PATH[pathParam];
      if (!key) {
        // tolerate a missing trailing slash (e.g. /privacy → /privacy/)
        if (pathParam.charAt(pathParam.length - 1) !== '/' && MANIFEST_BY_PATH[pathParam + '/']) {
          resolvedPath = pathParam + '/';
          key = MANIFEST_BY_PATH[resolvedPath];
        }
      } else {
        resolvedPath = pathParam;
      }
      resolvedKey = key || '';
    }
    if (!resolvedKey && fileKey) {
      // legacy: ?file=index.html.txt or ?file=index.html. resolve to
      // the manifest entry by raw mirror name, then derive the canonical
      // route from its live_path so the URL can be replaced cleanly.
      var legacyDisplay = fileKey.replace(/\.txt$/, '');
      var entry = MANIFEST[fileKey] || MANIFEST[legacyDisplay] || MANIFEST[legacyDisplay + '.txt'];
      if (entry && entry.live_path) {
        resolvedKey  = MANIFEST_BY_PATH[entry.live_path] || legacyDisplay + '.txt';
        resolvedPath = canonicalPathFor(entry.live_path);
      }
    }
    if (!resolvedKey) {
      if (!pathParam && !fileKey) { renderUnknown(null); return; }
      renderUnknown(pathParam || fileKey);
      return;
    }

    var meta = MANIFEST[resolvedKey];
    if (!meta) { renderUnknown(pathParam || fileKey); return; }

    // Canonicalise the URL in place: ?path=<encoded live route>. The
    // legacy ?file= form is accepted but never persisted.
    var canonicalQs = '?path=' + encodeURIComponent(resolvedPath || canonicalPathFor(meta.live_path));
    var canonicalUrl = location.pathname + canonicalQs + incomingHash;
    if ((location.search || '') !== canonicalQs) {
      history.replaceState(null, '', canonicalUrl);
    }

    fileKey = resolvedKey;
    _reader.fileKey  = resolvedKey;
    _reader.livePath = meta.live_path || '';
    _reader.pathQuery = canonicalPathFor(meta.live_path);

    // Canonical permanence — this file is not just a source viewer hit,
    // it is a public archival surface. Expose the publication's link
    // relations so feed readers, archives, and downstream citation tools
    // can resolve every level of the publication system at the page
    // level (canonical url for this specific file view, plain-text
    // alternate, parent catalogue, and version history).
    injectCanonicalLinks(meta, fileKey);

    renderMeta(meta, fileKey);

    fetch(meta.source_path)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(function (text) { renderCode(text, meta, fileKey); })
      .catch(function (err) { renderError(err); });
  }

  // Boot sequence — init() runs once the DOM is ready: immediately if
  // parsing is already complete, otherwise on DOMContentLoaded.
  function announce(msg) {
    if (!_announcerEl) return;
    _announcerEl.textContent = msg || '';
  }

  // Compute the live-region message that describes the current selection
  // state. Called from selectSingle / toggleLine / extendRange so screen-
  // reader users hear the result of every selection change, not only the
  // post-copy / post-clear actions.
  function announceSelectionState() {
    if (!_selection || _selection.size === 0) {
      announce(t('source_reader.action.selection_cleared'));
      return;
    }
    var list = _selectionList();
    if (list.length === 1) {
      announce(tf('source_reader.action.line_selected', { n: list[0] }));
      return;
    }
    if (_selectionIsContiguous()) {
      announce(tf('source_reader.action.range_selected', { start: list[0], end: list[list.length - 1] }));
      return;
    }
    announce(tf('source_reader.action.count_lines_many', { n: list.length }));
  }

  // Strip the #Lxx fragment without reloading. We replace the URL via
  // history.replaceState so the address bar reflects the live selection
  // for contiguous ranges, and never carries a fragment for non-
  // contiguous selections (no standard syntax for those).
  function setHashForSelection() {
    var list = _selectionList();
    var path = location.pathname + location.search;
    if (!list.length) {
      history.replaceState(null, '', path);
      return;
    }
    if (_selectionIsContiguous()) {
      var lo = list[0], hi = list[list.length - 1];
      var hash = (hi === lo) ? ('#L' + lo) : ('#L' + lo + '-L' + hi);
      history.replaceState(null, '', path + hash);
      return;
    }
    history.replaceState(null, '', path);
  }

  function renderSelectionVisual() {
    // wipe prior active/marked + aria-pressed
    var prev = document.querySelectorAll('.code-line--range-active, .code-line--range-marked');
    for (var i = 0; i < prev.length; i++) {
      prev[i].classList.remove('code-line--range-active');
      prev[i].classList.remove('code-line--range-marked');
    }
    var pressed = document.querySelectorAll('.line-number[aria-pressed="true"]');
    for (var p = 0; p < pressed.length; p++) {
      pressed[p].setAttribute('aria-pressed', 'false');
    }
    if (_focusFadeTimer) { clearTimeout(_focusFadeTimer); _focusFadeTimer = null; }
    // self-heal: if the toolbar element wasn't found during the initial
    // ensureSelectionToolbar() call (e.g. a race between attachLine-
    // RangeSelection() and the DOM having #source-toolbar ready), try
    // again now — by the time the user has interacted enough to
    // trigger renderSelectionVisual(), the toolbar is definitely in
    // the DOM. fixes the "tap a line, line highlights, but the floating
    // toolbar never appears" regression on iphone + desktop.
    if (!_toolbarEl) ensureSelectionToolbar();
    if (!_selection || _selection.size === 0) {
      if (_toolbarEl) _toolbarEl.classList.remove('is-visible');
      return;
    }
    var list = _selectionList();
    for (var k = 0; k < list.length; k++) {
      var line = document.getElementById('L' + list[k]);
      if (line) line.classList.add('code-line--range-active');
      var num = line && line.querySelector('.line-number');
      if (num) num.setAttribute('aria-pressed', 'true');
    }
    if (_toolbarEl) {
      var count = _toolbarEl.querySelector('.source-toolbar__count');
      if (count) {
        count.textContent = (list.length === 1)
          ? t('source_reader.action.count_line_one')
          : tf('source_reader.action.count_lines_many', { n: list.length });
      }
      // reveal first (so the bar is measurable), then anchor it.
      _toolbarEl.classList.add('is-visible');
      positionSelectionToolbar();
    }
  }

  // Smallest contiguous range containing the current selection. Returns
  // null when no selection is present.
  function containingRange() {
    if (!_selection || _selection.size === 0) return null;
    return { from: _selectionMin(), to: _selectionMax() };
  }

  // brief visual confirmation on the pressed action — a burgundy flash
  // (CSS .is-copied) held for ~1.4s. one shared timer; a fresh copy
  // cancels the previous flash so the cue never stacks.
  var _copiedTimer = 0;
  function flashCopied(btn) {
    if (!btn) return;
    if (_copiedTimer) { clearTimeout(_copiedTimer); _copiedTimer = 0; }
    var prev = document.querySelector('.source-toolbar__btn.is-copied');
    if (prev) prev.classList.remove('is-copied');
    btn.classList.add('is-copied');
    _copiedTimer = setTimeout(function () {
      btn.classList.remove('is-copied');
      _copiedTimer = 0;
    }, 1400);
  }

  function copySelectedSourceText(btn) {
    if (!_selection || _selection.size === 0) return;
    var list = _selectionList();
    var parts = [];
    for (var i = 0; i < list.length; i++) {
      parts.push(_reader.rawLines[list[i] - 1] || '');
    }
    var text = parts.join('\n');
    writeClipboard(text).then(function () {
      announce(tf('source_reader.action.lines_copied', { n: list.length }));
      flashCopied(btn);
    }).catch(function () {
      announce(t('source_reader.action.copy_failed'));
    });
  }

  function copySelectionLink(btn) {
    if (!_selection || _selection.size === 0) return;
    var range = containingRange();
    var hash = (range.from === range.to)
      ? ('#L' + range.from)
      : ('#L' + range.from + '-L' + range.to);
    var url = location.origin + location.pathname + location.search + hash;
    var normalised = !_selectionIsContiguous();
    writeClipboard(url).then(function () {
      announce(normalised
        ? tf('source_reader.action.link_copied_normalised', { start: range.from, end: range.to })
        : t('source_reader.action.link_copied'));
      flashCopied(btn);
    }).catch(function () {
      announce(t('source_reader.action.copy_failed'));
    });
  }

  function clearSelection() {
    var had = _selection && _selection.size > 0;
    if (_selection) _selection.clear();
    _selectionStart = null;
    setHashForSelection();
    renderSelectionVisual();
    if (had) announce(t('source_reader.action.selection_cleared'));
  }

  function selectSingle(line) {
    if (!_selection) return;
    _selection.clear();
    _selection.add(line);
    _selectionStart = line;
    setHashForSelection();
    renderSelectionVisual();
    announceSelectionState();
    var target = document.getElementById('L' + line);
    if (target) target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function extendRange(line) {
    if (!_selection) return;
    if (_selectionStart == null) { selectSingle(line); return; }
    _selection.clear();
    var lo = Math.min(_selectionStart, line);
    var hi = Math.max(_selectionStart, line);
    for (var i = lo; i <= hi; i++) _selection.add(i);
    setHashForSelection();
    renderSelectionVisual();
    announceSelectionState();
  }

  function toggleLine(line) {
    if (!_selection) return;
    if (_selection.has(line)) _selection.delete(line);
    else _selection.add(line);
    _selectionStart = line;
    setHashForSelection();
    renderSelectionVisual();
    announceSelectionState();
  }

  function ensureSelectionToolbar() {
    if (_toolbarEl) return;
    var bar = document.getElementById('source-toolbar');
    if (!bar) return;
    _toolbarEl = bar;
    bar.addEventListener('click', function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest('button[data-action]') : null;
      if (!btn) return;
      var action = btn.getAttribute('data-action');
      if (action === 'copy')      copySelectedSourceText(btn);
      else if (action === 'copy-link') copySelectionLink(btn);
      else if (action === 'clear')     clearSelection();
    });
  }

  // The selection toolbar is a contextual floating bar. Mount it once
  // as an absolutely-positioned child of the source frame so it can
  // float over the code; positionSelectionToolbar() anchors it on each
  // selection. CSS keeps it display:none until .is-visible is added.
  function mountSelectionToolbar(root) {
    ensureSelectionToolbar();
    if (root && _toolbarEl) {
      root.appendChild(_toolbarEl);
    }
  }

  // Anchor the floating toolbar just above the first selected line,
  // inside the source frame. The toolbar is position: absolute within
  // #source-view-root, so it scrolls with the code — no scroll handler.
  // Mobile (<=720px) uses a CSS fixed bottom bar, so the calc is skipped.
  function positionSelectionToolbar() {
    if (!_toolbarEl || !_selection || _selection.size === 0) return;
    if (window.matchMedia && window.matchMedia('(max-width: 720px)').matches) return;
    var frame = document.getElementById('source-view-root');
    var first = document.getElementById('L' + _selectionMin());
    if (!frame || !first) return;
    var fRect = frame.getBoundingClientRect();
    var lRect = first.getBoundingClientRect();
    var th = _toolbarEl.offsetHeight;
    var tw = _toolbarEl.offsetWidth;
    var top = (lRect.top - fRect.top) - th - 8;
    if (top < 0) top = 0;
    var maxTop = frame.scrollHeight - th;
    if (top > maxTop) top = maxTop;
    var left = lRect.left - fRect.left;
    var maxLeft = frame.clientWidth - tw;
    if (left > maxLeft) left = maxLeft;
    if (left < 0) left = 0;
    // phase 96 · cssom mutation instead of inline element.style.setProperty
    // (which violates csp style-src-attr 'none'). the empty <style id="sv-dyn">
    // element ships in source-view.html and is whitelisted in
    // CSP_INLINE_STYLE_HASHES_SOURCE_VIEW_DELTA; insertRule writes a
    // single #source-toolbar rule with the per-frame --st-top / --st-left
    // values. browsers don't recheck csp on cssom updates, so the empty-
    // string hash continues to match for the lifetime of the page.
    var sheet = _dynSheet || (_dynSheet = (function () {
      var el = document.getElementById('sv-dyn');
      return el ? el.sheet : null;
    })());
    if (sheet) {
      var rule = '#source-toolbar{--st-top:' + top + 'px;--st-left:' + left + 'px}';
      try {
        if (sheet.cssRules.length > 0) sheet.deleteRule(0);
        sheet.insertRule(rule, 0);
      } catch (_) { /* readonly sheet · skip */ }
    }
  }

  function attachLineRangeSelection() {
    ensureSelectionToolbar();
    _announcerEl = document.getElementById('source-announcer');

    // re-anchor the floating toolbar when the viewport reflows, so it
    // tracks the first selected line across resize / orientation change.
    var _resizeRaf = 0;
    window.addEventListener('resize', function () {
      if (_resizeRaf) return;
      _resizeRaf = (window.requestAnimationFrame || window.setTimeout)(function () {
        _resizeRaf = 0;
        if (_selection && _selection.size > 0) positionSelectionToolbar();
      });
    });

    // input-mode tracker — captured BEFORE click so the handler below
    // can branch on whether this came from a finger (no shift key) or
    // a mouse (modifier keys reachable). passive + capture so it never
    // interferes with scroll on touch.
    document.addEventListener('pointerdown', function (ev) {
      if (ev.pointerType === 'touch') _inputMode = 'touch';
      else if (ev.pointerType === 'mouse' || ev.pointerType === 'pen') _inputMode = 'mouse';
    }, { passive: true, capture: true });

    document.addEventListener('click', function (ev) {
      var a = ev.target && ev.target.closest ? ev.target.closest('.line-number') : null;
      if (a) {
        var m = /^#L(\d+)$/.exec(a.getAttribute('href') || '');
        if (!m) return;
        ev.preventDefault();
        var line = parseInt(m[1], 10);
        if (_inputMode === 'touch') {
          // tap-tap range model: first tap sets anchor; second tap on
          // a different row extends to a range; subsequent tap resets
          // to a new single-line anchor at that row; tapping the lone
          // selected row a second time clears (mirrors desktop quiet
          // toggle).
          if (!_selection || _selection.size === 0) { selectSingle(line); return; }
          if (_selection.size === 1 && _selection.has(line)) { clearSelection(); return; }
          if (_selection.size === 1) { extendRange(line); return; }
          selectSingle(line);
          return;
        }
        if (ev.shiftKey) { extendRange(line); return; }
        if (ev.metaKey || ev.ctrlKey) { toggleLine(line); return; }
        // single click on the currently sole-selected line clears it —
        // a quiet toggle gesture that keeps the address bar honest.
        if (_selection && _selection.size === 1 && _selection.has(line)) {
          clearSelection();
          return;
        }
        selectSingle(line);
        return;
      }

      // touch-only whole-row fallback: a finger doesn't have to land on
      // the small line-number anchor. desktop preserves the tight click
      // target so mouse users can still drag-select code text within a
      // row for ad-hoc copying.
      if (_inputMode === 'touch') {
        var row = ev.target && ev.target.closest ? ev.target.closest('.code-line') : null;
        if (row && row.id) {
          var rm = /^L(\d+)$/.exec(row.id);
          if (rm) {
            ev.preventDefault();
            var rowLine = parseInt(rm[1], 10);
            if (!_selection || _selection.size === 0) { selectSingle(rowLine); return; }
            if (_selection.size === 1 && _selection.has(rowLine)) { clearSelection(); return; }
            if (_selection.size === 1) { extendRange(rowLine); return; }
            selectSingle(rowLine);
            return;
          }
        }
      }

      // Click on empty area inside the code pane (not on a line, not on
      // a control) clears the selection. The toolbar absorbs its own
      // clicks via stopPropagation in ensureSelectionToolbar.
      if (_toolbarEl && _toolbarEl.contains(ev.target)) return;
      var pane = ev.target && ev.target.closest ? ev.target.closest('.code-shell, .code-reader') : null;
      if (pane && !ev.target.closest('.line-code')) {
        if (_selection && _selection.size > 0) clearSelection();
      }
    });

    document.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape') return;
      if (!_selection || _selection.size === 0) return;
      clearSelection();
    });
  }

  // ─── Internal link rewriter ───────────────────────────────────────────
  // Post-tokenization pass. Walks every .line-code text node and, when a
  // URL substring resolves to a manifest entry, splits the text node into
  // (prefix, <a class="source-link">, suffix). Never uses innerHTML;
  // never emits a link for external / mailto / tel / javascript URLs.
  function linkifyRenderedLines(scope) {
    if (!MANIFEST_BY_PATH) return;
    var root = scope || document;
    var codes = root.querySelectorAll('.line-code');
    var urlRe = /(["'])(\/(?!\/)[^"'\s<>]*)\1|(?:^|[\s(>])(\/(?!\/)[^\s"'<>)]{1,256})|https:\/\/trentpower\.fr(\/[^\s"'<>)]{0,256})/g;
    for (var i = 0; i < codes.length; i++) {
      linkifyOne(codes[i], urlRe);
    }
  }

  function resolveCandidatePath(raw) {
    if (!raw) return '';
    // strip query + fragment, normalise — manifest holds bare paths.
    var clean = raw.replace(/[#?].*$/, '');
    // exact match on either canonical-route or raw live_path
    if (MANIFEST_BY_PATH[clean]) return clean;
    // a route like /privacy without trailing slash should still resolve
    if (clean && clean.charAt(clean.length - 1) !== '/') {
      if (MANIFEST_BY_PATH[clean + '/']) return clean + '/';
    }
    return '';
  }

  function linkifyOne(codeEl, _urlRe) {
    var nodes = [];
    var walker = document.createTreeWalker(codeEl, NodeFilter.SHOW_TEXT, null);
    var n; while ((n = walker.nextNode())) nodes.push(n);
    for (var i = 0; i < nodes.length; i++) {
      linkifyTextNode(nodes[i]);
    }
  }

  function linkifyTextNode(node) {
    var text = node.nodeValue;
    if (!text) return;
    // quick reject — avoid the regex cost on plain code text.
    if (text.indexOf('/') === -1 && text.indexOf('http') === -1) return;
    // two shapes only:
    //   1. quoted "…/path…" or '…/path…' (the post-tokenizer shape of
    //      every html href / src / json url / css url(…) value).
    //   2. absolute https://trentpower.fr/… (rare in code, present in
    //      some json + meta tags).
    // bare /path-at-word-boundary is not handled — it pulls in too many
    // false positives (regex literals, integer division, comments) and
    // its real-world payoff is small because the tokenizer already
    // wraps source paths in string spans.
    var re = /(["'])(\/(?!\/)[^"'\s<>]+)\1|(\bhttps:\/\/trentpower\.fr)(\/[^\s"'<>)]*)/g;
    var out = [];
    var last = 0;
    var m;
    while ((m = re.exec(text)) !== null) {
      var matchStart = m.index;
      var matchEnd   = re.lastIndex;
      var candidate, anchorText, anchorStart, anchorEnd;
      if (m[2]) {
        // quoted form: link the path body, leave the surrounding quotes.
        candidate   = m[2];
        anchorText  = m[2];
        anchorStart = matchStart + 1;
        anchorEnd   = matchEnd - 1;
      } else if (m[4]) {
        candidate   = m[4];
        anchorText  = m[3] + m[4];
        anchorStart = matchStart;
        anchorEnd   = matchEnd;
      } else {
        continue;
      }
      if (/^\/\//.test(candidate)) continue;
      var resolved = resolveCandidatePath(candidate);
      if (!resolved) continue;
      if (anchorStart > last) out.push(document.createTextNode(text.slice(last, anchorStart)));
      var a = document.createElement('a');
      a.setAttribute('href', '/source/view/?path=' + encodeURIComponent(resolved));
      a.setAttribute('class', 'source-link');
      a.setAttribute('title', 'view source mirror');
      a.textContent = anchorText;
      out.push(a);
      last = anchorEnd;
    }
    if (!out.length) return;
    if (last < text.length) out.push(document.createTextNode(text.slice(last)));
    var parent = node.parentNode;
    if (!parent) return;
    for (var i = 0; i < out.length; i++) parent.insertBefore(out[i], node);
    parent.removeChild(node);
  }

  function boot() {
    attachLineRangeSelection();
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }
  boot();
})();
