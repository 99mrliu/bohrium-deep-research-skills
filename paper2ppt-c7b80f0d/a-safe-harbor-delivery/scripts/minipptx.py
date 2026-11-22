#!/usr/bin/env python3
"""minipptx — compact pure-stdlib OOXML .pptx writer/patcher (no third-party deps).

Produces a minimal but schema-valid 16:9 presentation package that opens in
PowerPoint, LibreOffice and python-pptx. Supports one layout ("title + bullets +
footer") plus a notes slide per slide. Slide XML is generated deterministically
from a plain dict, so patching a slide = regenerating its XML part inside the zip.

Public API:
    Deck().add_slide(title, bullets, notes, footer).save(path)
    patch_slide_parts(path, index1, slide_dict)   # 1-based slide number
    validate_package(path) -> list of error strings
"""
import os
import shutil
import tempfile
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

SLIDE_W = 12192000  # 16:9 EMU
SLIDE_H = 6858000

XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

# --------------------------------------------------------------------------- #
# Static package parts
# --------------------------------------------------------------------------- #

THEME_XML = XML_DECL + (
    '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="SafeHarbor">'
    '<a:themeElements>'
    '<a:clrScheme name="Office">'
    '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
    '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
    '<a:dk2><a:srgbClr val="1F3864"/></a:dk2>'
    '<a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
    '<a:accent1><a:srgbClr val="2E5E8C"/></a:accent1>'
    '<a:accent2><a:srgbClr val="C0504D"/></a:accent2>'
    '<a:accent3><a:srgbClr val="9BBB59"/></a:accent3>'
    '<a:accent4><a:srgbClr val="8064A2"/></a:accent4>'
    '<a:accent5><a:srgbClr val="4BACC6"/></a:accent5>'
    '<a:accent6><a:srgbClr val="F79646"/></a:accent6>'
    '<a:hlink><a:srgbClr val="0000FF"/></a:hlink>'
    '<a:folHlink><a:srgbClr val="800080"/></a:folHlink>'
    '</a:clrScheme>'
    '<a:fontScheme name="Office">'
    '<a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
    '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
    '</a:fontScheme>'
    '<a:fmtScheme name="Office">'
    '<a:fillStyleLst>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/></a:schemeClr></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"><a:shade val="95000"/></a:schemeClr></a:solidFill>'
    '</a:fillStyleLst>'
    '<a:lnStyleLst>'
    '<a:ln w="9525" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>'
    '<a:ln w="25400" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>'
    '<a:ln w="38100" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>'
    '</a:lnStyleLst>'
    '<a:effectStyleLst>'
    '<a:effectStyle><a:effectLst/></a:effectStyle>'
    '<a:effectStyle><a:effectLst/></a:effectStyle>'
    '<a:effectStyle><a:effectLst/></a:effectStyle>'
    '</a:effectStyleLst>'
    '<a:bgFillStyleLst>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/></a:schemeClr></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"><a:shade val="95000"/></a:schemeClr></a:solidFill>'
    '</a:bgFillStyleLst>'
    '</a:fmtScheme>'
    '</a:themeElements>'
    '</a:theme>'
)

_CLR_MAP = ('<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
            'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
            'accent6="accent6" hlink="hlink" folHlink="folHlink"/>')

_EMPTY_SPTREE = (
    '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree>'
)

_LVL1 = ('<a:lvl1pPr algn="l"><a:defRPr sz="1800"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
         '<a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr>')

SLIDE_MASTER_XML = XML_DECL + (
    '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    '<p:cSld>' + _EMPTY_SPTREE + '</p:cSld>' + _CLR_MAP +
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
    '<p:txStyles><p:titleStyle>' + _LVL1 + '</p:titleStyle>'
    '<p:bodyStyle>' + _LVL1 + '</p:bodyStyle>'
    '<p:otherStyle>' + _LVL1 + '</p:otherStyle></p:txStyles>'
    '</p:sldMaster>'
)

SLIDE_LAYOUT_XML = XML_DECL + (
    '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'type="obj" userDrawn="1" preserve="1">'
    '<p:cSld name="Title and Content">' + _EMPTY_SPTREE + '</p:cSld>'
    '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
    '</p:sldLayout>'
)

NOTES_MASTER_XML = XML_DECL + (
    '<p:notesMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    '<p:cSld>' + _EMPTY_SPTREE + '</p:cSld>' + _CLR_MAP +
    '<p:notesStyle>' + _LVL1 + '</p:notesStyle>'
    '</p:notesMaster>'
)

ROOT_RELS_XML = XML_DECL + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="ppt/presentation.xml"/>'
    '</Relationships>'
)

SLIDE_MASTER_RELS_XML = XML_DECL + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" '
    'Target="../slideLayouts/slideLayout1.xml"/>'
    '<Relationship Id="rId2" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" '
    'Target="../theme/theme1.xml"/>'
    '</Relationships>'
)

SLIDE_LAYOUT_RELS_XML = XML_DECL + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" '
    'Target="../slideMasters/slideMaster1.xml"/>'
    '</Relationships>'
)

NOTES_MASTER_RELS_XML = XML_DECL + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" '
    'Target="../theme/theme1.xml"/>'
    '</Relationships>'
)

# --------------------------------------------------------------------------- #
# Dynamic part builders
# --------------------------------------------------------------------------- #

def _run(text, size, bold=False, color="222222"):
    b = ' b="1"' if bold else ""
    return ('<a:r><a:rPr lang="en-US" sz="%d"%s><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:rPr>'
            '<a:t>%s</a:t></a:r>' % (size, b, color, escape(text)))


def _bullet_para(text, size=1600):
    return ('<a:p><a:pPr marL="285750" indent="-285750"><a:buFont typeface="Arial"/>'
            '<a:buChar char="\u2022"/></a:pPr>' + _run(text, size) + '</a:p>')


def _plain_para(text, size=1400, bold=False, color="222222"):
    return '<a:p><a:pPr><a:buNone/></a:pPr>' + _run(text, size, bold, color) + '</a:p>'


def _text_box(shape_id, name, x, y, cx, cy, paras_xml):
    return (
        '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square"><a:normAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody>'
        '</p:sp>' % (shape_id, escape(name), x, y, cx, cy, paras_xml)
    )


def slide_xml(slide):
    """Build ppt/slides/slideN.xml from dict {title, bullets, footer}."""
    title = slide.get("title") or ""
    bullets = slide.get("bullets") or []
    footer = slide.get("footer") or ""
    body = "".join(_bullet_para(str(b)) for b in bullets) or _bullet_para("[empty]")
    sp = _text_box(2, "Title 1", 457200, 228600, 11277600, 1005840,
                   _plain_para(title, 3200, bold=True, color="1F3864"))
    sp += _text_box(3, "Body 2", 457200, 1371600, 11277600, 4800600, body)
    if footer:
        sp += _text_box(4, "Footer 3", 457200, 6400800, 11277600, 365760,
                        _plain_para(footer, 1000, color="7F7F7F"))
    return XML_DECL + (
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        + sp +
        '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )


def notes_xml(slide):
    """Build ppt/notesSlides/notesSlideN.xml from dict {notes}."""
    notes = (slide.get("notes") or "").strip() or " "
    paras = "".join(_plain_para(line, 1400) for line in notes.splitlines()) or _plain_para(" ")
    sp = (
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder 1"/><p:cNvSpPr txBox="1"/>'
        '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="685800" y="4343400"/><a:ext cx="5486400" cy="4114800"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr/><a:lstStyle/>%s</p:txBody></p:sp>' % paras
    )
    return XML_DECL + (
        '<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        + sp +
        '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>'
    )


def _slide_rels_xml(i):
    return XML_DECL + (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" '
        'Target="../slideLayouts/slideLayout1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" '
        'Target="../notesSlides/notesSlide%d.xml"/>'
        '</Relationships>' % i
    )


def _notes_rels_xml(i):
    return XML_DECL + (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        'Target="../slides/slide%d.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" '
        'Target="../notesMasters/notesMaster1.xml"/>'
        '</Relationships>' % i
    )


def _presentation_xml(n):
    sld_ids = "".join('<p:sldId id="%d" r:id="rId%d"/>' % (256 + i, 3 + i) for i in range(n))
    return XML_DECL + (
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        '<p:notesMasterIdLst><p:notesMasterId r:id="rId2"/></p:notesMasterIdLst>'
        '<p:sldIdLst>' + sld_ids + '</p:sldIdLst>'
        '<p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>'
        '<p:notesSz cx="6858000" cy="9144000"/>'
        '</p:presentation>'
    )


def _presentation_rels_xml(n):
    rels = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>',
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster" Target="notesMasters/notesMaster1.xml"/>',
    ]
    for i in range(1, n + 1):
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide%d.xml"/>' % (2 + i, i))
    for i in range(1, n + 1):
        rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="notesSlides/notesSlide%d.xml"/>' % (2 + n + i, i))
    return XML_DECL + ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       + "".join(rels) + '</Relationships>')


def _content_types_xml(n):
    ov = ['<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
          '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
          '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
          '<Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>',
          '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>']
    for i in range(1, n + 1):
        ov.append('<Override PartName="/ppt/slides/slide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' % i)
    for i in range(1, n + 1):
        ov.append('<Override PartName="/ppt/notesSlides/notesSlide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>' % i)
    return XML_DECL + ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                       '<Default Extension="xml" ContentType="application/xml"/>'
                       + "".join(ov) + '</Types>')


# --------------------------------------------------------------------------- #
# Deck API
# --------------------------------------------------------------------------- #

class Deck(object):
    """Minimal 16:9 deck. add_slide(title, bullets, notes, footer) then save(path)."""

    def __init__(self):
        self.slides = []

    def add_slide(self, title="", bullets=None, notes="", footer=""):
        self.slides.append({"title": title, "bullets": list(bullets or []),
                            "notes": notes, "footer": footer})
        return self

    def _parts(self):
        n = len(self.slides)
        if n < 1:
            raise ValueError("deck must contain at least one slide")
        parts = {
            "[Content_Types].xml": _content_types_xml(n),
            "_rels/.rels": ROOT_RELS_XML,
            "ppt/presentation.xml": _presentation_xml(n),
            "ppt/_rels/presentation.xml.rels": _presentation_rels_xml(n),
            "ppt/slideMasters/slideMaster1.xml": SLIDE_MASTER_XML,
            "ppt/slideMasters/_rels/slideMaster1.xml.rels": SLIDE_MASTER_RELS_XML,
            "ppt/slideLayouts/slideLayout1.xml": SLIDE_LAYOUT_XML,
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels": SLIDE_LAYOUT_RELS_XML,
            "ppt/notesMasters/notesMaster1.xml": NOTES_MASTER_XML,
            "ppt/notesMasters/_rels/notesMaster1.xml.rels": NOTES_MASTER_RELS_XML,
            "ppt/theme/theme1.xml": THEME_XML,
        }
        for i, s in enumerate(self.slides, 1):
            parts["ppt/slides/slide%d.xml" % i] = slide_xml(s)
            parts["ppt/slides/_rels/slide%d.xml.rels" % i] = _slide_rels_xml(i)
            parts["ppt/notesSlides/notesSlide%d.xml" % i] = notes_xml(s)
            parts["ppt/notesSlides/_rels/notesSlide%d.xml.rels" % i] = _notes_rels_xml(i)
        return parts

    def save(self, path):
        parts = self._parts()
        _write_zip_atomic(path, parts)
        return path


def _write_zip_atomic(path, parts):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".pptx", dir=d)
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for name in parts:  # insertion order: content types first
                z.writestr(name, parts[name])
        shutil.move(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def patch_slide_parts(path, index1, slide):
    """Replace slide <index1> (1-based) XML + notes XML inside an existing minipptx deck.

    Rewrites the zip wholesale (zips cannot be edited in place), replacing only
    the two parts for that slide; every other part is preserved byte-for-byte.
    """
    slide_part = "ppt/slides/slide%d.xml" % index1
    notes_part = "ppt/notesSlides/notesSlide%d.xml" % index1
    with zipfile.ZipFile(path, "r") as z:
        names = z.namelist()
        if slide_part not in names:
            raise ValueError("slide %d not found in %s (has %d slides)"
                             % (index1, path, sum(1 for x in names
                                                  if x.startswith("ppt/slides/slide")
                                                  and x.endswith(".xml"))))
        parts = {name: z.read(name) for name in names}
    parts[slide_part] = slide_xml(slide)
    if notes_part in parts:
        parts[notes_part] = notes_xml(slide)
    ordered = {name: parts[name] for name in names}
    _write_zip_atomic(path, ordered)


def validate_package(path):
    """Return list of error strings; empty list = package parses cleanly."""
    errors = []
    if not zipfile.is_zipfile(path):
        return ["not a zip file: %s" % path]
    with zipfile.ZipFile(path, "r") as z:
        names = z.namelist()
        if "[Content_Types].xml" not in names:
            errors.append("missing [Content_Types].xml")
        for name in names:
            if name.endswith(".xml") or name.endswith(".rels"):
                try:
                    ET.fromstring(z.read(name))
                except Exception as e:
                    errors.append("malformed XML in %s: %s" % (name, e))
    return errors
