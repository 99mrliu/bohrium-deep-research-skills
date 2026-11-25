#!/usr/bin/env python3
"""mini_build.py — deliberately minimal plan.json -> presentation.pptx builder.

Pure stdlib (zipfile + string templates). Produces an editable OOXML deck:
title + bullet body + speaker notes + a footer "Source:" line on every slide.
This builder is intentionally small — the bundle's center of gravity is the
gates/journal/watchdog that can wrap ANY builder; this one just makes the
gated pipeline real and self-contained.

plan.json schema:
{
  "meta":  {"deck_title": "...", "source": "paper.pdf", "footer": "..."},
  "slides": [
     {"title": "...", "bullets": ["...", ...], "notes": "...",
      "evidence": [{"quote": "...", "source": "paper"}]}
  ]
}
"""
import datetime
import json
import os
import sys
import zipfile
from xml.sax.saxutils import escape

WORK_DIR = os.environ.get("CASE_WORK_DIR", "/app/work")
OUTPUT_DIR = os.environ.get("CASE_OUTPUT_DIR", "/app/output")

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
CT_SLIDE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
CT_NOTES = "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
R_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def theme_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="MiniTheme">
<a:themeElements>
<a:clrScheme name="Mini">
<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
<a:dk2><a:srgbClr val="1F3864"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2>
<a:accent1><a:srgbClr val="2E74B5"/></a:accent1><a:accent2><a:srgbClr val="C0504D"/></a:accent2>
<a:accent3><a:srgbClr val="9BBB59"/></a:accent3><a:accent4><a:srgbClr val="8064A2"/></a:accent4>
<a:accent5><a:srgbClr val="4BACC6"/></a:accent5><a:accent6><a:srgbClr val="F79646"/></a:accent6>
<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
</a:clrScheme>
<a:fontScheme name="Mini"><a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>
<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>
<a:fmtScheme name="Mini">
<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>
<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="25400"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="38100"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>
<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>
</a:fmtScheme>
</a:themeElements></a:theme>'''


SP_TREE_OPEN = ('<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
                '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
                '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
CLR_MAP = ('<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
           'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" '
           'hlink="hlink" folHlink="folHlink"/>')


def master_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster {NS}><p:cSld><p:bg><p:bgPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>
{SP_TREE_OPEN}</p:spTree></p:cSld>{CLR_MAP}
<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst></p:sldMaster>'''


def layout_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout {NS} type="blank" preserve="1"><p:cSld name="Blank">{SP_TREE_OPEN}</p:spTree></p:cSld>
<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'''


def notes_master_xml():
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notesMaster {NS}><p:cSld>{SP_TREE_OPEN}</p:spTree></p:cSld>{CLR_MAP}</p:notesMaster>'''


def rels_xml(rels):
    body = "".join(f'<Relationship Id="{rid}" Type="{typ}" Target="{tgt}"/>' for rid, typ, tgt in rels)
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{REL_NS}">{body}</Relationships>'


def text_runs(text, size, bold=False, color=None):
    rpr = f'<a:rPr lang="en-US" sz="{size}"' + (' b="1"' if bold else '')
    if color:
        rpr += f'><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr>'
    else:
        rpr += '/>'
    return f'<a:r>{rpr}<a:t>{escape(text)}</a:t></a:r>'


def slide_xml(slide, footer):
    bullets = slide.get("bullets") or []
    paras = "".join(
        '<a:p><a:pPr marL="285750" indent="-285750"><a:buChar char="\u2022"/></a:pPr>'
        + text_runs(b, 1800) + '</a:p>' for b in bullets)
    if not paras:
        paras = "<a:p/>"
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld {NS}><p:cSld>{SP_TREE_OPEN}
<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="457200" y="274638"/><a:ext cx="8229600" cy="1143000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
<p:txBody><a:bodyPr vert="horz" wrap="square"><a:normAutofit/></a:bodyPr><a:lstStyle/>
<a:p>{text_runs(slide.get("title", ""), 3200, bold=True, color="1F3864")}</a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content 2"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="457200" y="1600200"/><a:ext cx="8229600" cy="2900000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
<p:txBody><a:bodyPr wrap="square"><a:normAutofit/></a:bodyPr><a:lstStyle/>{paras}</p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="4" name="Footer 3"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="457200" y="4800000"/><a:ext cx="8229600" cy="300000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
<p:txBody><a:bodyPr/><a:lstStyle/><a:p>{text_runs(footer, 1000, color="808080")}</a:p></p:txBody></p:sp>
</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'''


def notes_xml(slide):
    notes = slide.get("notes") or ""
    ev_lines = []
    for ev in slide.get("evidence") or []:
        quote = ev.get("quote") if isinstance(ev, dict) else str(ev)
        ev_lines.append(f'Evidence: "{quote}"')
    body = "\n".join(x for x in [notes] + ev_lines if x)
    paras = "".join(f"<a:p>{text_runs(line, 1400)}</a:p>" for line in body.split("\n") if line.strip()) or "<a:p/>"
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:notes {NS}><p:cSld>{SP_TREE_OPEN}
<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder 1"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="685800" y="1143000"/><a:ext cx="5486400" cy="6858000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>{paras}</p:txBody></p:sp>
</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>'''


def content_types_xml(nslides):
    overrides = [
        ('<Override PartName="/ppt/presentation.xml" '
         'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'),
        ('<Override PartName="/ppt/slideMasters/slideMaster1.xml" '
         'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'),
        ('<Override PartName="/ppt/slideLayouts/slideLayout1.xml" '
         'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'),
        ('<Override PartName="/ppt/theme/theme1.xml" '
         'ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'),
        ('<Override PartName="/ppt/notesMasters/notesMaster1.xml" '
         'ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>'),
    ]
    for i in range(1, nslides + 1):
        overrides.append(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="{CT_SLIDE}"/>')
        overrides.append(f'<Override PartName="/ppt/notesSlides/notesSlide{i}.xml" ContentType="{CT_NOTES}"/>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + "".join(overrides) + "</Types>")


def build(plan, out_path):
    slides = plan.get("slides") or []
    if not slides:
        raise SystemExit("mini_build: plan has no slides")
    meta = plan.get("meta") or {}
    source = meta.get("source", "source paper")
    footer = meta.get("footer") or f"Source: {source} | generated {datetime.date.today().isoformat()}"
    n = len(slides)
    sld_ids = "".join(f'<p:sldId id="{255 + i}" r:id="rId{2 + i}"/>' for i in range(1, n + 1))
    presentation = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation {NS}><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>
<p:notesMasterIdLst><p:notesMasterId r:id="rId2"/></p:notesMasterIdLst>
<p:sldIdLst>{sld_ids}</p:sldIdLst>
<p:sldSz cx="9144000" cy="5143500" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'''
    pres_rels = [("rId1", f"{R_OFFICE}/slideMaster", "slideMasters/slideMaster1.xml"),
                 ("rId2", f"{R_OFFICE}/notesMaster", "notesMasters/notesMaster1.xml")]
    for i in range(1, n + 1):
        pres_rels.append((f"rId{2 + i}", f"{R_OFFICE}/slide", f"slides/slide{i}.xml"))
    pres_rels.append((f"rId{3 + n}", f"{R_OFFICE}/theme", "theme/theme1.xml"))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml(n))
        z.writestr("_rels/.rels", rels_xml([("rId1", f"{R_OFFICE}/officeDocument", "ppt/presentation.xml")]))
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels", rels_xml(pres_rels))
        z.writestr("ppt/theme/theme1.xml", theme_xml())
        z.writestr("ppt/slideMasters/slideMaster1.xml", master_xml())
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", rels_xml([
            ("rId1", f"{R_OFFICE}/slideLayout", "../slideLayouts/slideLayout1.xml"),
            ("rId2", f"{R_OFFICE}/theme", "../theme/theme1.xml")]))
        z.writestr("ppt/slideLayouts/slideLayout1.xml", layout_xml())
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", rels_xml([
            ("rId1", f"{R_OFFICE}/slideMaster", "../slideMasters/slideMaster1.xml")]))
        z.writestr("ppt/notesMasters/notesMaster1.xml", notes_master_xml())
        z.writestr("ppt/notesMasters/_rels/notesMaster1.xml.rels", rels_xml([
            ("rId1", f"{R_OFFICE}/theme", "../theme/theme1.xml")]))
        for i, slide in enumerate(slides, start=1):
            z.writestr(f"ppt/slides/slide{i}.xml", slide_xml(slide, footer))
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", rels_xml([
                ("rId1", f"{R_OFFICE}/slideLayout", "../slideLayouts/slideLayout1.xml"),
                ("rId2", f"{R_OFFICE}/notesSlide", f"../notesSlides/notesSlide{i}.xml")]))
            z.writestr(f"ppt/notesSlides/notesSlide{i}.xml", notes_xml(slide))
            z.writestr(f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels", rels_xml([
                ("rId1", f"{R_OFFICE}/notesMaster", "../notesMasters/notesMaster1.xml"),
                ("rId2", f"{R_OFFICE}/slide", f"../slides/slide{i}.xml")]))
    return out_path


def main():
    plan_path = os.path.join(WORK_DIR, "plan.json")
    if not os.path.isfile(plan_path):
        print(f"mini_build: ERROR {plan_path} not found — run the plan stage first", file=sys.stderr)
        return 1
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    out_path = os.path.join(OUTPUT_DIR, "presentation.pptx")
    build(plan, out_path)
    n = len(plan.get("slides") or [])
    print(f"mini_build: wrote {out_path} ({n} slide(s), {os.path.getsize(out_path)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
