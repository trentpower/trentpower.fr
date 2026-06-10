# tools/_retired/

Retired one-off and superseded scripts, kept for reference only.

**Nothing here is part of the build, gate, lint, or deploy pipeline.** These
files are not invoked by `build.sh`, `checks.py`, `gate.py`, `lint.py`, any
workflow, or any active tool. They are preserved because they document how a
past migration or generation step was performed.

| File | Why archived |
|---|---|
| `build_editorial_reference_docx.py` | Superseded by `tools/build/generate_editorial_binaries.py`. |
| `import_og_pngs.py` | One-time OG-image import; not re-run by the pipeline. |
| `extract_from_data_i18n.py` | One-time phase-A migration bridge (data-i18n → content YAML); the migration is complete. |
| `generate_build_report.py` | Superseded build-report writer; `build.sh` no longer invokes it (the ceremony transcript replaced it). |
