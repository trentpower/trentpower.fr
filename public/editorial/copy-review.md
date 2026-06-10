# Copy review — English

> Edit YAML in `content/en/`. The English copy register is regenerated from these YAMLs on every build; never edit the register directly.

---

## 1. Shared copy — edit here once, used across the site

### Shared · `site`

Reference these from page YAMLs as `{{ shared.site.KEY }}`.

| Key | Value |
|---|---|
| `shared.site.name` | trentpower.fr |
| `shared.site.location` | Paris, France |
| `shared.site.proof_line` | Private · Static · Signed · No tracking |
| `shared.site.edition_label` | Edition |

### Shared · `verification`

Reference these from page YAMLs as `{{ shared.verification.KEY }}`.

| Key | Value |
|---|---|
| `shared.verification.manifest` | Signed manifest |
| `shared.verification.signature` | Detached signature |
| `shared.verification.public_key` | Public key |
| `shared.verification.source_mirror` | Source mirror |
| `shared.verification.page_fingerprint` | Page fingerprint |
| `shared.verification.canonical_url` | Canonical URL |

### Shared · `actions`

Reference these from page YAMLs as `{{ shared.actions.KEY }}`.

| Key | Value |
|---|---|
| `shared.actions.copy` | Copy |
| `shared.actions.copied` | Copied |
| `shared.actions.close` | Close |
| `shared.actions.view_source` | View source |
| `shared.actions.verify_page` | Verify this page |
| `shared.actions.print_profile` | Print profile |

### Site chrome · `footer`

Emitted directly to `en.footer` in `strings.json`.

| Key | Value |
|---|---|
| `footer.privacy` | Privacy |
| `footer.lang_toggle` | FR |
| `footer.location` | Paris, France |
| `footer.verify` | Verify |
| `footer.theme.light` | Light |
| `footer.theme.auto` | Auto |
| `footer.theme.dark` | Dark |
| `footer.proof.edition` | Edition |
| `footer.proof.signed` | Signed |
| `footer.proof.manifest_link` | Integrity manifest |
| `footer.proof.last_verified` | Verified |
| `footer.proof.sha_title` | View this page's entry in the signed integrity manifest |
| `footer.proof.relative.today` | today |
| `footer.proof.relative.yesterday` | yesterday |
| `footer.proof.relative.days` | {n} days ago |
| `footer.proof.relative.months` | {n} months ago |
| `footer.proof.relative.years` | {n} years ago |
| `footer.provenance.line` | Machine-translated from the English original. |

### Site chrome · `modal`

Emitted directly to `en.modal` in `strings.json`.

| Key | Value |
|---|---|
| `modal.text` | This is a personal project. If you'd like to see it, I'd be happy to share access. |
| `modal.cta_aria` | Request access by email |
| `modal.close` | Close |
| `modal.cta_label` | Access by request |

### Site chrome · `cite`

Emitted directly to `en.cite` in `strings.json`.

| Key | Value |
|---|---|
| `cite.hover` | Copy citation |
| `cite.copied` | Copied |
| `cite.site_label` | Personal Site |
| `cite.edition_label` | Edition |
| `cite.label.action` | Cite & verify |
| `cite.overlay.kicker` | This page |
| `cite.overlay.lede` | Canonical publication record. |
| `cite.overlay.action.copy_citation` | Copy citation |
| `cite.overlay.action.verify` | Verify this page |
| `cite.overlay.action.open_source` | View source |
| `cite.overlay.action.view_integrity` | View integrity record |
| `cite.overlay.action.print_home` | Print profile |
| `cite.overlay.action.print_sheet` | Print profile |
| `cite.overlay.action.print_page` | Print profile |
| `cite.overlay.action.close` | Close |
| `cite.overlay.page_title.home` | Client Strategy & Growth Systems |
| `cite.overlay.page_title.privacy` | Privacy statement |
| `cite.overlay.page_title.security` | Security posture |
| `cite.overlay.page_title.integrity` | Integrity record |
| `cite.overlay.page_title.verify` | Verify page |
| `cite.overlay.page_title.source` | Source reader |
| `cite.overlay.page_title.source-reader` | Source reader |
| `cite.overlay.page_title.acknowledgments` | Security acknowledgements |
| `cite.overlay.page_title.integrity-verify-locally` | Verify locally |
| `cite.overlay.page_title.releases` | Release archive |
| `cite.overlay.page_title.release-archive` | Release archive · 2026-05-09 |
| `cite.overlay.page_title.forbidden` | Access not available |
| `cite.overlay.page_title.not-found` | Page not found |
| `cite.overlay.page_title.server-error` | Temporary server error |
| `cite.overlay.page_title.maintenance` | Down for maintenance |
| `cite.overlay.page_title.sw-reset` | Service worker reset |
| `cite.overlay.toast.citation_copied` | Citation copied |
| `cite.overlay.footer_signed` | Edition {edition} · Signed SHA256 |

### Site chrome · `copy`

Emitted directly to `en.copy` in `strings.json`.

| Key | Value |
|---|---|
| `copy.command` | Copy command |
| `copy.copied` | Copied |
| `copy.failed` | Copy failed |

### Site chrome · `trust_routes`

Emitted directly to `en.trust_routes` in `strings.json`.

| Key | Value |
|---|---|
| `trust_routes.heading` | Trust routes |
| `trust_routes.privacy_label` | Privacy |
| `trust_routes.privacy_desc` | What this site does not collect |
| `trust_routes.security_label` | Security |
| `trust_routes.security_desc` | How the site is protected |
| `trust_routes.integrity_label` | Integrity |
| `trust_routes.integrity_desc` | How releases are signed |
| `trust_routes.verify_label` | Verify |
| `trust_routes.verify_desc` | How a page can be checked |
| `trust_routes.source_label` | Source |
| `trust_routes.source_desc` | Readable mirrors of public files |
| `trust_routes.releases_label` | Releases |
| `trust_routes.releases_desc` | Frozen signed snapshots |

### Site chrome · `linkdesc`

Emitted directly to `en.linkdesc` in `strings.json`.

| Key | Value |
|---|---|
| `linkdesc.home` | Return to the homepage |
| `linkdesc.privacy` | Read how this site avoids analytics, cookies, profiling, tracking, and third-party assets |
| `linkdesc.cite` | Open citation and verification details for this page |
| `linkdesc.integrity` | Open the public integrity record, including hashes, signatures, and release verification |
| `linkdesc.linkedin` | Open Trent Power’s LinkedIn profile in a new tab without sending referrer data |
| `linkdesc.email` | Contact Trent Power by email |
| `linkdesc.source` | View the public source mirror of this site, with readable annotations and line references |
| `linkdesc.verify` | Check the current page against the published integrity data |
| `linkdesc.now` | Read what Trent Power is currently focused on |
| `linkdesc.theme_light` | Switch to the light appearance |
| `linkdesc.theme_auto` | Match the system appearance setting |
| `linkdesc.theme_dark` | Switch to the dark appearance |
| `linkdesc.lang_en` | Read this site in English |
| `linkdesc.lang_fr` | Lire ce site en français |
| `linkdesc.verify_locally` | Read the instructions to verify the publication locally with command-line tools |
| `linkdesc.manifest` | Download the signed integrity manifest (JSON listing every public file and its SHA-256) |
| `linkdesc.signature` | Download the detached PGP signature for the integrity manifest |
| `linkdesc.checksums` | Download the SHA-256 checksums for the signed release archives |
| `linkdesc.public_key` | Download the public PGP key used to sign releases |
| `linkdesc.zip` | Download the source archive as a ZIP file |
| `linkdesc.targz` | Download the source archive as a TAR.GZ file |
| `linkdesc.security_threat_model` | Read the security architecture and threat model for this site |
| `linkdesc.security_contact` | Read the security.txt disclosure policy for this site |

---

## 2. Page-specific copy

### Home

| Key | Value | Resolved from |
|---|---|---|
| `hero.statement` | Client strategy,<br><mark>growth systems,</mark><br>and cultural adoption<br>at global scale. |  |
| `hero.body` | I lead client strategy at Group level, focusing on the systems, governance, and ways of working that turn client relationships into long-term value. My work sits at the intersection of strategy, technology, and human relationships, with a focus on impact that scales and endures. |  |
| `approach.label` | Approach |  |
| `approach.growth_title` | Client growth takes discipline |  |
| `approach.growth_body` | Lasting growth follows when elegant systems are in place. |  |
| `approach.clienteling_title` | Clienteling converts transaction into meaning |  |
| `approach.clienteling_detail` | <dfn id="clienteling-definition" itemprop="name">Clienteling</dfn> <span itemprop="description">is a discipline. It is the practice of transforming what a Client Advisor knows into something a Client feels. The moment interactions become mechanical, it stops being Clienteling.</span> |  |
| `approach.adoption_title` | Adoption matters more than tools |  |
| `approach.adoption_body` | A strategy or technology only creates value when teams trust it and choose to use it. Trust must be earned, and utility must be proven. Client Advisors are first-line Clients and vital collaborators. |  |
| `approach.ai_title` | AI should amplify human relationships |  |
| `approach.ai_body` | Authenticity is a human advantage, and it cannot be automated. Trust, empathy, and judgement are built in the moment through tone and presence. I use AI to remove friction so people can show up more relevant, more consistent and more human, at scale. |  |
| `approach.governance_title` | Governance creates momentum |  |
| `approach.governance_body` | Clear ownership, cadence, and priorities create alignment, accelerate decisions, and enable scale. |  |
| `approach.taste_title` | Taste is a strategic advantage |  |
| `approach.taste_body` | Discernment, and cultural awareness shape interactions into something valuable and memorable. |  |
| `credentials.label` | Credentials |  |
| `credentials.sydney_title` | University of Sydney |  |
| `credentials.sydney_detail` | Master’s degree, 2009. |  |
| `credentials.exec_title` | Selective executive education |  |
| `credentials.exec_detail` | Ongoing senior-level learning across artificial intelligence, consumer behaviour, organisational transformation, and leadership coaching. |  |
| `trajectory.label` | Trajectory |  |
| `trajectory.current_label` | Current |  |
| `trajectory.current_title` | Group Director, Client Development & Client Relations |  |
| `trajectory.current_org` | <abbr title="Louis Vuitton Moët Hennessy">LVMH</abbr> |  |
| `trajectory.current_detail` | Group-wide client strategy across Maisons and markets |  |
| `trajectory.current_span` | 2023 — now |  |
| `trajectory.previous_label` | Previous |  |
| `trajectory.previous_title` | Group Head of Clienteling |  |
| `trajectory.previous_org` | <abbr title="Louis Vuitton Moët Hennessy">LVMH</abbr> |  |
| `trajectory.previous_span` | 2017 — 2023 |  |
| `trajectory.maisons_label` | Maisons |  |
| `trajectory.maisons_title` | Senior leadership across <a href="/#clienteling-definition" aria-label="Read the definition of Clienteling used on this site">Clienteling</a>, <abbr title="Customer Relationship Management">CRM</abbr> & Retail |  |
| `trajectory.maisons_org` | BVLGARI |  |
| `trajectory.maisons_span` | 2004 — 2017 |  |
| `trajectory.background_label` | Background |  |
| `trajectory.background_title` | Web Entrepreneur |  |
| `trajectory.background_detail` | Building online platforms and communities |  |
| `trajectory.background_span` | 1997 — 2004 |  |
| `projects.label` | Projects |  |
| `projects.paris_desc` | A private cultural intelligence system for Paris, combining location, effort, editorial judgement and personal taste into a calmer way to decide what is worth leaving home for. |  |
| `projects.paris_subline` | A personal experiment in taste systems, local relevance and human-scale recommendation. |  |
| `projects.paris_preview_header` | This week near Jourdain, 20th |  |
| `projects.paris_preview_caption` | A sample cultural intelligence selection for one week, one neighbourhood. |  |
| `projects.paris_cta` | View project |  |
| `projects.tier_walk` | walk |  |
| `projects.tier_metro` | metro |  |
| `projects.tier_bike` | bike |  |
| `contact.label` | Contact |  |
| `contact.headline` | Write,<br>and I&rsquo;ll <em>write back.</em> |  |
| `contact.email_aria` | Email Trent Power |  |
| `home.trust_privacy` | privacy-first |  |
| `home.trust_signed` | signed releases |  |
| `home.trust_static` | static |  |
| `home.trust_no_tracking` | no tracking |  |
| `print.kicker` | trentpower.fr |  |
| `print.name` | Trent Power |  |
| `print.role` | Client strategy, growth systems and cultural adoption |  |
| `print.contact.linkedin` | LinkedIn · Trent Power |  |
| `print.title` | Client strategy, growth systems and cultural adoption at global scale |  |
| `print.body` | I lead client strategy at Group level, focusing on the systems, governance and ways of working that turn client relationships into long-term value. My work sits at the intersection of strategy, technology and human relationships, with a focus on impact that scales and endures. |  |
| `print.focus.01.label` | 01 Focus |  |
| `print.focus.01.title` | Client growth takes discipline |  |
| `print.focus.01.body` | Lasting growth follows when strong systems are in place. |  |
| `print.focus.02.label` | 02 Adoption |  |
| `print.focus.02.title` | Adoption matters more than tools |  |
| `print.focus.02.body` | Technology creates value when teams trust it, choose it and use it. |  |
| `print.focus.03.label` | 03 Human relationships |  |
| `print.focus.03.title` | AI should amplify human relationships |  |
| `print.focus.03.body` | Authenticity remains a human advantage; automation must strengthen context, memory and care. |  |
| `print.focus.04.label` | 04 Governance |  |
| `print.focus.04.title` | Governance creates momentum |  |
| `print.focus.04.body` | Clear ownership and disciplined priorities create alignment and scale. |  |
| `print.credentials.label` | Credentials |  |
| `print.credentials.sydney_title` | University of Sydney |  |
| `print.credentials.sydney_detail` | Master’s degree, 2009. |  |
| `print.credentials.exec_title` | Selective executive education |  |
| `print.credentials.exec_detail` | Ongoing senior-level learning across artificial intelligence, consumer behaviour, organisational transformation, and leadership coaching. |  |
| `print.trajectory.label` | Trajectory |  |
| `print.trajectory.current.label` | Current |  |
| `print.trajectory.current.body` | Group Director, Client Development & Client Relations · LVMH |  |
| `print.trajectory.previous.label` | Previous |  |
| `print.trajectory.previous.body` | Senior leadership across Clienteling, CRM and Client Development |  |
| `print.trajectory.background.label` | Background |  |
| `print.trajectory.background.body` | Early digital and entrepreneurial work building online platforms and communities |  |
| `print.project.label` | Proof point |  |
| `print.project.title` | What’s On in Paris |  |
| `print.project.body` | A private cultural intelligence system for Paris, combining location, effort, editorial judgement and personal taste into a calmer way to decide what is worth leaving home for. |  |
| `print.project.note` | A personal experiment in taste systems, local relevance and human-scale recommendation. |  |
| `print.footer.proof` | Private · Static · Signed · No tracking | `shared.site.proof_line` |
| `print.footer.edition` | Edition <time datetime="2026-05-17">2026-05-17</time> · https://trentpower.fr/ |  |
| `print.footer.citation` | Trent Power. Personal Site. Paris, France. |  |
| `print.footer.evidence` | Public record · HTML · Edition 17 May 2026 |  |
| `print.place` | Personal Site · Paris, France |  |
| `print.doc_title` | Trent Power - Client Strategy Executive Profile |  |
| `print.arch.caption` | Static, privacy-first, signed and inspectable |  |
| `print.arch.browser` | Browser |  |
| `print.arch.host` | Static Host |  |
| `print.arch.files` | Site Files |  |
| `print.arch.cache` | Offline Cache |  |
| `print.arch.trust` | Trust |  |
| `print.arch.archive` | Archive |  |

### Privacy

| Key | Value | Resolved from |
|---|---|---|
| `privacy.page_title` | Privacy & Trust |  |
| `privacy.page_kicker` | Privacy & Trust |  |
| `privacy.page_h1` | <span class="hero-line">Nothing tracked.</span><span class="hero-line">Nothing to delete.</span> |  |
| `privacy.body_intro` | No tracking, analytics, cookies, profiling, embedded third-party services, or third-party requests while you browse. No personal data is collected for analytics, advertising, or profiling. Any limited technical data the server processes is used only to keep the site secure and operating correctly. |  |
| `privacy.body_detail` | External links are ordinary references. They are contacted only if you choose to open them. The only browser storage used is a local language preference. It stays on your device and is never transmitted. |  |
| `privacy.body_records` | Public inspection and verification records are published separately. You can read the <a href="/security/" aria-describedby="desc-security-threat-model">Security & threat model</a> for the full posture. |  |

### Integrity

| Key | Value | Resolved from |
|---|---|---|
| `integrity.page_kicker` | Integrity |  |
| `integrity.page_h1` | <span class="hero-line">Signed.</span><span class="hero-line">Verifiable.</span><span class="hero-line">Reproducible.</span> |  |
| `integrity.page_title` | Integrity |  |
| `integrity.body_intro` | Every public file is hashed and listed in a manifest, signed with a detached <abbr title="Pretty Good Privacy">PGP</abbr> signature so each release can be checked against the publisher's key - independently, on your own machine, without trust in this server. You can <a href="/integrity/verify-locally/" aria-describedby="desc-verify-locally">verify locally here</a>. |  |
| `integrity.file_integrity` | /integrity.json · SHA-256 hashes of all public assets |  |
| `integrity.file_sig` | /integrity.json.sig · detached PGP signature |  |
| `integrity.file_key` | /.well-known/pgp-key.asc · public signing key |  |
| `integrity.copy_button` | Copy |  |
| `integrity.copy_button_done` | Copied |  |
| `integrity.fingerprint_copy` | Copy fingerprint |  |
| `integrity.fingerprint_copied` | Copied |  |
| `integrity.record.kicker` | Signed release |  |
| `integrity.record.title` | <time datetime="2026-05">May 2026</time> |  |
| `integrity.record.status_short` | Manifest · Signature · Public key |  |
| `integrity.record.label.manifest` | Manifest |  |
| `integrity.record.label.signature` | Detached signature | `shared.verification.signature` |
| `integrity.record.label.public_key` | Public key |  |
| `integrity.record.label.archives` | Archives |  |
| `integrity.record.label.checksums` | Archive checksums |  |
| `integrity.record.label.fingerprint` | Fingerprint |  |
| `integrity.record.desc.manifest` | <abbr title="Secure Hash Algorithm, 256-bit">SHA-256</abbr> hashes of public files |  |
| `integrity.record.desc.signature` | Detached <abbr title="Pretty Good Privacy">PGP</abbr> signature |  |
| `integrity.record.desc.public_key` | Public signing key |  |
| `integrity.record.desc.archives` | Signed public source release |  |
| `integrity.record.desc.checksums` | Signed checksum list for archive downloads |  |
| `integrity.record.action.view_manifest` | View manifest |  |
| `integrity.record.action.view_releases` | View releases |  |
| `integrity.record.group.verification` | Verification records |  |
| `integrity.record.group.archives` | Source archives |  |
| `integrity.record.group.fingerprint` | Release fingerprint |  |
| `integrity.verify_release_local.summary` | Advanced local verification |  |
| `integrity.verify_release_local.note` | Run the signed manifest check in a temporary keyring. |  |
| `releases.page_title` | Releases |  |
| `releases.body_intro` | Each <dfn id="signed-release">release</dfn> is a frozen, signed snapshot of the public site at the time of publication. Source archives can be downloaded, and checksums and signatures are provided for local verification. |  |
| `releases.editions_heading` | Editions |  |
| `releases.group.current` | Current release |  |
| `releases.group.archive` | Archive |  |
| `releases.view_release` | View release |  |
| `releases.download_checksums_sig` | Checksums & signature |  |
| `releases.aria.actions_current` | Current release downloads and verification |  |
| `releases.aria.actions_archive` | Release record |  |
| `releases.detail.page_title` | May 2026 |  |
| `releases.detail.intro` | Signed release archives for the 9 May 2026 edition. A signed checksum list verifies the archive set; checksums verify the downloaded files; detached signatures verify each archive directly. The signed manifest at /integrity.json remains the live-site authority. |  |
| `releases.detail.card.kicker` | Release files |  |
| `releases.detail.card.title` | 9 May 2026 |  |
| `releases.detail.card.status` | ZIP · TAR.GZ · Checksums · Signatures |  |
| `releases.detail.card.label.zip` | ZIP |  |
| `releases.detail.card.label.zip_sig` | ZIP signature |  |
| `releases.detail.card.label.zip_sha` | ZIP checksum |  |
| `releases.detail.card.label.targz` | TAR.GZ |  |
| `releases.detail.card.label.targz_sig` | TAR.GZ signature |  |
| `releases.detail.card.label.targz_sha` | TAR.GZ checksum |  |
| `releases.detail.card.label.sums` | Checksum list |  |
| `releases.detail.card.label.sums_sig` | Checksum list signature |  |
| `releases.detail.card.desc.zip` | Portable public source snapshot |  |
| `releases.detail.card.desc.sig` | Detached <abbr title="Pretty Good Privacy">PGP</abbr> signature |  |
| `releases.detail.card.desc.sha` | SHA-256 checksum |  |
| `releases.detail.card.desc.targz` | Technical preservation archive |  |
| `releases.detail.card.desc.sums` | SHA-256 list for release archives |  |
| `releases.detail.card.desc.sums_sig` | Detached <abbr title="Pretty Good Privacy">PGP</abbr> signature over SHA256SUMS |  |
| `releases.detail.note` | Archive binaries are not included in /integrity.json to avoid recursive hashing. They are verified separately through the signed checksum list, individual SHA-256 checksums and detached signatures. <a href="/integrity/">Integrity</a> remains the live-site authority. |  |
| `releases.edition_feb` | February 2026 · initial signed release |  |
| `releases.edition_feb_date` | February 2026 |  |
| `releases.edition_feb_desc` | <cite>Initial signed release</cite> |  |
| `releases.edition_feb_meta` | Signed snapshot · Initial release |  |
| `releases.edition_may09_date` | 9 May 2026 |  |
| `releases.edition_may09_desc` | <cite>Final May edition</cite> |  |
| `releases.edition_may09_meta` | Signed snapshot · Earlier release |  |
| `releases.edition_may17_date` | 17 May 2026 |  |
| `releases.edition_may17_desc` | <cite>Editorial cohesion</cite> |  |
| `releases.edition_may17_meta` | Signed snapshot · Previous release |  |
| `releases.edition_may19_date` | 19 May 2026 |  |
| `releases.edition_may19_desc` | <cite>Bilingual editions</cite> |  |
| `releases.edition_may19_meta` | Signed snapshot · Current release |  |
| `releases.download_zip` | Download ZIP |  |
| `releases.download_targz` | Download TAR.GZ |  |

### Source

| Key | Value | Resolved from |
|---|---|---|
| `source.page_kicker` | Source |  |
| `source.heading` | <span class="hero-line">Every public byte,</span><span class="hero-line">in plain text.</span> |  |
| `source.intro_lede` | Selected public files, published in readable form. For inspection, preservation, and machine readability. |  |
| `source.curation_note` | This index shows the principal public mirrors. Additional mirrored files may remain available by direct URL where they support verification, recovery, or release integrity. |  |
| `source.download_lede` | Download the public source archive for the current edition |  |
| `source.download_targz` | TAR.GZ |  |
| `source.download_zip` | ZIP |  |
| `source.download_checksums` | Checksums |  |
| `source.group.published-pages` | Published pages |  |
| `source.group.trust-records` | Trust records |  |
| `source.group.scripts` | Scripts |  |
| `source.group.metadata` | Metadata |  |
| `source.col.validated` | Verified |  |
| `source.group_gloss.published-pages` | Readable mirrors of the principal public pages, served as plain text so the bytes can be inspected without execution. |  |
| `source.group_gloss.trust-records` | Public commitments and identity surfaces. Who publishes the site, what is promised, where disclosure runs. |  |
| `source.group_gloss.scripts` | Authored stylesheets and JavaScript the page ships to the browser. Mirrored from source, not the minified deployed bytes. |  |
| `source.group_gloss.metadata` | Server configuration and machine-readable records describing the site to crawlers, indexers and language models. |  |
| `source.editions.eyebrow` | Editions |  |
| `source.editions.title` | Edition lineage |  |
| `source.editions.note.current` | Current signed release |  |
| `source.editions.note.earlier` | Earlier signed release |  |
| `source.files.403_html_txt.description` | Forbidden page. |  |
| `source.files.404_html_txt.description` | Not found page. |  |
| `source.files.500_html_txt.description` | Server error page. |  |
| `source.files.ai_usage_txt_txt.description` | Statement of AI usage and policy for the site. |  |
| `source.files.app_enhance_js_txt.description` | Progressive enhancement layer. Non-essential interactions, gracefully optional. |  |
| `source.files.app_js_txt.description` | Authored runtime script. Navigation, language switch, citation drawer wiring. |  |
| `source.files.assertion_txt_txt.description` | Authorship assertion. Declaration of authorship and integrity intent. |  |
| `source.files.attestations_json_txt.description` | Public attestations. Verifiable claims about the site. |  |
| `source.files.changelog_txt_txt.description` | Edition change log. Notable revisions to the public site. |  |
| `source.files.cite_js_txt.description` | Cite-and-verify drawer. Surfaces canonical URL, page fingerprint and signature. |  |
| `source.files.fonts_full_css_txt.description` | Webfont declarations. Subsets, formats and fallbacks. |  |
| `source.files.htaccess_txt.description` | Apache configuration. Public-safety scanned before mirroring. |  |
| `source.files.humans_txt_txt.description` | Credits and notes for the people behind the site. |  |
| `source.files.i18n_core_js_txt.description` | Editorial translation source. All five languages in one authored JSON. |  |
| `source.files.i18n_de_js_txt.description` | German translations. |  |
| `source.files.i18n_es_js_txt.description` | Spanish translations. |  |
| `source.files.i18n_it_js_txt.description` | Italian translations. Deployed compact bytes. |  |
| `source.files.index_html_txt.description` | Home page. The editorial entry point. |  |
| `source.files.integrity_index_html_txt.description` | Integrity overview. The signed manifest, key and release authority. |  |
| `source.files.integrity_releases_2026_05_09_index_html_txt.description` | Frozen page record for the 2026-05-09 edition. |  |
| `source.files.integrity_releases_archive_css_txt.description` | Stylesheet used inside frozen release archives. Held alongside its release records. |  |
| `source.files.integrity_releases_index_html_txt.description` | Release index. The list of signed editions. |  |
| `source.files.llms_txt_txt.description` | Machine-readable guidance for language models and AI systems. |  |
| `source.files.maintenance_html_txt.description` | Maintenance notice. Used during planned downtime. |  |
| `source.files.manifest_webmanifest_txt.description` | Web app manifest. Installable surface metadata. |  |
| `source.files.pgp_txt_txt.description` | PGP statement. The signing key fingerprint and its use. |  |
| `source.files.print_css_txt.description` | Print stylesheet. Layout rules for paper output. |  |
| `source.files.privacy_index_html_txt.description` | Privacy statement. What is collected, retained and shared. |  |
| `source.files.readme_txt.description` | Orientation note for the source tree. Same text shipped at the root of every release archive. |  |
| `source.files.robots_txt_txt.description` | Crawler access policy and public indexing intent. |  |
| `source.files.security_acknowledgments_index_html_txt.description` | Acknowledgments for public security disclosures. |  |
| `source.files.security_index_html_txt.description` | Security posture. Architecture, headers and disclosure path. |  |
| `source.files.site_metadata_json_txt.description` | Site-level metadata. Edition, build, asset version. |  |
| `source.files.sitemap_xml_sha256_txt.description` | Source mirror of the SHA-256 checksum for sitemap.xml. |  |
| `source.files.sitemap_xml_txt.description` | Public sitemap. URL inventory for crawlers. |  |
| `source.files.source_manifest_json_txt.description` | Manifest of the /source/ tree itself. Every mirrored file with its hash. |  |
| `source.files.statement_txt_txt.description` | Editorial statement. The site's authoring principles. |  |
| `source.files.styles_css_txt.description` | Authored stylesheet. Mirrored from source, not the minified deployed bytes. |  |
| `source.files.sw_cache_manifest_json_txt.description` | Service worker cache manifest. Files pinned for offline use. |  |
| `source.files.sw_js_txt.description` | Service worker. Offline cache for the public site. |  |
| `source.files.sw_reset_index_html_txt.description` | Service worker reset. Clears the offline cache. |  |
| `source.files.verify_index_html_txt.description` | Verification interface. Page-level fingerprint checks. |  |
| `source.files.verify_verify_js_txt.description` | Verification logic. Renders a page record from the verification map. |  |
| `source.files.well_known_attribution_txt_txt.description` | Author attribution. Names the responsible party for the public site. |  |
| `source.files.well_known_build_json_txt.description` | Build record. Reproducibility data for the current edition. |  |
| `source.files.well_known_person_json_txt.description` | Machine-readable identity in JSON-LD. The reference used by discovery, federation and verification. |  |
| `source.files.well_known_person_json_txt.role` | Canonical identity record |  |
| `source.files.well_known_pgp_key_asc_txt.description` | ASCII-armoured public signing key. The publisher's signing identity. |  |
| `source.files.well_known_publication_json_txt.description` | Publication record. Describes the site as a self-managed editorial work. |  |
| `source.files.well_known_security_txt_txt.description` | Coordinated disclosure policy. Standard /.well-known/security.txt contact and scope. |  |
| `source.files.well_known_security_txt_txt.role` | Public trust surface |  |
| `source.files.well_known_webfinger_txt.description` | WebFinger discovery surface. Resolves identity across federated protocols. |  |
| `source.files.well_known_webfinger_txt.role` | Identity discovery |  |
| `source_reader.title` | Source reader |  |
| `source_reader.loading` | Loading source… |  |
| `source_reader.action.canonical` | Canonical |  |
| `source_reader.action.verify` | Verify |  |
| `source_reader.action.plain_text` | Raw |  |
| `source_reader.action.copy_code` | Copy code |  |
| `source_reader.action.wrap_lines` | Wrap lines |  |
| `source_reader.action.unwrap_lines` | Unwrap lines |  |
| `source_reader.action.back_to_top` | Top |  |
| `source_reader.action.copied` | Copied |  |
| `source_reader.action.view_source` | Source |  |
| `source_reader.action.view_annotated` | Annotated |  |
| `source_reader.action.view_rendered_page` | View rendered page |  |
| `source_reader.action.reading_mode` | Reading mode |  |
| `source_reader.action.top` | Top |  |
| `source_reader.action.copy` | Copy |  |
| `source_reader.action.copy_link` | Copy link |  |
| `source_reader.action.clear` | Clear |  |
| `source_reader.action.count_line_one` | 1 line |  |
| `source_reader.action.count_lines_many` | {n} lines |  |
| `source_reader.action.line_selected` | Line {n} selected |  |
| `source_reader.action.range_selected` | Lines {start} to {end} selected |  |
| `source_reader.action.selection_cleared` | Selection cleared |  |
| `source_reader.action.lines_copied` | {n} lines copied |  |
| `source_reader.action.link_copied` | Link copied |  |
| `source_reader.action.copy_failed` | Copy unavailable |  |
| `source_reader.action.link_copied_normalised` | Link copied — normalised to lines {start} to {end} |  |
| `source_reader.meta.validated` | Verified |  |
| `source_reader.meta.part_of` | Related systems: |  |
| `source_reader.meta.document_map` | Document map |  |
| `source_reader.meta.end_of_source` | End of source mirror |  |
| `source_reader.meta.intent` | This reader presents public source mirrors with structural annotations and signed publication references. |  |
| `source_reader.integrity.canonical` | Canonical file |  |
| `source_reader.integrity.edition` | Edition |  |
| `source_reader.integrity.sha256` | SHA-256 |  |
| `source_reader.integrity.signed_release` | Signed release |  |
| `source_reader.map_label.head` | Head |  |
| `source_reader.map_label.identity` | Identity |  |
| `source_reader.map_label.discovery` | Discovery |  |
| `source_reader.map_label.social_preview` | Social preview |  |
| `source_reader.map_label.assets` | Assets |  |
| `source_reader.map_label.structured_data` | Structured data |  |
| `source_reader.map_label.header` | Header |  |
| `source_reader.map_label.main` | Main |  |
| `source_reader.map_label.footer` | Footer |  |
| `source_reader.map_label.tokens` | Tokens |  |
| `source_reader.map_label.fonts` | Fonts |  |
| `source_reader.map_label.base` | Base |  |
| `source_reader.map_label.layout` | Layout |  |
| `source_reader.map_label.components` | Components |  |
| `source_reader.map_label.responsive` | Responsive |  |
| `source_reader.map_label.print` | Print |  |
| `source_reader.map_label.state` | State |  |
| `source_reader.map_label.i18n` | i18n |  |
| `source_reader.map_label.events` | Events |  |
| `source_reader.map_label.modals` | Modals |  |
| `source_reader.map_label.copy` | Copy |  |
| `source_reader.map_label.verification` | Verification |  |
| `source_reader.map_label.init` | Init |  |
| `source_reader.map_label.policy` | Policy |  |
| `source_reader.map_label.records` | Records |  |
| `source_reader.mode.label` | Reading mode |  |
| `source_reader.mode.source` | Source |  |
| `source_reader.mode.annotated` | Annotated |  |
| `source_reader.mode.raw` | Raw |  |
| `source_reader.end.title` | End of source mirror |  |
| `source_reader.end.edition` | Edition |  |
| `source_reader.end.sha256` | SHA-256 |  |
| `source_reader.end.signed_release` | Signed release |  |
| `source_reader.kind.html` | HyperText Markup Language |  |
| `source_reader.kind.css` | Cascading Style Sheets |  |
| `source_reader.kind.js` | JavaScript |  |
| `source_reader.kind.json` | JavaScript Object Notation |  |
| `source_reader.kind.xml` | Extensible Markup Language |  |
| `source_reader.kind.text` | Plain text |  |
| `source_reader.kind.apache` | Apache configuration |  |
| `source_reader.kind.sig` | Detached PGP signature |  |
| `source_reader.kind.asc` | ASCII-armoured PGP key |  |
| `source_reader.gloss.foundations` | character encoding, viewport, colour scheme. |  |
| `source_reader.gloss.head` | document head — metadata, no rendered content. |  |
| `source_reader.gloss.identity` | authorship, application name, attribution links. |  |
| `source_reader.gloss.document` | page title, description, canonical url. |  |
| `source_reader.gloss.discovery` | indexing and referrer policy. |  |
| `source_reader.gloss.social` | open graph and twitter card metadata. |  |
| `source_reader.gloss.assets` | stylesheets, scripts, icons, manifest. |  |
| `source_reader.gloss.icons` | platform icons and home-screen artwork. |  |
| `source_reader.gloss.structured` | json-ld schema, machine-readable identity. |  |
| `source_reader.gloss.header` | site header — wordmark and primary nav. |  |
| `source_reader.gloss.footer` | colophon, language switch, footer actions. |  |
| `source_reader.gloss.script` | site application logic. |  |
| `source_reader.gloss.tokens` | design tokens — colours, typography, spacing. |  |
| `source_reader.gloss.fonts` | font face declarations and font assets. |  |
| `source_reader.gloss.base` | reset and base element typography. |  |
| `source_reader.gloss.layout` | page-level layout grammar. |  |
| `source_reader.gloss.components` | reusable component styles. |  |
| `source_reader.gloss.responsive` | viewport-aware overrides. |  |
| `source_reader.gloss.print` | print stylesheet rules. |  |
| `source_reader.gloss.state` | application state and runtime variables. |  |
| `source_reader.gloss.i18n` | translation lookup and language switching. |  |
| `source_reader.gloss.events` | event listeners and interaction wiring. |  |
| `source_reader.gloss.modals` | overlay surfaces, dialogs, focus traps. |  |
| `source_reader.gloss.copy` | clipboard interactions. |  |
| `source_reader.gloss.verification` | signed-manifest and cryptographic references. |  |
| `source_reader.gloss.records` | editorial record entries. |  |
| `source_reader.gloss.init` | boot sequence — runs once on load. |  |
| `source_reader.gloss.policy` | declared site policies. |  |

### Verify

| Key | Value | Resolved from |
|---|---|---|
| `verify.kicker` | Verify |  |
| `verify.page_kicker` | Verify page |  |
| `verify.title` | Verify this page |  |
| `verify.lede` | A public route for checking source, hash, signature and canonical identity. |  |
| `verify.noscript_fallback` | JavaScript is required to select and display a page record here. Source mirrors, the signed manifest and release archives remain available through <a href="/source/">Source</a> and <a href="/integrity/">Integrity</a>. |  |
| `verify.meta` | Edition 2026-05-17 · trentpower.fr/verify/ |  |
| `verify.doc_title` | Trent Power - Verification Sheet |  |
| `verify.action.copy_canonical` | Copy URL |  |
| `verify.action.copy_hash` | Copy hash |  |
| `verify.action.copy_command` | Copy verification command |  |
| `verify.action.open_source` | Open source mirror |  |
| `verify.action.open_manifest` | Open manifest entry |  |
| `verify.action.open_signature` | Open signature |  |
| `verify.action.open_key` | Open public key |  |
| `verify.action.copied` | Copied |  |
| `verify.action.copy_manifest_command` | Copy manifest command |  |
| `verify.action.copy_source_command` | Copy source command |  |
| `verify.action.copy_fingerprint` | Copy fingerprint |  |
| `verify.action.view_source_mirror` | View source mirror |  |
| `verify.action.view_source_code` | View source code |  |
| `verify.action.open_source_mirror` | Open mirror |  |
| `verify.command.manifest_title` | Verify the signed manifest |  |
| `verify.command.source_title` | Verify the source mirror |  |
| `verify.command.note` | The signed manifest verifies the published file set. The second command hashes the source mirror so it can be compared against the expected SHA-256 above. |  |
| `verify.unknown.title` | Route not in the verification map |  |
| `verify.unknown.body` | This route is not in the public verification map. You can still inspect the public manifest, source view and signed releases. |  |
| `verify.unknown.action.source` | Source |  |
| `verify.unknown.action.manifest` | Integrity manifest |  |
| `verify.unknown.action.releases` | Release archive |  |
| `verify.status.found` | Found in signed manifest |  |
| `verify.status.missing` | Not found in current public manifest |  |
| `verify.title_default` | <span class="hero-line">Check page against code, size &amp; signature</span> |  |
| `verify.title_prefix` | Verify |  |
| `verify.lede_v2` | Check a published page against its canonical location, source mirror, page fingerprint and signed release archive. |  |
| `verify.local.heading` | Verify locally |  |
| `verify.local.manifest_label` | Verify the signed manifest |  |
| `verify.local.manifest_desc` | Checks that /integrity.json was signed by the published public key. |  |
| `verify.local.mirror_label` | Verify this page mirror |  |
| `verify.local.mirror_desc` | Calculates the source mirror fingerprint so it can be compared with the expected value above. |  |
| `verify.local.intro` | Run two local checks: verify the signed manifest, then compare this page's source mirror against the expected fingerprint. |  |
| `verify.local.subheading_manifest` | Verify signed manifest |  |
| `verify.local.subheading_mirror` | Verify source mirror |  |
| `verify.local.closing` | The signed manifest verifies the published file set. The source command hashes this page's mirror so it can be compared against the fingerprint above. |  |
| `verify.thispage.heading` | This page |  |
| `verify.thispage.row.title` | Page title |  |
| `verify.thispage.row.canonical` | Canonical URL |  |
| `verify.thispage.row.route` | Route |  |
| `verify.thispage.row.source` | Source mirror |  |
| `verify.thispage.row.file_type` | File type |  |
| `verify.thispage.row.file_size` | File size |  |
| `verify.thispage.row.manifest_status` | Manifest status |  |
| `verify.thispage.row.validated` | Last verified |  |
| `verify.thispage.row.sha256` | Page fingerprint |  |
| `verify.thispage.row.release` | Release archive |  |
| `verify.thispage.row.file` | File |  |
| `verify.thispage.row.citation` | Citation |  |
| `verify.thispage.row.route_prefix` | Route |  |
| `verify.thispage.status.found_manifest` | Found in signed manifest |  |
| `verify.thispage.status.source_available` | Source available |  |
| `verify.thispage.status.release_archived` | Release archived |  |
| `verify.thispage.status.short.signed` | Signed |  |
| `verify.thispage.status.short.source` | Mirrored |  |
| `verify.thispage.status.short.archived` | Archive |  |
| `verify.thispage.kicker` | Page record |  |
| `verify.thispage.group.citation` | Citation |  |
| `verify.thispage.group.location` | Canonical location |  |
| `verify.thispage.group.evidence` | Source mirror |  |
| `verify.thispage.group.fingerprint` | Page fingerprint |  |
| `verify.thispage.group.archive` | Release archive |  |
| `verify.thispage.validated_prefix` | Verified |  |
| `verify.selected.manifest` | Integrity manifest |  |
| `verify.selected.signature` | Detached signature | `shared.verification.signature` |
| `verify.selected.public_key` | Public key |  |
| `verify.general.source` | Source viewer |  |
| `verify.general.releases` | Release archive |  |
| `verify.chooser.heading` | Related records |  |
| `verify.chooser.label.home` | Homepage |  |
| `verify.chooser.label.privacy` | Privacy |  |
| `verify.chooser.label.security` | Security |  |
| `verify.chooser.label.integrity` | Integrity |  |
| `verify.chooser.label.verify` | Verify |  |
| `verify.chooser.label.source` | Source |  |
| `verify.chooser.label.releases` | Releases |  |
| `verify_intro.panel_label` | Current edition |  |
| `verify_intro.edition` | Edition |  |
| `verify_intro.signing_key` | Signing key |  |
| `verify_intro.manifest` | Signed manifest |  |
| `verify_intro.signature` | Detached signature | `shared.verification.signature` |
| `verify_intro.public_key` | Public key |  |
| `verify_intro.archive` | Edition archive |  |
| `verify_locally.page_kicker` | Verify Locally |  |
| `verify_locally.page_title` | <span class="hero-line">Get to</span><span class="hero-line">the terminal!</span> |  |
| `verify_locally.body_intro` | Detached verification notes for the signed integrity manifest. Run the check in a temporary keyring so the public signing key does not enter your default keychain. |  |
| `verify_locally.body_close` | The command imports the public key into a throw-away keyring, verifies the signed manifest, and removes the working files. No state is retained on the machine afterwards. |  |

### Security

| Key | Value | Resolved from |
|---|---|---|
| `security.page_title` | Security & Threat Model |  |
| `security.page_kicker` | Security & Threat Model |  |
| `security.page_h1` | <span class="hero-line">Static.</span><span class="hero-line">Self-managed.</span><span class="hero-line">Verification-led.</span> |  |
| `security.body_intro` | How this site is hosted, what it protects, what it doesn't - and how anyone can verify it independently. |  |
| `security.s1_summary` | 1. Architecture |  |
| `security.s2_summary` | 2. Assets protected |  |
| `security.s2_body` | The controls described here protect: |  |
| `security.s2_list` | Domain ownership DNS integrity Hosting account integrity Public content integrity The signing key used for release authenticity |  |
| `security.s3_summary` | 3. Threat model |  |
| `security.s3_infra_heading` | Infrastructure compromise |  |
| `security.s3_infra_list` | Registrar account takeover <abbr title="Domain Name System">DNS</abbr> hijack Hosting credential compromise |  |
| `security.s3_content_heading` | Content tampering |  |
| `security.s3_content_list` | Post-deployment file modification Malicious JavaScript injection Silent alteration of static assets |  |
| `security.s3_admin_heading` | Administrative abuse |  |
| `security.s3_admin_list` | Credential stuffing Automated vulnerability scanning |  |
| `security.s3_noise_heading` | Commodity internet noise |  |
| `security.s3_noise_body` | Continuous automated probing for common <abbr title="Content Management System">CMS</abbr> paths, configuration files, or known endpoints. These are treated as persistent background conditions rather than exceptional events. |  |
| `security.s4_summary` | 4. Controls |  |
| `security.s4_registrar_heading` | Registrar &amp; <abbr title="Domain Name System">DNS</abbr> |  |
| `security.s4_registrar_list` | <abbr title="Multi-Factor Authentication">MFA</abbr> enabled Registrar lock active <abbr title="Domain Name System Security Extensions">DNSSEC</abbr> enabled and validated <abbr title="Certificate Authority Authorization">CAA</abbr> records restrict certificate issuance |  |
| `security.s4_hosting_heading` | Hosting |  |
| `security.s4_hosting_list` | Multi-factor authentication enabled <abbr title="Secure File Transfer Protocol">SFTP</abbr>-only deployment No <abbr title="Secure Shell">SSH</abbr> shell exposure No scheduled background execution |  |
| `security.s4_content_heading` | Public content |  |
| `security.s4_content_list` | Static architecture reduces server-side attack surface Strict <abbr title="Content Security Policy">CSP</abbr> starting from <code>default-src 'none'</code> No external resource loading No dynamic script execution |  |
| `security.s4_monitoring_heading` | Monitoring |  |
| `security.s4_monitoring_list` | Structured log analysis Pattern detection and anomaly scoring File integrity drift detection against the signed release baseline |  |
| `security.s6_summary` | 6. Residual risk |  |
| `security.s6_protect_summary` | This model protects the public static site. It does not protect against registrar compromise, hosting compromise, client-device compromise or private key compromise. |  |
| `security.s6_intro` | This model does not attempt to address: |  |
| `security.s6_list` | Physical compromise of hosting infrastructure Global <abbr title="Domain Name System">DNS</abbr> root compromise Certificate authority (<abbr title="Certificate Authority">CA</abbr>) compromise State-level adversaries Zero-day browser exploits on client devices |  |
| `security.s6_footer` | The main risks remain domain, <abbr title="Domain Name System">DNS</abbr>, hosting and private key compromise. |  |
| `security.s7_summary` | 7. Disclosure |  |
| `security.s7_body` | Responsible disclosure is welcome. Security contact details and encrypted communication instructions are published at <a href="/.well-known/security.txt" aria-describedby="desc-security-contact"><code>/.well-known/security.txt</code></a>. |  |
| `security.s8_summary` | 8. Design principles |  |
| `security.s8_list` | Simplicity over complexity Deterministic behaviour over dynamic systems Transparency over obscurity Verifiable integrity over trust assumptions |  |
| `security.public_verification_summary` | 5. Public verification surface |  |
| `security.public_verification_intro` | The site exposes public inspection routes so published content can be checked without private infrastructure access. |  |
| `security.public_verification_list` | <a href="/integrity/" aria-label="Open the integrity archive for signed releases, public key and manifest"><code>/integrity/</code></a> records signed releases, public key and manifest <a href="/verify/" aria-label="Open the page verification tool for canonical URLs, source mirrors and fingerprints"><code>/verify/</code></a> records one page’s canonical <abbr title="Uniform Resource Locator">URL</abbr>, source mirror and fingerprint <a href="/source/" aria-label="Open readable source mirrors of selected public files"><code>/source/</code></a> publishes readable mirrors of selected public files <a href="/integrity/releases/" aria-label="Open frozen signed release snapshots"><code>/integrity/releases/</code></a> preserves frozen signed snapshots |  |
| `security.public_verification_footer` | These routes support inspection and provenance. They do not remove the need to protect <abbr title="Domain Name System">DNS</abbr>, hosting credentials and the private signing key. |  |
| `security.s1_routes_note` | Public inspection routes expose the signed manifest, page records, readable source mirrors and archived releases without exposing private infrastructure. |  |
| `security.architecture_card.kicker` | Architecture |  |
| `security.architecture_card.browser_label` | Browser |  |
| `security.architecture_card.browser_body` | <abbr title="HyperText Transfer Protocol Secure">HTTPS</abbr> · no cookies · no analytics |  |
| `security.architecture_card.host_label` | Static host |  |
| `security.architecture_card.host_body` | Apache · Gandi · Paris · <abbr title="Secure File Transfer Protocol">SFTP</abbr> deployment |  |
| `security.architecture_card.files_label` | Site files |  |
| `security.architecture_card.files_body` | <abbr title="HyperText Markup Language">HTML</abbr> · <abbr title="Cascading Style Sheets">CSS</abbr> · vanilla JS · self-hosted fonts |  |
| `security.architecture_card.cache_label` | Offline cache |  |
| `security.architecture_card.cache_body` | Service worker · local cache after first visit |  |
| `security.architecture_card.trust_label` | Trust |  |
| `security.architecture_card.trust_body` | Integrity · Verify · Source · Releases |  |
| `security.architecture_card.archive_label` | Archive |  |
| `security.architecture_card.archive_body` | Frozen signed releases |  |
| `acknowledgments.page_title` | Security acknowledgements |  |
| `acknowledgments.body_intro` | This page records responsible security disclosures that have been verified and resolved. |  |
| `acknowledgments.none` | There are no acknowledgements at present. This reflects the absence of reportable disclosures to date, not the absence of review or maintenance. |  |
| `acknowledgments.report` | If you believe you have found a security issue with this site, please report it responsibly. Contact details and disclosure preferences are listed in security.txt. |  |
| `acknowledgments.integrity_link` | Site integrity statement |  |

---

## 3. Print copy

### Home · print profile

_(no print fields)_

### Privacy · print profile

| Key | Value | Resolved from |
|---|---|---|
| `privacy.print.kicker` | Privacy & Trust |  |
| `privacy.print.title` | Privacy-first by design |  |
| `privacy.print.lede` | This site is intentionally simple and privacy-respectful. It uses no tracking, analytics, cookies, profiling, or embedded third-party requests while you browse. |  |
| `privacy.print.meta` | Edition 2026-05-17 · trentpower.fr/privacy/ |  |
| `privacy.print.card.01.label` | 01 No tracking |  |
| `privacy.print.card.01.title` | No tracking |  |
| `privacy.print.card.01.body` | No analytics. No cookies. No profiling. No third-party requests while browsing. |  |
| `privacy.print.card.02.label` | 02 No data collection |  |
| `privacy.print.card.02.title` | No data collection |  |
| `privacy.print.card.02.body` | No public forms. No visitor accounts. No behavioural tracking. No advertising infrastructure. |  |
| `privacy.print.card.03.label` | 03 Verification route |  |
| `privacy.print.card.03.title` | Verification route |  |
| `privacy.print.card.03.body` | Integrity page. Security page. Public manifest. Source view. |  |
| `privacy.print.card.04.label` | 04 Design principle |  |
| `privacy.print.card.04.title` | Privacy as posture |  |
| `privacy.print.card.04.body` | Privacy is not a compliance layer. It is part of the site’s editorial and professional posture. |  |
| `privacy.print.card.05.label` | 05 What you can check |  |
| `privacy.print.card.05.title` | What you can check |  |
| `privacy.print.card.05.body` | View source. Read /integrity.json. Verify the signature. Inspect the security headers. |  |
| `privacy.print.card.06.label` | 06 Contact |  |
| `privacy.print.card.06.title` | Contact |  |
| `privacy.print.card.06.body` | trent@trentpower.fr · canonical route trentpower.fr/privacy/ |  |
| `privacy.print.footer.proof` | Private · Static · Signed · No tracking | `shared.site.proof_line` |
| `privacy.print.footer.edition` | Edition 2026-05-17 · trentpower.fr/privacy/ |  |
| `privacy.print.qr.label` | trentpower.fr/privacy/ |  |
| `privacy.print.doc_title` | Trent Power - Privacy Trust Sheet |  |

### Integrity · print profile

| Key | Value | Resolved from |
|---|---|---|
| `integrity.print.kicker` | Integrity |  |
| `integrity.print.title` | Signed public verification |  |
| `integrity.print.lede` | Published files are listed in a public manifest and signed with a detached <abbr title="Pretty Good Privacy">PGP</abbr> signature so updates can be verified independently. |  |
| `integrity.print.meta` | Edition 2026-05-17 · trentpower.fr/integrity/ |  |
| `integrity.print.card.01.label` | 01 Manifest |  |
| `integrity.print.card.01.title` | Manifest |  |
| `integrity.print.card.01.body` | <code>/integrity.json</code> - <abbr title="Secure Hash Algorithm, 256-bit">SHA-256</abbr> hashes of every intentional public file. |  |
| `integrity.print.card.02.label` | 02 Signature |  |
| `integrity.print.card.02.title` | Detached signature | `shared.verification.signature` |
| `integrity.print.card.02.body` | /integrity.json.sig - detached <abbr title="Pretty Good Privacy">PGP</abbr> signature that verifies the manifest. |  |
| `integrity.print.card.03.label` | 03 Public key |  |
| `integrity.print.card.03.title` | Public key |  |
| `integrity.print.card.03.body` | /.well-known/pgp-key.asc - fingerprint A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263. |  |
| `integrity.print.card.04.label` | 04 Releases |  |
| `integrity.print.card.04.title` | Frozen releases |  |
| `integrity.print.card.04.body` | /integrity/releases/ - public snapshots: February 2026 and May 2026. |  |
| `integrity.print.card.05.label` | 05 Source route |  |
| `integrity.print.card.05.title` | Source route |  |
| `integrity.print.card.05.body` | /source/ - public text view of selected source files. No secrets, no private artefacts. |  |
| `integrity.print.card.06.label` | 06 Verification |  |
| `integrity.print.card.06.title` | Verification |  |
| `integrity.print.card.06.body` | curl -O trentpower.fr/integrity.json && curl -O trentpower.fr/integrity.json.sig && gpg --verify integrity.json.sig integrity.json |  |
| `integrity.print.footer.proof` | Private · Static · Signed · No tracking | `shared.site.proof_line` |
| `integrity.print.footer.edition` | Edition 2026-05-17 · trentpower.fr/integrity/ |  |
| `integrity.print.qr.label` | trentpower.fr/integrity/ |  |
| `integrity.print.doc_title` | Trent Power - Integrity Verification Sheet |  |
| `releases.print.kicker` | Releases |  |
| `releases.print.title` | Frozen public editions |  |
| `releases.print.lede` | Public release snapshots preserve selected editions of the site with local assets so their design and integrity can be inspected over time. |  |
| `releases.print.meta` | Edition 2026-05-17 · trentpower.fr/integrity/releases/ |  |
| `releases.print.doc_title` | Trent Power - Release Archive Sheet |  |
| `releases.print.card.01.label` | 01 9 May 2026 |  |
| `releases.print.card.01.title` | 9 May 2026 |  |
| `releases.print.card.01.body` | Final May edition. Signed source archives, deterministic ZIP and TAR.GZ, aggregated SHA256SUMS. Clean active filenames. One-page print profile. Trust sheets. |  |
| `releases.print.card.02.label` | 02 February 2026 |  |
| `releases.print.card.02.title` | February 2026 |  |
| `releases.print.card.02.body` | Initial signed release. Earlier visual system. Preserved as a historical archive. |  |
| `releases.print.card.03.label` | 03 Archive principle |  |
| `releases.print.card.03.title` | Archive principle |  |
| `releases.print.card.03.body` | Frozen assets. Local CSS and fonts. No live mutable style dependency. |  |
| `releases.print.card.04.label` | 04 Integrity route |  |
| `releases.print.card.04.title` | Integrity route |  |
| `releases.print.card.04.body` | /integrity.json · /integrity.json.sig · /.well-known/pgp-key.asc |  |
| `releases.print.card.05.label` | 05 Why it matters |  |
| `releases.print.card.05.title` | Why it matters |  |
| `releases.print.card.05.body` | Verifiability. Authorship. Continuity. Public trust. |  |
| `releases.print.card.06.label` | 06 Where to inspect |  |
| `releases.print.card.06.title` | Where to inspect |  |
| `releases.print.card.06.body` | /integrity/releases/2026-05-17/ · /integrity/releases/2026-05-09/ · /integrity/releases/2026-02/ · /source/ |  |
| `releases.print.footer.proof` | Private · Static · Signed · No tracking | `shared.site.proof_line` |
| `releases.print.footer.edition` | Edition 2026-05-17 · trentpower.fr/integrity/releases/ |  |
| `releases.print.qr.label` | trentpower.fr/integrity/releases/ |  |
| `release_archive.print.kicker` | Signed release archive |  |
| `release_archive.print.title` | Edition 2026-05-09 |  |
| `release_archive.print.lede` | Public release archive for the May 2026 signed edition, including manifests, checksums, detached signatures, and reproducible source records. |  |
| `release_archive.print.meta` | Edition 2026-05-09 · trentpower.fr/integrity/releases/2026-05-09/ |  |
| `release_archive.print.doc_title` | Trent Power - Release Archive 2026-05-09 |  |
| `release_archive.print.card.01.label` | 01 Manifest |  |
| `release_archive.print.card.01.title` | Manifest |  |
| `release_archive.print.card.01.body` | /integrity.json - SHA-256 hashes of every intentional public file at edition time. |  |
| `release_archive.print.card.02.label` | 02 Detached signature |  |
| `release_archive.print.card.02.title` | Detached signature |  |
| `release_archive.print.card.02.body` | /integrity.json.sig - PGP detached signature over the manifest. |  |
| `release_archive.print.card.03.label` | 03 Archive checksums |  |
| `release_archive.print.card.03.title` | Archive checksums |  |
| `release_archive.print.card.03.body` | /integrity/releases/2026-05-09/SHA256SUMS - sums for ZIP and TAR.GZ. |  |
| `release_archive.print.card.04.label` | 04 Source archive |  |
| `release_archive.print.card.04.title` | Source archive |  |
| `release_archive.print.card.04.body` | trentpower-fr-2026-05-09.zip · trentpower-fr-2026-05-09.tar.gz - deterministic. |  |
| `release_archive.print.card.05.label` | 05 Verification status |  |
| `release_archive.print.card.05.title` | Verification status |  |
| `release_archive.print.card.05.body` | gpg --verify integrity.json.sig integrity.json against the public key. |  |
| `release_archive.print.card.06.label` | 06 Release fingerprint |  |
| `release_archive.print.card.06.title` | Release fingerprint |  |
| `release_archive.print.card.06.body` | Signed by A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263. |  |
| `release_archive.print.footer.proof` | Private · Static · Signed · No tracking | `shared.site.proof_line` |
| `release_archive.print.footer.edition` | Edition 2026-05-09 · trentpower.fr/integrity/releases/2026-05-09/ |  |
| `release_archive.print.qr.label` | trentpower.fr/integrity/releases/2026-05-09/ |  |

### Source · print profile

| Key | Value | Resolved from |
|---|---|---|
| `source.print.kicker` | Source |  |
| `source.print.title` | Public source view |  |
| `source.print.lede` | Selected public files are mirrored as plain text so the site can be inspected from any reader, including mobile. |  |
| `source.print.meta` | Edition 2026-05-17 · trentpower.fr/source/ |  |
| `source.print.doc_title` | Trent Power - Public Source Sheet |  |
| `source.print.card.01.label` | 01 What is included |  |
| `source.print.card.01.title` | What is included |  |
| `source.print.card.01.body` | HTML mirrors. CSS. JavaScript. Manifest files. .htaccess mirror. |  |
| `source.print.card.02.label` | 02 What is excluded |  |
| `source.print.card.02.title` | What is excluded |  |
| `source.print.card.02.body` | Credentials. Private notes. Invoices. Backups. Generator internals unless explicitly public. |  |
| `source.print.card.03.label` | 03 How it is organised |  |
| `source.print.card.03.title` | How it is organised |  |
| `source.print.card.03.body` | Sorted by file type, then name. Plain text mirrors. SHA-256 hashes. File sizes. |  |
| `source.print.card.04.label` | 04 Verification |  |
| `source.print.card.04.title` | Verification |  |
| `source.print.card.04.body` | source-manifest.json · /integrity.json · detached signature · public key. |  |
| `source.print.card.05.label` | 05 Files of note |  |
| `source.print.card.05.title` | Files of note |  |
| `source.print.card.05.body` | styles.css.txt · app.js.txt · print.css.txt · htaccess.txt · source-manifest.json |  |
| `source.print.card.06.label` | 06 Principle |  |
| `source.print.card.06.title` | Principle |  |
| `source.print.card.06.body` | Human readers first. Machine-readable files preserve identity, authorship and context. |  |
| `source.print.footer.proof` | Private · Static · Signed · No tracking | `shared.site.proof_line` |
| `source.print.footer.edition` | Edition 2026-05-17 · trentpower.fr/source/ |  |
| `source.print.qr.label` | trentpower.fr/source/ |  |

### Verify · print profile

| Key | Value | Resolved from |
|---|---|---|
| `verify_locally.print.kicker` | Integrity verification |  |
| `verify_locally.print.title` | Verify locally |  |
| `verify_locally.print.lede` | Detached verification notes for independently checking the signed integrity manifest using the published public key. |  |
| `verify_locally.print.meta` | Edition 2026-05-17 · trentpower.fr/integrity/verify-locally/ |  |
| `verify_locally.print.doc_title` | Trent Power - Verify Locally |  |
| `verify_locally.print.card.01.label` | 01 Temporary keyring |  |
| `verify_locally.print.card.01.title` | Temporary keyring |  |
| `verify_locally.print.card.01.body` | Use a temp GNUPGHOME so the import does not touch your main keyring. |  |
| `verify_locally.print.card.02.label` | 02 Import public key |  |
| `verify_locally.print.card.02.title` | Import public key |  |
| `verify_locally.print.card.02.body` | curl /.well-known/pgp-key.asc · gpg --import pgp-key.asc. |  |
| `verify_locally.print.card.03.label` | 03 Verify signature |  |
| `verify_locally.print.card.03.title` | Verify signature |  |
| `verify_locally.print.card.03.body` | gpg --verify integrity.json.sig integrity.json - expect Good signature. |  |
| `verify_locally.print.card.04.label` | 04 Check manifest |  |
| `verify_locally.print.card.04.title` | Check manifest |  |
| `verify_locally.print.card.04.body` | /integrity.json lists every public file with its SHA-256. |  |
| `verify_locally.print.card.05.label` | 05 Compare checksums |  |
| `verify_locally.print.card.05.title` | Compare checksums |  |
| `verify_locally.print.card.05.body` | Re-hash any file and compare against the manifest entry. |  |
| `verify_locally.print.card.06.label` | 06 Reproducibility notes |  |
| `verify_locally.print.card.06.title` | Reproducibility notes |  |
| `verify_locally.print.card.06.body` | Each signed edition is frozen in /integrity/releases/. No mutable assets. |  |
| `verify_locally.print.footer.proof` | Private · Static · Signed · No tracking | `shared.site.proof_line` |
| `verify_locally.print.footer.edition` | Edition 2026-05-17 · trentpower.fr/integrity/verify-locally/ |  |
| `verify_locally.print.qr.label` | trentpower.fr/integrity/verify-locally/ |  |

### Security · print profile

| Key | Value | Resolved from |
|---|---|---|
| `security.print.kicker` | Security & Threat Model |  |
| `security.print.title` | Static, self-managed, verification-led |  |
| `security.print.lede` | The public site is static HTML, CSS and vanilla JavaScript, with strict headers, no runtime server logic, no public database and no third-party scripts. |  |
| `security.print.meta` | Edition 2026-05-17 · trentpower.fr/security/ |  |
| `security.print.card.01.label` | 01 Architecture |  |
| `security.print.card.01.title` | Architecture |  |
| `security.print.card.01.body` | Static HTML, CSS, vanilla JavaScript. Self-managed deployment on Apache (Gandi, Paris). No public database. |  |
| `security.print.card.02.label` | 02 Headers |  |
| `security.print.card.02.title` | Security headers |  |
| `security.print.card.02.body` | <abbr title="Content Security Policy">CSP</abbr> default-deny. <abbr title="HTTP Strict Transport Security">HSTS</abbr>. <abbr title="Cross-Origin Opener Policy">COOP</abbr> / <abbr title="Cross-Origin Embedder Policy">COEP</abbr> / <abbr title="Cross-Origin Resource Policy">CORP</abbr>. Referrer-Policy no-referrer. Locked-down Permissions-Policy. |  |
| `security.print.card.03.label` | 03 Assets protected |  |
| `security.print.card.03.title` | Assets protected |  |
| `security.print.card.03.body` | Identity. Published content. Public verification files. Source integrity. |  |
| `security.print.card.04.label` | 04 Threat model |  |
| `security.print.card.04.title` | Threat model |  |
| `security.print.card.04.body` | Content injection. Hosting credential compromise. Spoofed identity. Stale or tampered files. |  |
| `security.print.card.05.label` | 05 Controls |  |
| `security.print.card.05.title` | Controls |  |
| `security.print.card.05.body` | No third-party scripts. No public forms. Signed integrity manifest. Restricted file exposure. Service-worker-controlled cache. |  |
| `security.print.card.06.label` | 06 Residual risk |  |
| `security.print.card.06.title` | Residual risk |  |
| `security.print.card.06.body` | Hosting and registrar risk remain. Static-site exposure is reduced, not eliminated. Responsible disclosure route is published. |  |
| `security.print.footer.proof` | Private · Static · Signed · No tracking | `shared.site.proof_line` |
| `security.print.footer.edition` | Edition 2026-05-17 · trentpower.fr/security/ |  |
| `security.print.qr.label` | trentpower.fr/security/ |  |
| `security.print.doc_title` | Trent Power - Security Threat Model Sheet |  |
| `acknowledgments.print.kicker` | Security acknowledgments |  |
| `acknowledgments.print.title` | Responsible disclosure record |  |
| `acknowledgments.print.lede` | Acknowledgements for individuals and researchers who contributed responsibly to the security posture of this site. |  |
| `acknowledgments.print.meta` | Edition 2026-05-17 · trentpower.fr/security/acknowledgments/ |  |
| `acknowledgments.print.doc_title` | Trent Power - Security Acknowledgments |  |
| `acknowledgments.print.card.01.label` | 01 Disclosure model |  |
| `acknowledgments.print.card.01.title` | Disclosure model |  |
| `acknowledgments.print.card.01.body` | Coordinated, time-bounded, with credit on request. |  |
| `acknowledgments.print.card.02.label` | 02 Reporting policy |  |
| `acknowledgments.print.card.02.title` | Reporting policy |  |
| `acknowledgments.print.card.02.body` | trent@trentpower.fr · PGP-signed reports preferred · public key at /.well-known/pgp-key.asc. |  |
| `acknowledgments.print.card.03.label` | 03 Coordinated remediation |  |
| `acknowledgments.print.card.03.title` | Coordinated remediation |  |
| `acknowledgments.print.card.03.body` | Acknowledge within 72 hours. Patch, verify, publish notes if material. |  |
| `acknowledgments.print.card.04.label` | 04 Verification process |  |
| `acknowledgments.print.card.04.title` | Verification process |  |
| `acknowledgments.print.card.04.body` | Reproduce, hash, sign, and record in the next signed release. |  |
| `acknowledgments.print.card.05.label` | 05 Security contact |  |
| `acknowledgments.print.card.05.title` | Security contact |  |
| `acknowledgments.print.card.05.body` | trent@trentpower.fr · fingerprint A729 591B 450D 3F59 3694 98BD 8299 1F25 04AE 0263. |  |
| `acknowledgments.print.card.06.label` | 06 Publication status |  |
| `acknowledgments.print.card.06.title` | Publication status |  |
| `acknowledgments.print.card.06.body` | Acknowledgement page is the canonical record; updates accompany each signed edition. |  |
| `acknowledgments.print.footer.proof` | Private · Static · Signed · No tracking | `shared.site.proof_line` |
| `acknowledgments.print.footer.edition` | Edition 2026-05-17 · trentpower.fr/security/acknowledgments/ |  |
| `acknowledgments.print.qr.label` | trentpower.fr/security/acknowledgments/ |  |

---

## 4. Metadata copy (page <title>, OG, social previews)

### Home · meta

| Key | Value | Resolved from |
|---|---|---|
| `meta.home.title` | Client Strategy & Growth Systems · Trent Power |  |
| `meta.home.description` | Client strategy, growth systems and cultural adoption at global scale |  |
| `meta.home.og_title` | Client Strategy & Growth Systems · Trent Power |  |
| `meta.home.og_description` | Client strategy, growth systems and cultural adoption at global scale |  |

### Privacy · meta

| Key | Value | Resolved from |
|---|---|---|
| `meta.privacy.title` | Privacy & Trust · Trent Power |  |
| `meta.privacy.description` | A simple, privacy-respectful site with no tracking, analytics, cookies, profiling, or embedded third-party requests while you browse |  |

### Integrity · meta

| Key | Value | Resolved from |
|---|---|---|
| `meta.integrity.title` | Integrity · Trent Power |  |
| `meta.integrity.description` | Signed public releases, integrity manifest, detached signature and public signing key |  |
| `meta.releases.title` | Releases · Trent Power |  |
| `meta.releases.description` | Frozen, signed snapshots of the public site |  |

### Source · meta

| Key | Value | Resolved from |
|---|---|---|
| `meta.source.title` | Source mirrors · Trent Power |  |
| `meta.source.description` | Readable public mirrors of selected site files |  |

### Verify · meta

| Key | Value | Resolved from |
|---|---|---|
| `meta.verify.title` | Verify this page · Trent Power |  |
| `meta.verify.description` | A public page record showing the canonical URL, source mirror, page fingerprint and signed release archive |  |
| `meta.verify_locally.title` | Verify locally · Trent Power |  |
| `meta.verify_locally.description` | Detached verification notes: signed manifest check from a temporary keyring |  |

### Security · meta

| Key | Value | Resolved from |
|---|---|---|
| `meta.security.title` | Security & Threat Model · Trent Power |  |
| `meta.security.description` | Security architecture, operational controls, public verification surfaces and residual risks |  |
| `meta.acknowledgments.title` | Security acknowledgements · Trent Power |  |
| `meta.acknowledgments.description` | Responsible security disclosures verified and resolved for trentpower.fr. |  |

