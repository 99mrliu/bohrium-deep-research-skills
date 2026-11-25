#!/usr/bin/env python3
"""Minimal pure-stdlib PPTX builder for ingest-provenance-forge.

Refuses to build unless bindings.json reports ok:true (fail-closed).
Writes a 16:9 deck with a title textbox, bullet textbox (each bullet carries
its provenance footer "p.<page> · spans <ids>"), an optional figure PNG, and
speaker notes. If --template is given, the slide size is adopted from
ppt/presentation.xml sldSz; full theme inheritance is OUT OF SCOPE and is
declared in the manifest.

If soffice/libreoffice is on PATH, also exports presentation.pdf and renders
preview PNGs into <output>/preview/. Otherwise records the miss gracefully.

Usage:
    python3 build_deck.py --plan work/plan.json --bindings work/bindings.json \
        [--template target-template.pptx]
"""
import argparse
import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from xml.sax.saxutils import escape

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
EMU_W, EMU_H = 12192000, 6858000  # 16:9 wide
MARGIN = 548640                    # 0.6 in
SYN_PREFIX = "SYNTHETIC EXAMPLE — "


def log(msg):
    print(f"[build_deck] {msg}", flush=True)


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def sp_textbox(sid, name, x, y, cx, cy, paras):
    """paras: list of (text, size_hpt, bold, color, bullet)"""
    body = []
    for text, size, bold, color, bullet in paras:
        ppr = ('<a:pPr marL="342900" indent="-342900"><a:buChar char="\u2022"/></a:pPr>'
               if bullet else "<a:pPr/>")
        b = ' b="1"' if bold else ""
        body.append(
            f'<a:p>{ppr}<a:r><a:rPr lang="en-US" sz="{size}"{b}>'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr>'
            f'<a:t>{escape(text)}</a:t></a:r></a:p>')
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{escape(name)}"/>'
            f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>{"".join(body)}</p:txBody></p:sp>')


def sp_picture(sid, name, rid, x, y, cx, cy):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{sid}" name="{escape(name)}"/>'
            f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')


def slide_xml(shapes):
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<p:sld {NS}><p:cSld><p:spTree>'
            f'<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            f'<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
            f'<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            f'{"".join(shapes)}</p:spTree></p:cSld>'
            f'<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')


THEME = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="ipf-minimal">
<a:themeElements>
<a:clrScheme name="ipf"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
<a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="F3F4F6"/></a:lt2>
<a:accent1><a:srgbClr val="2563EB"/></a:accent1><a:accent2><a:srgbClr val="0D9488"/></a:accent2>
<a:accent3><a:srgbClr val="D97706"/></a:accent3><a:accent4><a:srgbClr val="7C3AED"/></a:accent4>
<a:accent5><a:srgbClr val="DC2626"/></a:accent5><a:accent6><a:srgbClr val="4B5563"/></a:accent6>
<a:hlink><a:srgbClr val="0000FF"/></a:hlink><a:folHlink><a:srgbClr val="800080"/></a:folHlink></a:clrScheme>
<a:fontScheme name="ipf"><a:majorFont><a:latin typeface="Helvetica"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
<a:minorFont><a:latin typeface="Helvetica"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>
<a:fmtScheme name="ipf">
<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/><a:satMod val="170000"/></a:schemeClr></a:solidFill>
<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="93000"/><a:satMod val="150000"/><a:shade val="98000"/><a:lumMod val="102500"/></a:schemeClr></a:gs>
<a:gs pos="100000"><a:schemeClr val="phClr"><a:tint val="98000"/><a:satMod val="130000"/><a:shade val="90000"/><a:lumMod val="103000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="5400000" scaled="0"/></a:gradFill></a:fillStyleLst>
<a:lnStyleLst><a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>
<a:ln w="12700" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>
<a:ln w="19050" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln></a:lnStyleLst>
<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/><a:satMod val="170000"/></a:schemeClr></a:solidFill>
<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="93000"/><a:satMod val="150000"/><a:shade val="98000"/><a:lumMod val="102500"/></a:schemeClr></a:gs>
<a:gs pos="100000"><a:schemeClr val="phClr"><a:tint val="98000"/><a:satMod val="130000"/><a:shade val="90000"/><a:lumMod val="103000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="5400000" scaled="0"/></a:gradFill></a:bgFillStyleLst>
</a:fmtScheme></a:themeElements></a:theme>'''

EMPTY_TREE = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
              '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
              '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
CLRMAP = ('<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
          'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
          'accent6="accent6" hlink="hlink" folHlink="folHlink"/>')

MASTER = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:sldMaster {NS}>'
          f'<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>'
          f'<a:effectLst/></p:bgPr></p:bg><p:spTree>{EMPTY_TREE}</p:spTree></p:cSld>{CLRMAP}'
          f'<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
          f'<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz="3200"/></a:lvl1pPr></p:titleStyle>'
          f'<p:bodyStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:bodyStyle>'
          f'<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle>'
          f'</p:txStyles></p:sldMaster>')

LAYOUT = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          f'<p:sldLayout {NS} type="blank" preserve="1">'
          f'<p:cSld name="Blank"><p:spTree>{EMPTY_TREE}</p:spTree></p:cSld>'
          f'<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')

NOTES_MASTER = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                f'<p:notesMaster {NS}><p:cSld><p:spTree>{EMPTY_TREE}</p:spTree></p:cSld>'
                f'{CLRMAP}<p:notesStyle><a:lvl1pPr><a:defRPr sz="1200"/></a:lvl1pPr>'
                f'</p:notesStyle></p:notesMaster>')


def notes_xml(text):
    paras = "".join(
        f'<a:p><a:r><a:rPr lang="en-US" sz="1200"/><a:t>{escape(line)}</a:t></a:r></a:p>'
        for line in (text.splitlines() or [""]))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<p:notes {NS}><p:cSld><p:spTree>{EMPTY_TREE}'
            f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder"/>'
            f'<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="685800" y="457200"/><a:ext cx="5486400" cy="8229600"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>{paras}</p:txBody></p:sp>'
            f'</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>')


RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '{}</Relationships>')


def rel(rid, rtype, target):
    return (f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/{rtype}" Target="{target}"/>')


def main():
    ap = argparse.ArgumentParser(description="Build PPTX from a fail-closed verified plan")
    ap.add_argument("--plan", default=None)
    ap.add_argument("--bindings", default=None)
    ap.add_argument("--template", default=None)
    ap.add_argument("--input-dir", default=os.environ.get("CASE_INPUT_DIR", "/input"))
    ap.add_argument("--work-dir", default=os.environ.get("CASE_WORK_DIR", "/app/work"))
    ap.add_argument("--output-dir", default=os.environ.get("CASE_OUTPUT_DIR", "/app/output"))
    args = ap.parse_args()
    work = os.path.abspath(args.work_dir)
    outdir = os.path.abspath(args.output_dir)
    os.makedirs(outdir, exist_ok=True)

    plan = json.load(open(args.plan or os.path.join(work, "plan.json"), encoding="utf-8"))
    bindings = json.load(open(args.bindings or os.path.join(work, "bindings.json"),
                              encoding="utf-8"))
    if not bindings.get("ok"):
        log("REFUSING to build: bindings.json shows failures; fix the plan, not the checker")
        return 1

    manifest = {"builder": "build_deck.py (pure-stdlib minimal pptx writer)",
                "synthetic_example": bool(plan.get("synthetic_example")),
                "slides": [], "missing_tools": [], "export": {}}

    cx, cy = EMU_W, EMU_H
    if args.template and os.path.isfile(args.template):
        try:
            with zipfile.ZipFile(args.template) as z:
                xml = z.read("ppt/presentation.xml").decode("utf-8", "replace")
            m = re.search(r'<p:sldSz[^>]*cx="(\d+)"[^>]*cy="(\d+)"', xml)
            if m:
                cx, cy = int(m.group(1)), int(m.group(2))
                manifest["template"] = {"path": os.path.abspath(args.template),
                                        "adopted": "slide size only",
                                        "note": "full theme inheritance is out of scope"}
        except Exception as e:
            manifest["template"] = {"path": os.path.abspath(args.template),
                                    "error": f"could not parse template: {e}"}
    else:
        manifest["template"] = {"note": "no template; default 16:9; full theme "
                                        "inheritance out of scope"}

    figures = {}
    fig_path = os.path.join(work, "figures.json")
    if os.path.isfile(fig_path):
        for f in json.load(open(fig_path, encoding="utf-8")).get("figures", []):
            figures[f["fig_id"]] = f

    synthetic = bool(plan.get("synthetic_example"))
    slides = plan.get("slides", [])
    ev = bindings.get("evidence_map", {})

    parts = {}  # arcname -> bytes/str
    slide_rels = {}
    media = []
    content_overrides = []
    pres_rels = [rel("rId1", "slideMaster", "slideMasters/slideMaster1.xml"),
                 rel("rId2", "notesMaster", "notesMasters/notesMaster1.xml")]
    sld_ids = []

    for i, slide in enumerate(slides):
        n = i + 1
        sid = slide.get("id", f"s{n}")
        title = slide.get("title", "")
        if synthetic and n == 1 and not title.startswith(SYN_PREFIX):
            title = SYN_PREFIX + title
        shapes, rid_n = [], 1
        sp_id = 10
        slide_rel = [rel("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml")]
        fig = slide.get("figure")
        fig_entry = figures.get(fig) if fig else None
        img_path = fig_entry.get("crop_path") if fig_entry else None
        if fig and fig_entry and fig_entry.get("kind") == "table":
            img_path = None  # tables are transcribed, never embedded as crops
        has_img = bool(img_path and os.path.isfile(img_path))

        shapes.append(sp_textbox(sp_id, "Title", MARGIN, 274320, cx - 2 * MARGIN, 820000,
                                 [(title, 2800, True, "1F2937", False)]))
        sp_id += 1

        body_w = int((cx - 2 * MARGIN) * 0.54) if has_img else cx - 2 * MARGIN
        paras = []
        for j, bullet in enumerate(slide.get("bullets", [])):
            paras.append((bullet.get("text", ""), 1600, False, "111827", True))
            footer = ev.get(f"{sid}/b{j + 1}", {}).get("footer")
            if footer:
                paras.append((footer, 1000, False, "6B7280", False))
        if not paras:
            paras = [("", 1600, False, "111827", False)]
        shapes.append(sp_textbox(sp_id, "Body", MARGIN, 1250000, body_w, cy - 2300000, paras))
        sp_id += 1

        if has_img:
            size = png_size(img_path)
            arc = f"media/image{n}.png"
            media.append((arc, img_path))
            rid_n = len(slide_rel) + 1
            slide_rel.append(rel(f"rId{rid_n}", "image", f"../{arc}"))
            max_w, max_h = int((cx - 2 * MARGIN) * 0.42), cy - 2900000
            if size:
                iw, ih = size
                scale = min(max_w / iw, max_h / ih)
                w, h = int(iw * scale), int(ih * scale)
            else:
                w, h = max_w, max_h
            ix = cx - MARGIN - w
            iy = 1400000 + max(0, (max_h - h) // 2)
            shapes.append(sp_picture(sp_id, os.path.basename(img_path), f"rId{rid_n}",
                                     ix, iy, w, h))
            sp_id += 1
        elif fig_entry and fig_entry.get("kind") == "table":
            shapes.append(sp_textbox(sp_id, "TableNote", cx - MARGIN - 4200000, 1400000,
                                     4200000, 900000,
                                     [(f"[{fig}] prefer native/CSV transcription",
                                       1200, False, "6B7280", False)]))
            sp_id += 1

        # footer source line
        pages, span_ids = set(), []
        for j in range(len(slide.get("bullets", []))):
            e = ev.get(f"{sid}/b{j + 1}", {})
            pages.update(e.get("pages", []))
            span_ids.extend(e.get("span_ids", []))
        if pages:
            src = (f"p.{','.join(str(p) for p in sorted(pages))} \u00b7 spans "
                   f"{','.join(span_ids)}")
            shapes.append(sp_textbox(sp_id, "SourceFooter", MARGIN, cy - 500000,
                                     cx - 2 * MARGIN, 320000,
                                     [(src, 900, False, "9CA3AF", False)]))
            sp_id += 1

        parts[f"ppt/slides/slide{n}.xml"] = slide_xml(shapes)
        note_text = slide.get("notes", "") or ""
        if synthetic:
            note_text = (note_text + "\n" if note_text else "") + \
                "SYNTHETIC EXAMPLE - not an official case result."
        parts[f"ppt/notesSlides/notesSlide{n}.xml"] = notes_xml(note_text)
        rid_n += 1
        slide_rel.append(rel(f"rId{rid_n}", "notesSlide", f"../notesSlides/notesSlide{n}.xml"))
        slide_rels[n] = slide_rel
        pres_rels.append(rel(f"rId{len(pres_rels) + 1}", "slide", f"slides/slide{n}.xml"))
        sld_ids.append(f'<p:sldId id="{255 + n}" r:id="rId{len(pres_rels)}"/>')
        content_overrides += [
            (f"/ppt/slides/slide{n}.xml", "slide"),
            (f"/ppt/notesSlides/notesSlide{n}.xml", "notesSlide"),
        ]
        manifest["slides"].append({"id": sid, "title": title, "figure": fig,
                                   "bullets": len(slide.get("bullets", []))})

    pres = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<p:presentation {NS}>'
            f'<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
            f'<p:notesMasterIdLst><p:notesMasterId r:id="rId2"/></p:notesMasterIdLst>'
            f'<p:sldIdLst>{"".join(sld_ids)}</p:sldIdLst>'
            f'<p:sldSz cx="{cx}" cy="{cy}" type="wide"/><p:notesSz cx="6858000" cy="9144000"/>'
            f'</p:presentation>')
    parts["ppt/presentation.xml"] = pres
    parts["ppt/_rels/presentation.xml.rels"] = RELS.format("".join(pres_rels))
    parts["ppt/slideMasters/slideMaster1.xml"] = MASTER
    parts["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = RELS.format(
        rel("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml") +
        rel("rId2", "theme", "../theme/theme1.xml"))
    parts["ppt/slideLayouts/slideLayout1.xml"] = LAYOUT
    parts["ppt/slideLayouts/_rels/slideLayout1.xml.rels"] = RELS.format(
        rel("rId1", "slideMaster", "../slideMasters/slideMaster1.xml"))
    parts["ppt/notesMasters/notesMaster1.xml"] = NOTES_MASTER
    parts["ppt/notesMasters/_rels/notesMaster1.xml.rels"] = RELS.format(
        rel("rId1", "theme", "../theme/theme1.xml"))
    parts["ppt/theme/theme1.xml"] = THEME
    for n, srel in slide_rels.items():
        parts[f"ppt/slides/_rels/slide{n}.xml.rels"] = RELS.format("".join(srel))
        parts[f"ppt/notesSlides/_rels/notesSlide{n}.xml.rels"] = RELS.format(
            rel("rId1", "slide", f"../slides/slide{n}.xml") +
            rel("rId2", "notesMaster", "../notesMasters/notesMaster1.xml"))

    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Default Extension="png" ContentType="image/png"/>',
          '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
          '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
          '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
          '<Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>',
          '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>']
    for part, kind in content_overrides:
        ct.append(f'<Override PartName="{part}" ContentType="application/vnd.openxmlformats-officedocument.presentationml.{kind}+xml"/>')
    ct.append("</Types>")
    parts["[Content_Types].xml"] = "".join(ct)
    parts["_rels/.rels"] = RELS.format(
        rel("rId1", "officeDocument", "ppt/presentation.xml"))

    pptx_path = os.path.join(outdir, "presentation.pptx")
    with zipfile.ZipFile(pptx_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in parts.items():
            z.writestr(arc, data)
        for arc, src in media:
            z.write(src, f"ppt/{arc}")
    log(f"wrote {pptx_path} ({len(slides)} slides)")

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        r = subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                            "--outdir", outdir, pptx_path],
                           capture_output=True, text=True, timeout=300)
        pdf_out = os.path.join(outdir, "presentation.pdf")
        if r.returncode == 0 and os.path.isfile(pdf_out):
            manifest["export"]["pdf"] = pdf_out
            pdftoppm = shutil.which("pdftoppm")
            if pdftoppm:
                prev = os.path.join(outdir, "preview")
                os.makedirs(prev, exist_ok=True)
                subprocess.run([pdftoppm, "-r", "100", "-png", pdf_out,
                                os.path.join(prev, "slide")],
                               capture_output=True, text=True)
                manifest["export"]["previews"] = sorted(glob.glob(prev + "/*.png"))
        else:
            manifest["export"]["error"] = (r.stderr or r.stdout).strip()[:300]
    else:
        manifest["missing_tools"].append("soffice")
        manifest["export"]["skipped"] = ("soffice/libreoffice not on PATH; "
                                         "presentation.pdf and previews not produced")
        log("soffice not found; skipping PDF export and previews (recorded in manifest)")

    with open(os.path.join(work, "build_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
