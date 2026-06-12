# Visual QA contact sheets

Publication proofing artefacts: every representative page of the public
site, both languages, desktop and mobile, light and dark, assembled into
four labelled sheets. They exist so a human can scan the whole surface
at once and answer one question — does this still feel like one
authored product?

The sheets are not a replacement for accessibility or functional tests,
and they are never a deploy gate. The `visual-qa` job of the
publication-check workflow uploads them as a run artefact; locally they
land here and stay out of version control.

Regenerate (requires the optional Playwright dependency):

    python3 -m pip install playwright && python3 -m playwright install chromium
    python3 tools/visual/capture_contact_sheet.py

Outputs:

| Sheet | Viewport | Colour scheme |
| --- | --- | --- |
| `contact-sheet-desktop-light.png` | 1440 × 900 | light |
| `contact-sheet-desktop-dark.png` | 1440 × 900 | dark |
| `contact-sheet-mobile-light.png` | 390 × 844 | light |
| `contact-sheet-mobile-dark.png` | 390 × 844 | dark |

Captured pages: root language gate, English and French homes, privacy /
confidentialité, security / sécurité, verify / vérifier, integrity /
intégrité, source viewer (both languages), local storage, documentation,
403, 404, 500 and maintenance.
