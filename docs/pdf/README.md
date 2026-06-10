# docs/pdf — the README.pdf source

`README.pdf` (at the repository root) is the editorial, print-ready documentation
of the whole site. This folder is its source. **The HTML is the source of truth;
the PDF is an export** — when the docs change, edit the HTML and re-pour. Never
hand-patch the exported PDF.

## Files

```
readme.html        the editorial document (edit this)
guide.css          the print style system (visual contract; copied verbatim)
print-paged.css    paged-media adapter: @page furniture, breaks, data charts
fonts/             Klim woff2 — Signifier, Söhne, Söhne Mono
paper-noise.svg    warm-paper texture
build.sh           paginate + export → ../../README.pdf
```

## Re-pour

```sh
bash docs/pdf/build.sh
```

Needs Chromium on `PATH` (used headless) and Node/npx (pulls `pagedjs-cli` into
the gitignored `node_modules` on first run). Output is `README.pdf` at the repo
root.

## Conventions (from the style brief)

- Type: Signifier (serif, all reading), Söhne (sans, captions only — never
  headings), Söhne Mono (paths, hashes, labels).
- Colour: warm paper, iron ink, one oxblood accent. No semantic colour. Code
  tokens are the only jewel-tone pigment; diagrams read in grayscale.
- Every section: plain-English summary → small visual model → detail → one-line
  "why this matters". Never open with implementation detail.
- Reuse the `guide.css` classes; do not invent new treatments.
- Figures (check counts, file-class weights) are read from the repo at authoring
  time (`tools/lib/checks.py`, `git ls-files public/`) — keep them accurate when the
  underlying numbers change.

## Fonts / licensing

Set in Klim Type Foundry families, the same woff2 the live site already serves.
If they cannot be embedded in a distributed PDF, substitute Source Serif · Inter
· JetBrains Mono and note the swap on the colophon.
