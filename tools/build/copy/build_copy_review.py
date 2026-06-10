#!/usr/bin/env python3
"""Build the copywriter-focused review document from content/en/ YAML sources.

This is the *editing* view of the canonical copy: shared copy first, then
per-page body, print and metadata sections, with every shared reference clearly
annotated. (It replaced the retired "System B" editorial-copy-review.* exports,
which re-scraped rendered HTML for the same strings.)

Outputs:
  public/editorial/copy-review.md
  public/editorial/copy-review.html
"""

from __future__ import annotations

import html
import sys
from collections import OrderedDict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

sys.path.insert(
    0,
    str(
        next(
            _a
            for _a in __import__("pathlib").Path(__file__).resolve().parents
            if _a.name == "tools"
        )
        / "lib"
    ),
)
from build_copy import (  # noqa: E402
    ALIAS_SHARED_KEYS,
    CONTENT_DIR,
    EMITTED_SHARED_SURFACES,
    PAGE_SURFACES,
    REF_RE,
    ROOT,
)

OUT_DIR = ROOT / "public" / "editorial"
MD_PATH = OUT_DIR / "copy-review.md"
HTML_PATH = OUT_DIR / "copy-review.html"


def load_yaml(path: Path):
    with path.open() as f:
        return yaml.safe_load(f) or {}


def walk_leaves(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_leaves(v, path + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_leaves(v, path + (f"[{i}]",))
    elif isinstance(node, str):
        yield path, node


def resolve_with_refs(node, shared, path=()):
    """Return list of (dotted_path, raw_value, resolved_value, ref_targets[])."""
    out = []
    for p, raw in walk_leaves(node, path):
        refs = REF_RE.findall(raw)
        resolved = raw
        if refs:
            for ref in refs:
                parts = ref.split(".")
                cur = shared
                ok = True
                for piece in parts:
                    if isinstance(cur, dict) and piece in cur:
                        cur = cur[piece]
                    else:
                        ok = False
                        break
                if ok and isinstance(cur, str):
                    resolved = resolved.replace("{{ shared." + ref + " }}", cur)
                    resolved = resolved.replace("{{shared." + ref + "}}", cur)
        out.append((p, raw, resolved, refs))
    return out


# ---------- Markdown rendering ----------


def md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def render_md(shared, pages):
    lines = []
    lines.append("# Copy review — English")
    lines.append("")
    lines.append(
        "> Edit YAML in `content/en/`. The English copy register is regenerated from these YAMLs on every build; never edit the register directly."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # SHARED
    lines.append("## 1. Shared copy — edit here once, used across the site")
    lines.append("")
    for top in shared:
        if top in ALIAS_SHARED_KEYS:
            lines.append(f"### Shared · `{top}`")
            lines.append("")
            lines.append("Reference these from page YAMLs as `{{ shared." + top + ".KEY }}`.")
            lines.append("")
            lines.append("| Key | Value |")
            lines.append("|---|---|")
            for p, raw, _resolved, _ in resolve_with_refs(shared[top], shared, (top,)):
                lines.append(f"| `shared.{'.'.join(p)}` | {md_escape(raw)} |")
            lines.append("")
    for top in EMITTED_SHARED_SURFACES:
        if top not in shared:
            continue
        lines.append(f"### Site chrome · `{top}`")
        lines.append("")
        lines.append(f"Emitted directly to `en.{top}` in `strings.json`.")
        lines.append("")
        lines.append("| Key | Value |")
        lines.append("|---|---|")
        for p, raw, _, _ in resolve_with_refs(shared[top], shared, (top,)):
            lines.append(f"| `{'.'.join(p)}` | {md_escape(raw)} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # PAGE-BODY
    lines.append("## 2. Page-specific copy")
    lines.append("")
    for page_name in PAGE_SURFACES:
        page = pages[page_name]
        lines.append(f"### {page_name.capitalize()}")
        lines.append("")
        body_rows = _collect_section(
            page, shared, exclude_top_keys={"meta"}, exclude_sub_key="print"
        )
        if not body_rows:
            lines.append("_(no page-body fields)_")
            lines.append("")
            continue
        lines.append("| Key | Value | Resolved from |")
        lines.append("|---|---|---|")
        for path, _raw, resolved, refs in body_rows:
            value_cell = md_escape(resolved) if not refs else md_escape(resolved)
            ref_cell = ", ".join(f"`shared.{r}`" for r in refs) if refs else ""
            lines.append(f"| `{'.'.join(path)}` | {value_cell} | {ref_cell} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # PRINT
    lines.append("## 3. Print copy")
    lines.append("")
    for page_name in PAGE_SURFACES:
        page = pages[page_name]
        lines.append(f"### {page_name.capitalize()} · print profile")
        lines.append("")
        print_rows = _collect_print(page, shared)
        if not print_rows:
            lines.append("_(no print fields)_")
            lines.append("")
            continue
        lines.append("| Key | Value | Resolved from |")
        lines.append("|---|---|---|")
        for path, _raw, resolved, refs in print_rows:
            value_cell = md_escape(resolved)
            ref_cell = ", ".join(f"`shared.{r}`" for r in refs) if refs else ""
            lines.append(f"| `{'.'.join(path)}` | {value_cell} | {ref_cell} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # METADATA
    lines.append("## 4. Metadata copy (page <title>, OG, social previews)")
    lines.append("")
    for page_name in PAGE_SURFACES:
        page = pages[page_name]
        meta = page.get("meta") or {}
        if not meta:
            continue
        lines.append(f"### {page_name.capitalize()} · meta")
        lines.append("")
        lines.append("| Key | Value | Resolved from |")
        lines.append("|---|---|---|")
        for path, _raw, resolved, refs in resolve_with_refs(meta, shared, ("meta",)):
            ref_cell = ", ".join(f"`shared.{r}`" for r in refs) if refs else ""
            lines.append(f"| `{'.'.join(path)}` | {md_escape(resolved)} | {ref_cell} |")
        lines.append("")

    return "\n".join(lines) + "\n"


def _collect_section(page, shared, exclude_top_keys, exclude_sub_key):
    rows = []
    for top, val in page.items():
        if top in exclude_top_keys:
            continue
        if isinstance(val, dict):
            non_excluded = OrderedDict((k, v) for k, v in val.items() if k != exclude_sub_key)
            if non_excluded:
                rows.extend(resolve_with_refs(non_excluded, shared, (top,)))
        else:
            for path, raw, resolved, refs in resolve_with_refs(val, shared, (top,)):
                rows.append((path, raw, resolved, refs))
    return rows


def _collect_print(page, shared):
    rows = []
    for top, val in page.items():
        if not isinstance(val, dict):
            continue
        if "print" in val:
            rows.extend(resolve_with_refs(val["print"], shared, (top, "print")))
    return rows


# ---------- HTML rendering ----------

HTML_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Copy review — English</title>
<style>
  :root { color-scheme: light; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
         max-width: 980px; margin: 2rem auto; padding: 0 1.25rem; line-height: 1.55; color: #222; }
  h1 { border-bottom: 2px solid #222; padding-bottom: .5rem; }
  h2 { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #ccc; }
  h3 { margin-top: 2rem; }
  .banner { background: #fff7e6; border-left: 4px solid #d4a000; padding: .75rem 1rem; margin: 1rem 0; }
  table { border-collapse: collapse; width: 100%; margin: .75rem 0 1.5rem; font-size: 14px; }
  th, td { border: 1px solid #d8d8d8; padding: .4rem .55rem; vertical-align: top; text-align: left; }
  th { background: #f4f4f4; }
  td.key { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: nowrap; color: #555; width: 30%; }
  td.ref { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #888; font-size: 12px; width: 22%; }
  code { background: #f0f0f0; padding: 0 .25rem; border-radius: 3px; }
  .note { color: #666; font-size: 14px; }
</style>
</head>
<body>
"""

HTML_FOOT = "\n</body>\n</html>\n"


def render_html(shared, pages):
    parts = [HTML_HEAD]
    parts.append("<h1>Copy review — English</h1>")
    parts.append(
        '<div class="banner"><strong>Editing model:</strong> '
        "Edit YAML in <code>content/en/</code>. The English copy "
        "register is regenerated from these YAMLs on every build; "
        "never edit the register directly.</div>"
    )

    # SHARED
    parts.append("<h2>1. Shared copy — edit here once, used across the site</h2>")
    for top in shared:
        if top in ALIAS_SHARED_KEYS:
            parts.append(f"<h3>Shared · <code>{top}</code></h3>")
            parts.append(
                f'<p class="note">Reference from page YAMLs as <code>{{{{ shared.{top}.KEY }}}}</code>.</p>'
            )
            parts.append(
                _html_table(
                    shared[top], shared, (top,), include_ref_col=False, key_prefix=f"shared.{top}"
                )
            )
    for top in EMITTED_SHARED_SURFACES:
        if top not in shared:
            continue
        parts.append(f"<h3>Site chrome · <code>{top}</code></h3>")
        parts.append(
            f'<p class="note">Emitted directly to <code>en.{top}</code> in <code>strings.json</code>.</p>'
        )
        parts.append(_html_table(shared[top], shared, (top,), include_ref_col=False))

    # PAGE-BODY
    parts.append("<h2>2. Page-specific copy</h2>")
    for page_name in PAGE_SURFACES:
        page = pages[page_name]
        parts.append(f"<h3>{html.escape(page_name.capitalize())}</h3>")
        body_rows = _collect_section(
            page, shared, exclude_top_keys={"meta"}, exclude_sub_key="print"
        )
        parts.append(_html_table_rows(body_rows))

    # PRINT
    parts.append("<h2>3. Print copy</h2>")
    for page_name in PAGE_SURFACES:
        page = pages[page_name]
        parts.append(f"<h3>{html.escape(page_name.capitalize())} · print profile</h3>")
        parts.append(_html_table_rows(_collect_print(page, shared)))

    # METADATA
    parts.append("<h2>4. Metadata copy (page &lt;title&gt;, OG, social previews)</h2>")
    for page_name in PAGE_SURFACES:
        page = pages[page_name]
        meta = page.get("meta") or {}
        if not meta:
            continue
        parts.append(f"<h3>{html.escape(page_name.capitalize())} · meta</h3>")
        parts.append(_html_table(meta, shared, ("meta",), include_ref_col=True))

    parts.append(HTML_FOOT)
    return "".join(parts)


def _html_table(node, shared, base_path, include_ref_col, key_prefix=None):
    rows = resolve_with_refs(node, shared, base_path)
    return _html_table_rows(rows, include_ref_col=include_ref_col, key_prefix=key_prefix)


def _html_table_rows(rows, include_ref_col=True, key_prefix=None):
    if not rows:
        return '<p class="note"><em>(no fields)</em></p>'
    head = "<thead><tr><th>Key</th><th>Value</th>"
    if include_ref_col:
        head += "<th>Resolved from</th>"
    head += "</tr></thead>"
    body = ["<tbody>"]
    for path, _raw, resolved, refs in rows:
        key_str = ".".join(path)
        if key_prefix:
            key_str = f"{key_prefix}.{'.'.join(path[1:])}" if len(path) > 1 else key_prefix
        value_html = html.escape(resolved)
        if refs:
            value_html += "  " + " ".join(
                f'<span class="ref">← {{{{ shared.{r} }}}}</span>' for r in refs
            )
        ref_cell = ""
        if include_ref_col:
            ref_cell = '<td class="ref">'
            if refs:
                ref_cell += ", ".join(f"shared.{r}" for r in refs)
            ref_cell += "</td>"
        body.append(
            f'<tr><td class="key">{html.escape(key_str)}</td><td>{value_html}</td>{ref_cell}</tr>'
        )
    body.append("</tbody>")
    return "<table>" + head + "".join(body) + "</table>"


def main():
    shared = load_yaml(CONTENT_DIR / "shared.yml")
    pages = OrderedDict()
    for page_name in PAGE_SURFACES:
        pages[page_name] = load_yaml(CONTENT_DIR / "pages" / f"{page_name}.yml")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    md = render_md(shared, pages)
    MD_PATH.write_text(md, encoding="utf-8")

    html_doc = render_html(shared, pages)
    HTML_PATH.write_text(html_doc, encoding="utf-8")

    print(
        f"copy_review: wrote {MD_PATH.relative_to(ROOT)} and {HTML_PATH.relative_to(ROOT)}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
