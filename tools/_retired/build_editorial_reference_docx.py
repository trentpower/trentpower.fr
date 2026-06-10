#!/usr/bin/env python3
"""build_editorial_reference_docx.py — produce a pandoc reference
DOCX that defines named TP styles for the editorial-review export.

Pandoc's `--reference-doc=...` lets us define the visual treatment
of each named paragraph style; the generated review DOCX then
carries the editorial typography (large serif copy as the
protagonist, muted sans metadata, mono keys, restrained oxblood
accent) without depending on a third-party `python-docx` library.

Inputs
- pandoc's default reference.docx, extracted via
  `pandoc --print-default-data-file=reference.docx`.

Output
- tools/editorial-review-reference.docx — same layout, with
  additional `<w:style>` definitions for the TP-* style family.

The result is committed to the repo so the build runs offline.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "tools" / "editorial-review-reference.docx"

# each tp-* style is described by a tiny dataclass-style dict so the
# block of xml is generated programmatically and remains easy to
# tune. fonts are a fallback chain — word respects the first
# available; system fonts are used so the document opens cleanly
# without requiring proprietary face files.
SERIF_PRIMARY = "Iowan Old Style"
SERIF_FALLBACK = "Cambria"
SANS_PRIMARY = "Inter"
SANS_FALLBACK = "Calibri"
MONO_PRIMARY = "JetBrains Mono"
MONO_FALLBACK = "Consolas"

# word measures size in half-points. 28 = 14pt, etc.
TP_STYLES = [
    {
        "id": "TPTitle",
        "name": "TP Title",
        "based": "Title",
        "next": "TPMetadata",
        "rPr": {
            "rFonts": (SERIF_PRIMARY, SERIF_FALLBACK),
            "size": "64",  # 32pt
            "color": "15140F",
            "bold": False,
        },
        "pPr": {"spacingBefore": "0", "spacingAfter": "240"},
    },
    {
        "id": "TPSection",
        "name": "TP Section",
        "based": "Heading1",
        "next": "TPMetadata",
        "rPr": {
            "rFonts": (SERIF_PRIMARY, SERIF_FALLBACK),
            "size": "44",  # 22pt
            "color": "15140F",
            "bold": False,
        },
        "pPr": {"spacingBefore": "720", "spacingAfter": "320", "pageBreakBefore": True},
    },
    {
        "id": "TPSubhead",
        "name": "TP Subhead",
        "based": "Heading2",
        "next": "TPEditableCopy",
        "rPr": {
            "rFonts": (SERIF_PRIMARY, SERIF_FALLBACK),
            "size": "28",  # 14pt
            "color": "15140F",
            "bold": False,
            "italic": False,
        },
        "pPr": {"spacingBefore": "360", "spacingAfter": "80"},
    },
    {
        "id": "TPEditableCopy",
        "name": "TP Editable Copy",
        "based": "Normal",
        "next": "TPEditableCopy",
        "rPr": {
            "rFonts": (SERIF_PRIMARY, SERIF_FALLBACK),
            "size": "28",  # 14pt
            "color": "15140F",
        },
        "pPr": {"spacingBefore": "100", "spacingAfter": "260", "lineSpacing": "320"},
    },
    {
        "id": "TPMetadata",
        "name": "TP Metadata",
        "based": "Normal",
        "next": "TPKey",
        "rPr": {
            "rFonts": (SANS_PRIMARY, SANS_FALLBACK),
            "size": "16",  # 8pt
            "color": "6B655D",
            "caps": True,
            "spacing": "20",  # tracked, in twentieths of a point
        },
        "pPr": {"spacingBefore": "240", "spacingAfter": "20"},
    },
    {
        "id": "TPKey",
        "name": "TP Key",
        "based": "Normal",
        "next": "TPEditableCopy",
        "rPr": {
            "rFonts": (MONO_PRIMARY, MONO_FALLBACK),
            "size": "16",  # 8pt
            "color": "A29A8E",
        },
        "pPr": {"spacingBefore": "0", "spacingAfter": "60"},
    },
    {
        "id": "TPNote",
        "name": "TP Note",
        "based": "Normal",
        "next": "TPMetadata",
        "rPr": {
            "rFonts": (SANS_PRIMARY, SANS_FALLBACK),
            "size": "18",  # 9pt
            "color": "6B655D",
            "italic": True,
        },
        "pPr": {"spacingBefore": "60", "spacingAfter": "200"},
    },
    {
        "id": "TPCover",
        "name": "TP Cover",
        "based": "Normal",
        "next": "TPMetadata",
        "rPr": {
            "rFonts": (SERIF_PRIMARY, SERIF_FALLBACK),
            "size": "24",  # 12pt
            "color": "15140F",
        },
        "pPr": {"spacingBefore": "0", "spacingAfter": "200"},
    },
    {
        "id": "TPEntry",
        "name": "TP Entry",
        "based": "Normal",
        "next": "TPMetadata",
        "rPr": {
            "rFonts": (SERIF_PRIMARY, SERIF_FALLBACK),
            "size": "24",  # 12pt
            "color": "15140F",
        },
        "pPr": {"spacingBefore": "0", "spacingAfter": "0"},
    },
]

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
WR = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)


# editorial folio — header (running banner) and footer (page x of y).
# pandoc respects header/footer references defined in the reference
# document's section properties; the resulting word document inherits
# the same chrome on every page. the visible text is the canonical
# document identity. Page-of-pages is rendered via word field codes
# so both word and libreoffice resolve them at render time.

HEADER_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    f"<w:hdr {WR}>"
    "<w:p>"
    "<w:pPr>"
    '<w:pStyle w:val="Header"/>'
    "<w:tabs>"
    '<w:tab w:val="center" w:pos="4500"/>'
    '<w:tab w:val="right"  w:pos="9000"/>'
    "</w:tabs>"
    "</w:pPr>"
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    "<w:t>trentpower.fr</w:t></w:r>"
    "<w:r><w:tab/></w:r>"
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:i/><w:color w:val="857F75"/></w:rPr>'
    "<w:t>Editorial Copy Review</w:t></w:r>"
    "<w:r><w:tab/></w:r>"
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    '<w:t xml:space="preserve">Edition </w:t></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    "<w:t>2026-05-09</w:t></w:r>"
    "</w:p>"
    "</w:hdr>"
)

FOOTER_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    f"<w:ftr {WR}>"
    "<w:p>"
    "<w:pPr>"
    '<w:pStyle w:val="Footer"/>'
    "<w:tabs>"
    '<w:tab w:val="right" w:pos="9000"/>'
    "</w:tabs>"
    "</w:pPr>"
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:caps/><w:color w:val="9A9388"/>'
    '<w:spacing w:val="30"/></w:rPr>'
    "<w:t>Editorial &#8212; Confidential</w:t></w:r>"
    "<w:r><w:tab/></w:r>"
    # word field codes for page x / y so word + libreoffice
    # resolve dynamically at render time.
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    '<w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    '<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    '<w:fldChar w:fldCharType="end"/></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    '<w:t xml:space="preserve"> / </w:t></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    '<w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    '<w:instrText xml:space="preserve"> NUMPAGES </w:instrText></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Inter" w:hAnsi="Inter"/>'
    '<w:sz w:val="16"/><w:color w:val="9A9388"/></w:rPr>'
    '<w:fldChar w:fldCharType="end"/></w:r>'
    "</w:p>"
    "</w:ftr>"
)


def _xml_style(s: dict) -> str:
    rpr = []
    rprcfg = s.get("rPr", {})
    if "rFonts" in rprcfg:
        primary, fallback = rprcfg["rFonts"]
        rpr.append(
            f'<w:rFonts w:ascii="{primary}" w:hAnsi="{primary}" '
            f'w:eastAsia="{fallback}" w:cs="{fallback}"/>'
        )
    if "size" in rprcfg:
        rpr.append(f'<w:sz w:val="{rprcfg["size"]}"/>')
        rpr.append(f'<w:szCs w:val="{rprcfg["size"]}"/>')
    if "color" in rprcfg:
        rpr.append(f'<w:color w:val="{rprcfg["color"]}"/>')
    if rprcfg.get("bold"):
        rpr.append("<w:b/>")
    else:
        rpr.append('<w:b w:val="0"/>')
    if rprcfg.get("italic"):
        rpr.append("<w:i/>")
    if rprcfg.get("caps"):
        rpr.append("<w:caps/>")
    if "spacing" in rprcfg:
        rpr.append(f'<w:spacing w:val="{rprcfg["spacing"]}"/>')
    rpr_xml = "<w:rPr>" + "".join(rpr) + "</w:rPr>"

    ppr = []
    pprcfg = s.get("pPr", {})
    if pprcfg.get("pageBreakBefore"):
        ppr.append("<w:pageBreakBefore/>")
    spacing_attrs = []
    if "spacingBefore" in pprcfg:
        spacing_attrs.append(f'w:before="{pprcfg["spacingBefore"]}"')
    if "spacingAfter" in pprcfg:
        spacing_attrs.append(f'w:after="{pprcfg["spacingAfter"]}"')
    if "lineSpacing" in pprcfg:
        spacing_attrs.append(f'w:line="{pprcfg["lineSpacing"]}" w:lineRule="auto"')
    if spacing_attrs:
        ppr.append(f"<w:spacing {' '.join(spacing_attrs)}/>")
    ppr.append("<w:keepLines/>")
    ppr_xml = "<w:pPr>" + "".join(ppr) + "</w:pPr>"

    return (
        f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{s["id"]}">'
        f'<w:name w:val="{s["name"]}"/>'
        f'<w:basedOn w:val="{s["based"]}"/>'
        f'<w:next w:val="{s["next"]}"/>'
        f"<w:qFormat/>"
        f"{ppr_xml}{rpr_xml}"
        f"</w:style>"
    )


def main() -> int:
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        print("FAIL: pandoc not found — cannot extract default reference.docx", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = pathlib.Path(tmp_s)
        ref_path = tmp / "pandoc-default.docx"
        # pandoc emits the binary on stdout; capture it.
        proc = subprocess.run(
            [pandoc, "--print-default-data-file=reference.docx"],
            check=True,
            capture_output=True,
        )
        ref_path.write_bytes(proc.stdout)

        # read every entry, mutate styles.xml.
        entries: list[tuple[str, bytes]] = []
        with zipfile.ZipFile(ref_path, "r") as z:
            for name in z.namelist():
                entries.append((name, z.read(name)))

        new_entries = []
        for name, data in entries:
            if name == "word/styles.xml":
                xml = data.decode("utf-8")
                # append our TP-styles right before the closing </w:styles>.
                tp_styles_xml = "".join(_xml_style(s) for s in TP_STYLES)
                xml = xml.replace("</w:styles>", tp_styles_xml + "</w:styles>")
                data = xml.encode("utf-8")
            elif name == "[Content_Types].xml":
                xml = data.decode("utf-8")
                # register the header / footer parts.
                add = (
                    '<Override PartName="/word/header1.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument'
                    '.wordprocessingml.header+xml"/>'
                    '<Override PartName="/word/footer1.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument'
                    '.wordprocessingml.footer+xml"/>'
                )
                xml = xml.replace("</Types>", add + "</Types>")
                data = xml.encode("utf-8")
            elif name == "word/_rels/document.xml.rels":
                xml = data.decode("utf-8")
                # add relationships for header and footer. use rids
                # that won't collide with pandoc's defaults — high
                # numbers for safety.
                add = (
                    '<Relationship Id="rIdEdHdr" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/'
                    '2006/relationships/header" Target="header1.xml"/>'
                    '<Relationship Id="rIdEdFtr" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/'
                    '2006/relationships/footer" Target="footer1.xml"/>'
                )
                xml = xml.replace("</Relationships>", add + "</Relationships>")
                data = xml.encode("utf-8")
            elif name == "word/document.xml":
                xml = data.decode("utf-8")
                # inject header + footer references into the section
                # properties so every page carries the editorial
                # chrome. pandoc preserves <w:sectPr> from the
                # reference doc when rendering.
                section_chrome = (
                    '<w:headerReference w:type="default" r:id="rIdEdHdr"/>'
                    '<w:footerReference w:type="default" r:id="rIdEdFtr"/>'
                )
                # replace the empty <w:sectPr /> with one carrying
                # our references. tolerate either self-closed or
                # paired forms.
                if "<w:sectPr />" in xml:
                    xml = xml.replace(
                        "<w:sectPr />",
                        f"<w:sectPr>{section_chrome}</w:sectPr>",
                    )
                elif "<w:sectPr/>" in xml:
                    xml = xml.replace(
                        "<w:sectPr/>",
                        f"<w:sectPr>{section_chrome}</w:sectPr>",
                    )
                else:
                    # Already-populated sectpr — inject the references
                    # at the start so they take effect.
                    xml = xml.replace(
                        "<w:sectPr>",
                        f"<w:sectPr>{section_chrome}",
                        1,
                    )
                data = xml.encode("utf-8")
            new_entries.append((name, data))

        # append the new header / footer xml parts.
        new_entries.append(("word/header1.xml", HEADER_XML.encode("utf-8")))
        new_entries.append(("word/footer1.xml", FOOTER_XML.encode("utf-8")))

        OUT.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in new_entries:
                z.writestr(name, data)

    print(
        f"  → {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB · {len(TP_STYLES)} TP-* styles)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
