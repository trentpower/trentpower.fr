# Authorship statement

> All content and code are reviewed manually before publication.
> Selective language model assistance may be used for drafting or
> structuring, but no automated publishing occurs.

This is the canonical authorship position for trentpower.fr. The
same statement appears at `/humans.txt` for visitors and is encoded
in machine-readable form at `/attestations.json`:

```json
"automated_publishing": false,
"manual_review_before_publication": true,
"language_model_assistance": "selective drafting or structuring only"
```

## Why this lives here, not in commit messages

Tool provenance and authorship are different things. The repository
is a publication record: the commit history reflects editorial
stewardship, not the chain of utilities used to draft a paragraph.
Putting model trailers (`Co-authored-by:`, `Generated-by:`,
`AI-assisted-by:`) on individual commits would conflate the two and
turn the log into a tool-attribution diary.

The site may use selective language model assistance for drafting or
structuring. Every byte that ships is reviewed before publication.
That posture is recorded once, here and in the public-facing files
above; it is not appended to every commit.

## Enforcement

`tools/quality/validate_git_metadata.py` is a build-gate that scans every
publishable file under `public/`, `tools/`, `templates/`, `docs/`,
`.github/`, and `reports/` for the forbidden trailer
shapes and vendor strings. It runs as predeploy step 14. Any
regression — a stray `Co-authored-by:` line in a generated file, a
`Claude Code` reference in HTML, a `Generated-by:` trailer in a
release note — fails the build before any SFTP transfer.

History rewrite (one-time; the operator's audit record is kept
locally, outside the public tree) removed pre-existing trailers
from earlier commits. The current commit log reflects the
stewardship the site claims.

## Wording rules

Acceptable wording, in calm editorial register:

- "manually reviewed"
- "manually published"
- "reviewed before release"
- "editorially maintained"
- "static publication"
- "no automated publishing"

Avoid (per `tools/quality/validate_language_consistency.py`):

- "hand-written" / "handwritten"
- "fully manual" / "100% manual"
- "AI-generated" / "model-generated"
- "co-created with AI"

The intent is precise truth, not anti-AI defensiveness or
performative manual-craft mythology. The site is authored,
reviewed, and published deliberately. That is enough.
