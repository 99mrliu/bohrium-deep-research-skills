#!/usr/bin/env python3
"""build_deck.py - assemble an EDITABLE academic deck from an audited plan.

Fail-closed: refuses to build when the number audit is not PASS.

Pure-stdlib OOXML (pptx) writer - no python-pptx, no network. Slide kinds:
  * title   big title + subtitle bullets
  * text    title + bullet paragraphs
  * table   NATIVE pptx table (<a:tbl> in a graphicFrame) filled verbatim from
            the referenced mined CSV - editable in PowerPoint/WPS, header row
            bold, theme-colored header fill
  * chart   replotted chart PNG + footer "Replotted from Table N, p.X - values
            verbatim" (from the chart's provenance json)
  * figure  verified crop PNG + original caption line + "Source: Figure N, p.X"
Every slide gets a speaker-notes part (real notesSlide XML).
Slide size is adopted from --template's ppt/presentation.xml sldSz when given
(full theme inheritance is out of scope - declare it in exceptions).

Also copies provenance artifacts into the output dir:
  tables/ (mined CSVs + tables.json), charts/ (PNGs + provenance jsons).
When soffice is on PATH: exports /app/output/presentation.pdf and renders
pdftoppm previews into /app/output/preview/.

Invocation:
  python3 /skills/weekly-skill/scripts/build_deck.py \
    --plan work/plan.json --audit /app/output/number_audit.json \
    [--template /input/target-template.pptx]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from xml.sax.saxutils import escape

EMU = 914400
NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
TABLE_STYLE_URI = "http://schemas.openxmlformats.org/drawingml/2006/table"


def fail(msg: str, code: int = 1) -> "None":
    print(f"[build_deck] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def emu(inches: float) -> int:
    return int(round(inches * EMU))


def png_size(path: str):
    with open(path, "rb") as f:
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            fail(f"not a PNG: {path}")
        f.read(4)
        if f.read(4) != b"IHDR":
            fail(f"bad PNG (no IHDR): {path}")
        w, h = struct.unpack(">II", f.read(8))
    return w, h


# ---------------------------------------------------------------- shape XML
def tx_body(paras) -> str:
    """paras: list of (text, size_pt, bold, color_hex, bullet) tuples."""
    out = []
    for text, size, bold, color, bullet in paras:
        ppr = ""
        if bullet:
            ppr = ('<a:pPr marL="228600" indent="-228600">'
                   '<a:buFont typeface="Arial"/><a:buChar char="\u2022"/>'
                   '</a:pPr>')
        b = ' b="1"' if bold else ""
        out.append(
            f'<a:p>{ppr}<a:r><a:rPr lang="en-US" sz="{int(size * 100)}"{b}>'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr>'
            f'<a:t>{escape(text)}</a:t></a:r></a:p>')
    return "".join(out) or '<a:p><a:endParaRPr lang="en-US"/></a:p>'


def textbox(sid: int, name: str, x, y, cx, cy, paras) -> str:
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{escape(name)}"/>'
        f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/>'
        f'</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'<p:txBody><a:bodyPr wrap="square" lIns="45720" tIns="27432" '
        f'rIns="45720" bIns="27432"/><a:lstStyle/>{tx_body(paras)}'
        f'</p:txBody></p:sp>')


def picture(sid: int, name: str, rid: str, x, y, cx, cy) -> str:
    return (
        f'<p:pic><p:nvPicPr><p:cNvPr id="{sid}" name="{escape(name)}"/>'
        f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        f'<p:nvPr/></p:nvPicPr>'
        f'<p:blipFill><a:blip r:embed="{rid}"/>'
        f'<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/>'
        f'</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'</p:pic>')


def table_frame(sid: int, name: str, x, y, cx, cy, header, rows,
                header_fill="1F4E79") -> str:
    ncols = len(header)
    col_w = cx // ncols
    n_rows = 1 + len(rows)
    row_h = max(emu(0.32), cy // n_rows)

    def cell(text, bold, color, fill):
        fill_xml = (f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
                    if fill else '<a:noFill/>')
        return (
            f'<a:tc><a:txBody><a:bodyPr/><a:lstStyle/><a:p>'
            f'<a:r><a:rPr lang="en-US" sz="1300"{(" b=\"1\"" if bold else "")}>'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr>'
            f'<a:t>{escape(text)}</a:t></a:r></a:p></a:txBody>'
            f'<a:tcPr marL="45720" marR="45720" marT="18288" marB="18288" '
            f'anchor="ctr">{fill_xml}</a:tcPr></a:tc>')

    grid = "".join(f'<a:gridCol w="{col_w}"/>' for _ in range(ncols))
    trs = [f'<a:tr h="{row_h}">' + "".join(
        cell(h, True, "FFFFFF", header_fill) for h in header) + "</a:tr>"]
    for i, r in enumerate(rows):
        fill = "DCE6F1" if i % 2 == 0 else "FFFFFF"
        trs.append(f'<a:tr h="{row_h}">' + "".join(
            cell(c, False, "1A1A1A", fill) for c in r) + "</a:tr>")
    return (
        f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{sid}" '
        f'name="{escape(name)}"/><p:cNvGraphicFramePr>'
        f'<a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>'
        f'<p:nvPr/></p:nvGraphicFramePr>'
        f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="{TABLE_STYLE_URI}">'
        f'<a:tbl><a:tblPr firstRow="1" bandRow="1"/>'
        f'<a:tblGrid>{grid}</a:tblGrid>{"".join(trs)}'
        f'</a:tbl></a:graphicData></a:graphic></p:graphicFrame>')


# ------------------------------------------------------------- package parts
def content_types(n_slides: int) -> str:
    overrides = [
        ('/ppt/presentation.xml', 'presentationml.presentation.main+xml'),
        ('/ppt/slideMasters/slideMaster1.xml', 'presentationml.slideMaster+xml'),
        ('/ppt/slideLayouts/slideLayout1.xml', 'presentationml.slideLayout+xml'),
        ('/ppt/notesMasters/notesMaster1.xml', 'presentationml.notesMaster+xml'),
        ('/ppt/theme/theme1.xml', 'theme+xml'),
        ('/ppt/theme/theme2.xml', 'theme+xml'),
        ('/docProps/core.xml', 'core-properties+xml'),
        ('/docProps/app.xml', 'extended-properties+xml'),
    ]
    for i in range(1, n_slides + 1):
        overrides.append((f'/ppt/slides/slide{i}.xml',
                          'presentationml.slide+xml'))
        overrides.append((f'/ppt/notesSlides/notesSlide{i}.xml',
                          'presentationml.notesSlide+xml'))
    o = "".join(f'<Override PartName="{p}" ContentType="application/vnd.'
                f'openxmlformats-officedocument.{c}"/>' for p, c in overrides)
    return (f'{XML_HEAD}<Types xmlns="http://schemas.openxmlformats.org/package'
            f'/2006/content-types"><Default Extension="rels" ContentType="appl'
            f'ication/vnd.openxmlformats-package.relationships+xml"/>'
            f'<Default Extension="xml" ContentType="application/xml"/>'
            f'<Default Extension="png" ContentType="image/png"/>{o}</Types>')


def rels_xml(rels) -> str:
    body = "".join(
        f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/{typ}" Target="{escape(tgt)}"/>'
        for rid, typ, tgt in rels)
    return (f'{XML_HEAD}<Relationships xmlns="http://schemas.openxmlformats.'
            f'org/package/2006/relationships">{body}</Relationships>')


THEME = (
    f'{XML_HEAD}<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/'
    f'2006/main" name="TableRebind"><a:themeElements>'
    f'<a:clrScheme name="TableRebind">'
    f'<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
    f'<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
    f'<a:dk2><a:srgbClr val="1F4E79"/></a:dk2>'
    f'<a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
    f'<a:accent1><a:srgbClr val="1F4E79"/></a:accent1>'
    f'<a:accent2><a:srgbClr val="C0504D"/></a:accent2>'
    f'<a:accent3><a:srgbClr val="9BBB59"/></a:accent3>'
    f'<a:accent4><a:srgbClr val="8064A2"/></a:accent4>'
    f'<a:accent5><a:srgbClr val="4BACC6"/></a:accent5>'
    f'<a:accent6><a:srgbClr val="F79646"/></a:accent6>'
    f'<a:hlink><a:srgbClr val="0000FF"/></a:hlink>'
    f'<a:folHlink><a:srgbClr val="800080"/></a:folHlink></a:clrScheme>'
    f'<a:fontScheme name="TableRebind"><a:majorFont><a:latin typeface="Calibri'
    f'"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont>'
    f'<a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/>'
    f'</a:minorFont></a:fontScheme>'
    f'<a:fmtScheme name="TableRebind">'
    + '<a:fillStyleLst>' + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3 + '</a:fillStyleLst>'
    + '<a:lnStyleLst>' + '<a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>' * 3 + '</a:lnStyleLst>'
    + '<a:effectStyleLst>' + '<a:effectStyle><a:effectLst/></a:effectStyle>' * 3 + '</a:effectStyleLst>'
    + '<a:bgFillStyleLst>' + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3 + '</a:bgFillStyleLst>'
    + f'</a:fmtScheme></a:themeElements></a:theme>')

GRP_SP_TREE = (
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')

CLR_MAP = ('<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
           'accent2="accent2" accent3="accent3" accent4="accent4" '
           'accent5="accent5" accent6="accent6" hlink="hlink" '
           'folHlink="folHlink"/>')

SLIDE_MASTER = (
    f'{XML_HEAD}<p:sldMaster {NS}><p:cSld><p:bg><p:bgPr>'
    f'<a:solidFill><a:schemeClr val="bg1"/></a:solidFill><a:effectLst/>'
    f'</p:bgPr></p:bg><p:spTree>{GRP_SP_TREE}</p:spTree></p:cSld>{CLR_MAP}'
    f'<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/>'
    f'</p:sldLayoutIdLst><p:txStyles>'
    f'<p:titleStyle><a:lvl1pPr><a:defRPr sz="3200" b="1"/></a:lvl1pPr></p:titleStyle>'
    f'<p:bodyStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:bodyStyle>'
    f'<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle>'
    f'</p:txStyles></p:sldMaster>')

SLIDE_LAYOUT = (
    f'{XML_HEAD}<p:sldLayout {NS}><p:cSld name="Blank"><p:spTree>'
    f'{GRP_SP_TREE}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/>'
    f'</p:clrMapOvr></p:sldLayout>')

NOTES_MASTER = (
    f'{XML_HEAD}<p:notesMaster {NS}><p:cSld><p:spTree>{GRP_SP_TREE}'
    f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder"/>'
    f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
    f'<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
    f'<p:spPr><a:xfrm><a:off x="685800" y="4400550"/>'
    f'<a:ext cx="5486400" cy="3600450"/></a:xfrm>'
    f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
    f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/>'
    f'</a:p></p:txBody></p:sp></p:spTree></p:cSld>{CLR_MAP}</p:notesMaster>')


def slide_xml(shapes: str) -> str:
    return (f'{XML_HEAD}<p:sld {NS}><p:cSld><p:spTree>{GRP_SP_TREE}{shapes}'
            f'</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/>'
            f'</p:clrMapOvr></p:sld>')


def notes_xml(text: str) -> str:
    paras = "".join(
        f'<a:p><a:r><a:rPr lang="en-US" sz="1200"/><a:t>{escape(line)}</a:t>'
        f'</a:r></a:p>' for line in text.split("\n") if line.strip())
    return (
        f'{XML_HEAD}<p:notes {NS}><p:cSld><p:spTree>{GRP_SP_TREE}'
        f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder"/>'
        f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        f'<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="685800" y="4400550"/>'
        f'<a:ext cx="5486400" cy="3600450"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        f'<p:txBody><a:bodyPr/><a:lstStyle/>{paras or "<a:p/>"}'
        f'</p:txBody></p:sp></p:spTree></p:cSld><p:clrMapOvr>'
        f'<a:masterClrMapping/></p:clrMapOvr></p:notes>')


# ------------------------------------------------------------------- builder
class Deck:
    def __init__(self, cx: int, cy: int):
        self.cx, self.cy = cx, cy
        self.slides = []          # list of dict(shapes, rels, notes)
        self.media = {}           # path -> media name
        self.sid = 10

    def next_id(self):
        self.sid += 1
        return self.sid

    def add_media(self, path: str) -> str:
        if path not in self.media:
            self.media[path] = f"image{len(self.media) + 1}.png"
        return self.media[path]

    def add_slide(self, shapes: str, rels, notes: str):
        self.slides.append({"shapes": shapes, "rels": rels, "notes": notes})

    def fit(self, path, box_x, box_y, box_cx, box_cy):
        w, h = png_size(path)
        scale = min(box_cx / w, box_cy / h)
        cx, cy = int(w * scale), int(h * scale)
        return box_x + (box_cx - cx) // 2, box_y + (box_cy - cy) // 2, cx, cy


def main() -> None:
    ap = argparse.ArgumentParser(description="Build editable pptx from audited plan.")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--template", default=None)
    args = ap.parse_args()

    work = os.environ.get("CASE_WORK_DIR", "/app/work")
    out = os.environ.get("CASE_OUTPUT_DIR", "/app/output")
    os.makedirs(out, exist_ok=True)

    # ---- fail closed on audit
    with open(args.audit, encoding="utf-8") as f:
        audit = json.load(f)
    if audit.get("overall") != "PASS":
        fail(f"number audit is {audit.get('overall')!r}, not PASS; "
             f"refusing to build - fix the plan, not the checker")
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    tables = figures = []
    for name, var in (("tables.json", "tables"), ("figures.json", "figures")):
        p = os.path.join(work, name)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                if var == "tables":
                    tables = json.load(f)
                else:
                    figures = json.load(f)

    # ---- slide size from template
    cx, cy = 12192000, 6858000  # 16:9 default
    if args.template:
        try:
            with zipfile.ZipFile(args.template) as z:
                pres = z.read("ppt/presentation.xml").decode("utf-8")
            m = re.search(r'<p:sldSz[^>]*cx="(\d+)"[^>]*cy="(\d+)"', pres)
            if m:
                cx, cy = int(m.group(1)), int(m.group(2))
                print(f"[build_deck] slide size adopted from template: "
                      f"{cx}x{cy} EMU (theme inheritance out of scope)")
        except Exception as e:  # noqa: BLE001 - degrade, do not crash
            print(f"[build_deck] WARNING: could not read template "
                  f"({e}); using default 16:9 size")

    deck = Deck(cx, cy)
    margin = emu(0.6)
    content_w = cx - 2 * margin
    title_h = emu(0.9)

    def title_shape(txt):
        return textbox(deck.next_id(), "Title", margin, emu(0.25),
                       content_w, title_h, [(txt, 26, True, "1F4E79", False)])

    for slide in plan.get("slides", []):
        kind = slide.get("kind", "text")
        title = slide.get("title", "")
        bullets = list(slide.get("bullets", []))
        notes = [f"kind: {kind}", slide.get("source_line", "")]
        shapes, rels = "", [("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml")]
        rid_n = 1

        def add_pic(path, box):
            nonlocal rid_n, shapes
            media = deck.add_media(path)
            rid_n += 1
            rels.append((f"rId{rid_n}", "image", f"../media/{media}"))
            x, y, w, h = deck.fit(path, *box)
            shapes_local = picture(deck.next_id(), os.path.basename(path),
                                   f"rId{rid_n}", x, y, w, h)
            return shapes_local

        if kind == "title":
            paras = [(title, 40, True, "1F4E79", False)]
            paras += [(b, 18, False, "333333", False) for b in bullets]
            shapes += textbox(deck.next_id(), "TitleBlock", margin,
                              cy // 2 - emu(1.2), content_w, emu(2.6), paras)
        elif kind in ("text",):
            shapes += title_shape(title)
            shapes += textbox(deck.next_id(), "Bullets", margin, emu(1.35),
                              content_w, cy - emu(1.8),
                              [(b, 18, False, "1A1A1A", True) for b in bullets])
        elif kind == "table":
            tref = slide.get("table_ref")
            rec = next((t for t in tables if t["table_id"] == tref), None)
            if not rec or not rec.get("csv_path") or \
                    not os.path.isfile(rec["csv_path"]):
                fail(f"slide {slide.get('id')}: table_ref {tref!r} unresolved")
            with open(rec["csv_path"], encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))
            header, data = rows[0], rows[1:]
            shapes += title_shape(title)
            tbl_h = min(cy - emu(2.0), emu(0.4) * (len(data) + 1))
            shapes += table_frame(deck.next_id(), f"NativeTable-{tref}",
                                  margin, emu(1.5), content_w, tbl_h,
                                  header, data)
            footer = f"Native editable table - values verbatim from {rec['caption'].split(':')[0]}, p.{rec['page']}"
            shapes += textbox(deck.next_id(), "TableFooter", margin,
                              cy - emu(0.55), content_w, emu(0.4),
                              [(footer, 10, False, "555555", False)])
            if bullets:
                notes.append("bullets: " + " | ".join(bullets))
            notes.append(f"table source: {rec['csv_path']} "
                         f"({len(data)} data rows, mined verbatim)")
        elif kind == "chart":
            cref = slide.get("chart_ref")
            png = os.path.join(work, "charts", f"{cref}.png")
            prov_p = os.path.join(work, "charts", f"{cref}.provenance.json")
            if not os.path.isfile(png) or not os.path.isfile(prov_p):
                fail(f"slide {slide.get('id')}: chart_ref {cref!r} unresolved")
            with open(prov_p, encoding="utf-8") as f:
                prov = json.load(f)
            shapes += title_shape(title)
            shapes += add_pic(png, (margin, emu(1.3), content_w, cy - emu(2.3)))
            footer = (f"Replotted from {prov.get('table_label', prov['csv'])}, "
                      f"p.{prov.get('page', '?')} - values verbatim")
            shapes += textbox(deck.next_id(), "ChartFooter", margin,
                              cy - emu(0.85), content_w, emu(0.35),
                              [(footer, 11, False, "555555", False)])
            if bullets:
                shapes += textbox(deck.next_id(), "ChartBullets", margin,
                                  cy - emu(1.6), content_w, emu(0.65),
                                  [(b, 12, False, "1A1A1A", True) for b in bullets])
            notes.append(f"chart provenance: {json.dumps(prov['rows_used'])}")
        elif kind == "figure":
            fref = slide.get("figure_ref")
            rec = next((g for g in figures if g["fig_id"] == fref), None)
            if not rec or not os.path.isfile(rec.get("crop_path", "")):
                fail(f"slide {slide.get('id')}: figure_ref {fref!r} unresolved")
            shapes += title_shape(title)
            shapes += add_pic(rec["crop_path"],
                              (margin, emu(1.3), content_w, cy - emu(2.6)))
            num = fref.split("-", 1)[1]
            shapes += textbox(
                deck.next_id(), "FigCaption", margin, cy - emu(1.2),
                content_w, emu(0.8),
                [(rec["caption"], 11, True, "333333", False),
                 (f"Source: Figure {num}, p.{rec['page']}", 10, False,
                  "555555", False)])
            notes.append(f"figure crop: {rec['crop_path']} "
                         f"(classification: {rec.get('classification')})")
        else:
            fail(f"slide {slide.get('id')}: unknown kind {kind!r}")

        deck.add_slide(shapes, rels, "\n".join(n for n in notes if n))

    # ---- write package
    pptx_path = os.path.join(out, "presentation.pptx")
    n = len(deck.slides)
    if n == 0:
        fail("plan has no slides")
    pres_rels = [("rId1", "slideMaster", "slideMasters/slideMaster1.xml"),
                 ("rId2", "notesMaster", "notesMasters/notesMaster1.xml")]
    for i in range(1, n + 1):
        pres_rels.append((f"rId{i + 2}", "slide", f"slides/slide{i}.xml"))
    sld_ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i + 2}"/>'
                      for i in range(1, n + 1))
    presentation = (
        f'{XML_HEAD}<p:presentation {NS}>'
        f'<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/>'
        f'</p:sldMasterIdLst><p:notesMasterIdLst><p:notesMasterId r:id="rId2"/>'
        f'</p:notesMasterIdLst><p:sldIdLst>{sld_ids}</p:sldIdLst>'
        f'<p:sldSz cx="{deck.cx}" cy="{deck.cy}"/>'
        f'<p:notesSz cx="6858000" cy="9144000"/></p:presentation>')

    with zipfile.ZipFile(pptx_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types(n))
        z.writestr("_rels/.rels", rels_xml([
            ("rId1", "officeDocument", "ppt/presentation.xml"),
            ("rId2", "metadata/core-properties", "docProps/core.xml"),
            ("rId3", "extended-properties", "docProps/app.xml")]))
        z.writestr("docProps/core.xml",
                   f'{XML_HEAD}<cp:coreProperties xmlns:cp="http://schemas.'
                   f'openxmlformats.org/package/2006/metadata/core-properties" '
                   f'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                   f'xmlns:dcterms="http://purl.org/dc/terms/" '
                   f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                   f'<dc:title>{escape(plan.get("title", "academic deck"))}'
                   f'</dc:title><dc:creator>table-rebind-lab</dc:creator>'
                   f'</cp:coreProperties>')
        z.writestr("docProps/app.xml",
                   f'{XML_HEAD}<Properties xmlns="http://schemas.openxmlformats'
                   f'.org/officeDocument/2006/extended-properties">'
                   f'<Application>table-rebind-lab</Application>'
                   f'<Slides>{n}</Slides></Properties>')
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels", rels_xml(pres_rels))
        z.writestr("ppt/theme/theme1.xml", THEME)
        z.writestr("ppt/theme/theme2.xml", THEME)
        z.writestr("ppt/slideMasters/slideMaster1.xml", SLIDE_MASTER)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", rels_xml([
            ("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
            ("rId2", "theme", "../theme/theme1.xml")]))
        z.writestr("ppt/slideLayouts/slideLayout1.xml", SLIDE_LAYOUT)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", rels_xml([
            ("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")]))
        z.writestr("ppt/notesMasters/notesMaster1.xml", NOTES_MASTER)
        z.writestr("ppt/notesMasters/_rels/notesMaster1.xml.rels", rels_xml([
            ("rId1", "theme", "../theme/theme2.xml")]))
        for i, s in enumerate(deck.slides, start=1):
            rels = list(s["rels"]) + [("rIdNotes", "notesSlide",
                                       f"../notesSlides/notesSlide{i}.xml")]
            z.writestr(f"ppt/slides/slide{i}.xml", slide_xml(s["shapes"]))
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", rels_xml(rels))
            z.writestr(f"ppt/notesSlides/notesSlide{i}.xml",
                       notes_xml(s["notes"]))
            z.writestr(f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels",
                       rels_xml([("rId1", "slide", f"../slides/slide{i}.xml"),
                                 ("rId2", "notesMaster",
                                  "../notesMasters/notesMaster1.xml")]))
        for path, name in deck.media.items():
            z.write(path, f"ppt/media/{name}")
    print(f"[build_deck] wrote {pptx_path} ({n} slide(s), "
          f"{os.path.getsize(pptx_path) / 1024:.1f} KB)")

    # ---- copy provenance artifacts into the output dir
    for sub, patterns in (("tables", ("*.csv", "tables.json")),
                          ("charts", ("*.png", "*.provenance.json"))):
        src = os.path.join(work, sub)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(out, sub)
        os.makedirs(dst, exist_ok=True)
        if sub == "tables":
            extra = os.path.join(work, "tables.json")
            if os.path.isfile(extra):
                shutil.copy2(extra, os.path.join(dst, "tables.json"))
        for fn in sorted(os.listdir(src)):
            if any(fn.endswith(p.lstrip("*")) for p in patterns):
                shutil.copy2(os.path.join(src, fn), os.path.join(dst, fn))
    print(f"[build_deck] copied tables/ and charts/ artifacts into {out}")

    # ---- optional PDF export + previews
    soffice = shutil.which("soffice")
    if soffice:
        r = subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                            "--outdir", out, pptx_path],
                           capture_output=True, text=True, timeout=300)
        pdf_path = os.path.join(out, "presentation.pdf")
        if r.returncode == 0 and os.path.isfile(pdf_path):
            print(f"[build_deck] exported {pdf_path}")
            pdftoppm = shutil.which("pdftoppm")
            if pdftoppm:
                prev = os.path.join(out, "preview")
                os.makedirs(prev, exist_ok=True)
                subprocess.run([pdftoppm, "-png", "-r", "100", pdf_path,
                                os.path.join(prev, "preview")],
                               capture_output=True, text=True)
                print(f"[build_deck] previews -> {prev}/preview-*.png")
        else:
            print(f"[build_deck] WARNING: soffice export failed: "
                  f"{r.stderr.strip()[:200]}")
    else:
        print("[build_deck] soffice not found; skipping presentation.pdf "
              "and previews (note this in result.json exceptions)")


if __name__ == "__main__":
    main()
