<!-- pull request · trentpower.fr public record -->

## What changes

<!-- One paragraph. What the reader of the public record gains. -->

## Promotion path

- [ ] `feature/*` → `preprod` (release candidate)
- [ ] `preprod` → `main` (promotion — same bytes, no rebase, no rebuild)

## Checklist

- [ ] `bash tools/build/build.sh --check` passes locally
- [ ] `python3 tools/quality/gate.py --all` is green (all blocking checks)
- [ ] New or changed tooling behaviour has tests in `tools/quality/tests/`
      (`python3 -m unittest discover -s tools/quality/tests`)
- [ ] Commits are authored `Trent Power <trent@trentpower.fr>` and signed
- [ ] Commit messages carry no attribution trailers (the git-metadata gate blocks them)
- [ ] No licensed font binaries added to version control
- [ ] If `public/` changed: edition, integrity manifest and signature are coherent
- [ ] Generated public files were changed through their sources, never by hand
