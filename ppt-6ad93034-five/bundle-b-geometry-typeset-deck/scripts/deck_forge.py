#!/usr/bin/env python3
"""deck_forge.py -- pure-stdlib .pptx writer driven by textfit.py layout geometry.

    deck_forge.py --layout work/layout.json --theme work/theme.json \
        [--template /input/target-template.pptx] [--images work/figs] \
        [--out /app/output/presentation.pptx]

KEY FEATURE -- theme cloning: when --template is given, the bytes of
ppt/theme/theme1.xml are copied VERBATIM from the template into the output
package, and every run references theme fonts via "+mj-lt"/"+mn-lt"/"+mj-ea"/
"+mn-ea" typeface attributes and theme colors via <a:schemeClr val="accent1"/>
etc. PowerPoint / LibreOffice therefore resolve the organizer template's REAL
fonts and colors. What is NOT cloned: slide-master ARTWORK (bitmaps, background
images, decorative shapes) -- declared as an exception (see SKILL.md).

Also writes: speaker-notes slides, footer text boxes, literal slide numbers,
and PNG image embedding (aspect ratio read from the PNG IHDR header). Missing
image files become a placeholder box labeled with the intended source path --
never a fabricated chart.

Deterministic: fixed zip member order, fixed docProps timestamps; identical
layout+theme+template input -> byte-identical pptx.
"""
import argparse
import json
import os
import struct
import sys
import zipfile
from xml.sax.saxutils import escape

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

FIXED_TIMESTAMP = "2026-01-01T00:00:00Z"  # deterministic docProps
FIXED_ZIP_DATE = (2026, 1, 1, 0, 0, 0)     # deterministic zip member headers


def _writestr(zf, name, data):
    """Write a zip member with a fixed timestamp -> byte-deterministic pptx."""
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    zf.writestr(info, data)


# --------------------------------------------------------------------------
# default theme (used only when no template is supplied)
# --------------------------------------------------------------------------
def default_theme_xml():
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
            "<a:theme xmlns:a=\"%s\" name=\"GeometryTypesetDefault\">"
            "<a:themeElements><a:clrScheme name=\"Office\">"
            "<a:dk1><a:srgbClr val=\"000000\"/></a:dk1>"
            "<a:lt1><a:srgbClr val=\"FFFFFF\"/></a:lt1>"
            "<a:dk2><a:srgbClr val=\"44546A\"/></a:dk2>"
            "<a:lt2><a:srgbClr val=\"E7E6E6\"/></a:lt2>"
            "<a:accent1><a:srgbClr val=\"4472C4\"/></a:accent1>"
            "<a:accent2><a:srgbClr val=\"ED7D31\"/></a:accent2>"
            "<a:accent3><a:srgbClr val=\"A5A5A5\"/></a:accent3>"
            "<a:accent4><a:srgbClr val=\"FFC000\"/></a:accent4>"
            "<a:accent5><a:srgbClr val=\"5B9BD5\"/></a:accent5>"
            "<a:accent6><a:srgbClr val=\"70AD47\"/></a:accent6>"
            "<a:hlink><a:srgbClr val=\"0563C1\"/></a:hlink>"
            "<a:folHlink><a:srgbClr val=\"954F72\"/></a:folHlink>"
            "</a:clrScheme>"
            "<a:fontScheme name=\"Office\">"
            "<a:majorFont><a:latin typeface=\"Calibri Light\"/><a:ea typeface=\"\"/>"
            "<a:cs typeface=\"\"/></a:majorFont>"
            "<a:minorFont><a:latin typeface=\"Calibri\"/><a:ea typeface=\"\"/>"
            "<a:cs typeface=\"\"/></a:minorFont>"
            "</a:fontScheme>"
            "<a:fmtScheme name=\"Office\">"
            "<a:fillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill>"
            "<a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill>"
            "<a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:fillStyleLst>"
            "<a:lnStyleLst>"
            "<a:ln w=\"6350\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:ln>"
            "<a:ln w=\"12700\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:ln>"
            "<a:ln w=\"19050\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:ln>"
            "</a:lnStyleLst>"
            "<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>"
            "<a:effectStyle><a:effectLst/></a:effectStyle>"
            "<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>"
            "<a:bgFillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill>"
            "<a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill>"
            "<a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:bgFillStyleLst>"
            "</a:fmtScheme></a:themeElements>"
            "</a:theme>" % A)


def read_template_theme(template_path):
    """Return verbatim bytes of ppt/theme/theme1.xml from the template, or None."""
    if not template_path or not os.path.isfile(template_path):
        return None
    try:
        with zipfile.ZipFile(template_path) as zf:
            for name in sorted(zf.namelist()):
                if name.startswith("ppt/theme/theme"):
                    return zf.read(name)
    except (zipfile.BadZipFile, OSError, KeyError):
        return None
    return None


# --------------------------------------------------------------------------
# XML fragment builders
# --------------------------------------------------------------------------
def _rpr(size_pt, color_val, bold=False, major=False):
    b = ' b="1"' if bold else ""
    face = "+mj-lt" if major else "+mn-lt"
    ea = "+mj-ea" if major else "+mn-ea"
    return ('<a:rPr lang="en-US" sz="%d"%s dirty="0">'
            '<a:solidFill><a:schemeClr val="%s"/></a:solidFill>'
            '<a:latin typeface="%s"/><a:ea typeface="%s"/></a:rPr>'
            % (round(size_pt * 100), b, color_val, face, ea))


def _para(text, size_pt, color_val, bullet=None, bold=False, major=False,
          align=None):
    """One a:p. bullet=True -> buChar with hanging indent; False -> indented
    continuation line; None -> plain paragraph."""
    ppr = ""
    algn = ' algn="%s"' % align if align else ""
    if bullet is True:
        ppr = ('<a:pPr marL="228600" indent="-228600"%s>'
               '<a:buClr><a:schemeClr val="%s"/></a:buClr>'
               '<a:buFont typeface="Arial"/><a:buChar char="\u2022"/></a:pPr>'
               % (algn, color_val))
    elif bullet is False:
        ppr = '<a:pPr marL="228600" indent="0"%s><a:buNone/></a:pPr>' % algn
    elif algn:
        ppr = '<a:pPr%s/>' % algn
    return ("<a:p>%s<a:r>%s<a:t>%s</a:t></a:r></a:p>"
            % (ppr, _rpr(size_pt, color_val, bold=bold, major=major),
               escape(text)))


def _textbox(sid, name, box, paras_xml, anchor="t"):
    return (
        '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        '<a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square" lIns="45720" tIns="22860" rIns="45720" '
        'bIns="22860" anchor="%s"/><a:lstStyle/>%s</p:txBody></p:sp>'
        % (sid, escape(name), box["x"], box["y"], box["w"], box["h"],
           anchor, paras_xml))


def _placeholder_box(sid, name, box, label):
    paras = _para(label, 11, "accent3", align="ctr")
    return (
        '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        '<a:solidFill><a:schemeClr val="lt2"/></a:solidFill>'
        '<a:ln w="9525"><a:solidFill><a:schemeClr val="accent3"/></a:solidFill>'
        '</a:ln></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/>%s'
        '</p:txBody></p:sp>'
        % (sid, escape(name), box["x"], box["y"], box["w"], box["h"], paras))


def png_size(path):
    """Read (width, height) px from a PNG IHDR header; None if unreadable."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(26)
        if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            return None
        w, h = struct.unpack(">II", head[16:24])
        return (w, h) if w > 0 and h > 0 else None
    except OSError:
        return None


def _pic(sid, name, box, rel_id):
    return (
        '<p:pic><p:nvPicPr><p:cNvPr id="%d" name="%s"/>'
        '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        '<p:nvPr/></p:nvPicPr>'
        '<p:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch>'
        '</p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
        % (sid, escape(name), rel_id, box["x"], box["y"], box["w"], box["h"]))


# --------------------------------------------------------------------------
# slide / notes assembly
# --------------------------------------------------------------------------
def _slide_xml(slide, layout, rels, next_id):
    """Build slide XML + media rels. rels: list to append (rid, target) to."""
    shapes = []
    sid = next_id[0]

    def nid():
        next_id[0] += 1
        return next_id[0]

    tb = slide.get("title_box")
    if tb and tb.get("lines"):
        paras = "".join(_para(ln, tb["size_pt"], "accent1", bold=True, major=True)
                        for ln in tb["lines"])
        shapes.append(_textbox(nid(), "Title", tb, paras))

    bb = slide.get("body_box")
    if bb and bb.get("items"):
        paras = []
        for item in bb["items"]:
            for i, ln in enumerate(item["lines"]):
                paras.append(_para(ln, bb["size_pt"], "tx1",
                                   bullet=(i == 0) if item.get("bullet") else None))
        shapes.append(_textbox(nid(), "Body", bb, "".join(paras)))

    sb = slide.get("source_box")
    if sb and sb.get("lines"):
        paras = "".join(_para(ln, sb["size_pt"], "accent3") for ln in sb["lines"])
        shapes.append(_textbox(nid(), "SourceLine", sb, paras))

    if slide.get("image_box"):
        ib = slide["image_box"]
        img_rel = slide.get("image")
        img_path = None
        if img_rel:
            cand = img_rel if os.path.isabs(img_rel) else os.path.join(
                slide.get("_images_dir", ""), img_rel)
            if os.path.isfile(cand):
                img_path = cand
        if img_path:
            dims = png_size(img_path)
            box = dict(ib)
            if dims:
                w_px, h_px = dims
                scale = min(box["w"] / w_px, box["h"] / h_px)
                box["w"] = round(w_px * scale)
                box["h"] = round(h_px * scale)
                box["x"] += round((ib["w"] - box["w"]) / 2)
            rel_id = "rId%d" % (len(rels) + 2)
            rels.append((rel_id, "../media/%s" % os.path.basename(img_path),
                         img_path))
            shapes.append(_pic(nid(), os.path.basename(img_path), box, rel_id))
        else:
            label = "[image placeholder] %s (file not found)" % (img_rel or "?")
            shapes.append(_placeholder_box(nid(), "ImagePlaceholder", ib, label))

    # footer + slide number (small boxes in the reserved bottom zone)
    slide_h = layout["slide_h_emu"]
    slide_w = layout["slide_w_emu"]
    foot = slide.get("footer") or ""
    if foot:
        fbox = {"x": 548640, "y": slide_h - 329184, "w": round(slide_w * 0.7),
                "h": 256032}
        short = foot if len(foot) <= 80 else foot[:77] + "..."
        shapes.append(_textbox(nid(), "Footer", fbox,
                               _para(short, 9, "accent3")))
    nbox = {"x": slide_w - 914400, "y": slide_h - 329184, "w": 640080,
            "h": 256032}
    shapes.append(_textbox(nid(), "SlideNumber", nbox,
                           _para(str(slide.get("slide_no", "")), 9, "accent3",
                                 align="r")))

    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<p:sld xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">'
            '<p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
            '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            "%s</p:spTree></p:cSld><p:clrMapOvr><a:overrideClrMapping "
            'bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
            'accent2="accent2" accent3="accent3" accent4="accent4" '
            'accent5="accent5" accent6="accent6" hlink="hlink" '
            'folHlink="folHlink"/></p:clrMapOvr></p:sld>'
            % (A, R, P, "".join(shapes)))


def _notes_xml(notes_text):
    paras = "".join("<a:p><a:r><a:rPr lang=\"en-US\" dirty=\"0\"/>"
                    "<a:t>%s</a:t></a:r></a:p>" % escape(ln)
                    for ln in (notes_text or "").split("\n") if ln.strip())
    if not paras:
        paras = '<a:p><a:endParaRPr lang="en-US"/></a:p>'
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<p:notes xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">'
            '<p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
            '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder"/>'
            '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="685800" y="457200"/>'
            '<a:ext cx="5486400" cy="4114800"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            '<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>%s</p:txBody></p:sp>'
            '</p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>'
            % (A, R, P, paras))


# --------------------------------------------------------------------------
# package-level parts
# --------------------------------------------------------------------------
_CONTENT_TYPES_HEAD = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                       '<Types xmlns="http://schemas.openxmlformats.org/'
                       'package/2006/content-types">'
                       '<Default Extension="rels" ContentType="application/vnd.'
                       'openxmlformats-package.relationships+xml"/>'
                       '<Default Extension="xml" ContentType="application/xml"/>'
                       '<Default Extension="png" ContentType="image/png"/>')

_CT = {
    "pres": "application/vnd.openxmlformats-officedocument.presentationml."
            "presentation.main+xml",
    "master": "application/vnd.openxmlformats-officedocument.presentationml."
              "slideMaster+xml",
    "layout": "application/vnd.openxmlformats-officedocument.presentationml."
              "slideLayout+xml",
    "theme": "application/vnd.openxmlformats-officedocument.theme+xml",
    "slide": "application/vnd.openxmlformats-officedocument.presentationml."
             "slide+xml",
    "notes": "application/vnd.openxmlformats-officedocument.presentationml."
             "notesSlide+xml",
    "notesMaster": "application/vnd.openxmlformats-officedocument."
                   "presentationml.notesMaster+xml",
    "core": "application/vnd.openxmlformats-package.core-properties+xml",
    "app": "application/vnd.openxmlformats-officedocument.extended-properties+xml",
}

_ROOT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
              '2006/relationships">'
              '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
              'officeDocument/2006/relationships/officeDocument" '
              'Target="ppt/presentation.xml"/>'
              '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
              'package/2006/relationships/metadata/core-properties" '
              'Target="docProps/core.xml"/>'
              '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/'
              'officeDocument/2006/relationships/extended-properties" '
              'Target="docProps/app.xml"/>'
              "</Relationships>")

_MASTER_XML = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<p:sldMaster xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">'
               '<p:cSld><p:spTree>'
               '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
               '</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
               '<a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/>'
               '</a:xfrm></p:grpSpPr></p:spTree></p:cSld>'
               '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
               'accent1="accent1" accent2="accent2" accent3="accent3" '
               'accent4="accent4" accent5="accent5" accent6="accent6" '
               'hlink="hlink" folHlink="folHlink"/>'
               '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/>'
               '</p:sldLayoutIdLst>'
               '<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr/></a:lvl1pPr>'
               '</p:titleStyle><p:bodyStyle><a:lvl1pPr><a:defRPr/></a:lvl1pPr>'
               '</p:bodyStyle><p:otherStyle><a:lvl1pPr><a:defRPr/></a:lvl1pPr>'
               '</p:otherStyle></p:txStyles></p:sldMaster>' % (A, R, P))

_MASTER_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                '2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/slideLayout" '
                'Target="../slideLayouts/slideLayout1.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/theme" '
                'Target="../theme/theme1.xml"/></Relationships>')

_NOTES_MASTER_XML = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                     '<p:notesMaster xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">'
                     '<p:cSld><p:spTree>'
                     '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/>'
                     '<p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
                     '<a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
                     '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
                     '</p:spTree></p:cSld>'
                     '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
                     'accent1="accent1" accent2="accent2" accent3="accent3" '
                     'accent4="accent4" accent5="accent5" accent6="accent6" '
                     'hlink="hlink" folHlink="folHlink"/>'
                     '<p:notesStyle><a:lvl1pPr><a:defRPr/></a:lvl1pPr>'
                     '</p:notesStyle></p:notesMaster>' % (A, R, P))

_NOTES_MASTER_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                      '<Relationships xmlns="http://schemas.openxmlformats.org/'
                      'package/2006/relationships">'
                      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.'
                      'org/officeDocument/2006/relationships/theme" '
                      'Target="../theme/theme1.xml"/></Relationships>')

_LAYOUT_XML = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<p:sldLayout xmlns:a="%s" xmlns:r="%s" xmlns:p="%s" type="blank">'
               '<p:cSld name="Blank"><p:spTree>'
               '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
               '</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
               '<a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/>'
               '</a:xfrm></p:grpSpPr></p:spTree></p:cSld>'
               '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
               % (A, R, P))

_LAYOUT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                '2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/slideMaster" '
                'Target="../slideMasters/slideMaster1.xml"/></Relationships>')

_CORE_XML = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
             '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/'
             'package/2006/metadata/core-properties" xmlns:dc="http://purl.org/'
             'dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
             'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
             '<dc:title>%s</dc:title><dc:creator>geometry-typeset-deck</dc:creator>'
             '<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
             '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>'
             '</cp:coreProperties>')


# --------------------------------------------------------------------------
# main forge routine (importable: used by examples/make_fixture.py)
# --------------------------------------------------------------------------
def forge(out_path, layout, theme=None, template_path=None, images_dir=None,
          theme_bytes=None):
    """Write a complete pptx to out_path from a layout dict.

    theme_bytes, when given, are written verbatim as ppt/theme/theme1.xml
    (theme cloning); otherwise template_path is probed for theme bytes;
    otherwise the built-in default theme is used. Returns a stats dict.
    """
    slides = layout.get("slides", [])
    theme_xml = theme_bytes or read_template_theme(template_path) \
        or default_theme_xml().encode("utf-8")
    theme_cloned = bool(theme_bytes or read_template_theme(template_path))

    media = []           # (arcname, absolute path)
    slide_parts = []     # (name, xml, rels_xml, notes_xml_or_None)
    for idx, slide in enumerate(slides, start=1):
        slide = dict(slide)
        slide["_images_dir"] = images_dir or ""
        rels = []
        xml = _slide_xml(slide, layout, rels, [2])
        rel_entries = [
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/slideLayout" '
            'Target="../slideLayouts/slideLayout1.xml"/>']
        for rel_id, target, abspath in rels:
            arc = "ppt/media/%s" % os.path.basename(abspath)
            media.append((arc, abspath))
            rel_entries.append(
                '<Relationship Id="%s" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/image" Target="%s"/>'
                % (rel_id, target))
        notes_xml = None
        if slide.get("notes"):
            notes_xml = _notes_xml(slide["notes"])
            rel_entries.append(
                '<Relationship Id="rIdNotes" Type="http://schemas.openxmlformats.'
                'org/officeDocument/2006/relationships/notesSlide" '
                'Target="../notesSlides/notesSlide%d.xml"/>' % idx)
        rels_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/'
                    'package/2006/relationships">%s</Relationships>'
                    % "".join(rel_entries))
        slide_parts.append((idx, xml, rels_xml, notes_xml))

    # presentation.xml + its rels
    has_notes = any(sp[3] for sp in slide_parts)
    sld_ids = "".join('<p:sldId id="%d" r:id="rId%d"/>' % (256 + i, 2 + i)
                      for i in range(len(slides)))
    notes_master_id = ('<p:notesMasterIdLst><p:notesMasterId r:id="rIdNM"/>'
                       '</p:notesMasterIdLst>' if has_notes else '')
    pres_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<p:presentation xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">'
                '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/>'
                '</p:sldMasterIdLst>%s<p:sldIdLst>%s</p:sldIdLst>'
                '<p:sldSz cx="%d" cy="%d" type="custom"/>'
                '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
                % (A, R, P, notes_master_id, sld_ids,
                   layout["slide_w_emu"], layout["slide_h_emu"]))
    pres_rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.'
                 'org/officeDocument/2006/relationships/slideMaster" '
                 'Target="slideMasters/slideMaster1.xml"/>']
    if has_notes:
        pres_rels.append('<Relationship Id="rIdNM" Type="http://schemas.openxml'
                         '.formats.org/officeDocument/2006/relationships/'
                         'notesMaster" Target="notesMasters/notesMaster1.xml"/>')
    for i in range(len(slides)):
        pres_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxml'
                         'formats.org/officeDocument/2006/relationships/slide" '
                         'Target="slides/slide%d.xml"/>' % (2 + i, 1 + i))
    pres_rels_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                     '<Relationships xmlns="http://schemas.openxmlformats.org/'
                     'package/2006/relationships">%s</Relationships>'
                     % "".join(pres_rels))

    overrides = [
        '<Override PartName="/ppt/presentation.xml" ContentType="%s"/>' % _CT["pres"],
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="%s"/>'
        % _CT["master"],
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="%s"/>'
        % _CT["layout"],
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="%s"/>' % _CT["theme"],
        '<Override PartName="/docProps/core.xml" ContentType="%s"/>' % _CT["core"],
        '<Override PartName="/docProps/app.xml" ContentType="%s"/>' % _CT["app"],
    ]
    if has_notes:
        overrides.append('<Override PartName="/ppt/notesMasters/notesMaster1.xml" '
                         'ContentType="%s"/>' % _CT["notesMaster"])
    for idx, _, _, notes_xml in slide_parts:
        overrides.append('<Override PartName="/ppt/slides/slide%d.xml" '
                         'ContentType="%s"/>' % (idx, _CT["slide"]))
        if notes_xml:
            overrides.append('<Override PartName="/ppt/notesSlides/notesSlide%d.'
                             'xml" ContentType="%s"/>' % (idx, _CT["notes"]))
    content_types = _CONTENT_TYPES_HEAD + "".join(overrides) + "</Types>"

    title = layout.get("meta", {}).get("title", "presentation")
    app_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument'
               '/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.'
               'org/officeDocument/2006/docPropsVTypes">'
               '<Application>geometry-typeset-deck</Application>'
               '<Slides>%d</Slides></Properties>' % len(slides))

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        _writestr(zf, "[Content_Types].xml", content_types)
        _writestr(zf, "_rels/.rels", _ROOT_RELS)
        _writestr(zf, "docProps/core.xml",
                  _CORE_XML % (escape(title), FIXED_TIMESTAMP, FIXED_TIMESTAMP))
        _writestr(zf, "docProps/app.xml", app_xml)
        _writestr(zf, "ppt/presentation.xml", pres_xml)
        _writestr(zf, "ppt/_rels/presentation.xml.rels", pres_rels_xml)
        _writestr(zf, "ppt/slideMasters/slideMaster1.xml", _MASTER_XML)
        _writestr(zf, "ppt/slideMasters/_rels/slideMaster1.xml.rels", _MASTER_RELS)
        _writestr(zf, "ppt/slideLayouts/slideLayout1.xml", _LAYOUT_XML)
        _writestr(zf, "ppt/slideLayouts/_rels/slideLayout1.xml.rels", _LAYOUT_RELS)
        _writestr(zf, "ppt/theme/theme1.xml", theme_xml)
        if has_notes:
            _writestr(zf, "ppt/notesMasters/notesMaster1.xml", _NOTES_MASTER_XML)
            _writestr(zf, "ppt/notesMasters/_rels/notesMaster1.xml.rels",
                      _NOTES_MASTER_RELS)
        for idx, xml, rels_xml, notes_xml in slide_parts:
            _writestr(zf, "ppt/slides/slide%d.xml" % idx, xml)
            _writestr(zf, "ppt/slides/_rels/slide%d.xml.rels" % idx, rels_xml)
            if notes_xml:
                _writestr(zf, "ppt/notesSlides/notesSlide%d.xml" % idx, notes_xml)
                notes_rels = ('<?xml version="1.0" encoding="UTF-8" '
                              'standalone="yes"?>\n'
                              '<Relationships xmlns="http://schemas.openxmlformats.'
                              'org/package/2006/relationships">'
                              '<Relationship Id="rId1" Type="http://schemas.'
                              'openxmlformats.org/officeDocument/2006/'
                              'relationships/slide" Target="../slides/slide%d.xml"/>'
                              '<Relationship Id="rId2" Type="http://schemas.'
                              'openxmlformats.org/officeDocument/2006/'
                              'relationships/notesMaster" '
                              'Target="../notesMasters/notesMaster1.xml"/>'
                              '</Relationships>' % idx)
                _writestr(zf, "ppt/notesSlides/_rels/notesSlide%d.xml.rels" % idx,
                          notes_rels)
        for arc, abspath in media:
            with open(abspath, "rb") as fh:
                _writestr(zf, arc, fh.read())

    return {"slides": len(slides), "media": len(media),
            "theme_cloned": theme_cloned, "out": out_path}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Forge an editable pptx from layout.json.")
    ap.add_argument("--layout", required=True)
    ap.add_argument("--theme", required=True)
    ap.add_argument("--template", default=None)
    ap.add_argument("--images", default=None)
    ap.add_argument("--out", default=os.path.join(
        os.environ.get("CASE_OUTPUT_DIR", "/app/output"), "presentation.pptx"))
    args = ap.parse_args(argv)

    with open(args.layout, encoding="utf-8") as fh:
        layout = json.load(fh)
    with open(args.theme, encoding="utf-8") as fh:
        theme = json.load(fh)
    stats = forge(args.out, layout, theme=theme, template_path=args.template,
                  images_dir=args.images)
    print("deck_forge: %d slide(s), %d media file(s), theme_cloned=%s -> %s"
          % (stats["slides"], stats["media"], stats["theme_cloned"], stats["out"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
