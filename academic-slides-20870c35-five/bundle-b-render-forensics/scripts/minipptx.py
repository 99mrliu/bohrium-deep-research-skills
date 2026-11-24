#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""minipptx.py —— stdlib-only 最小但合法的 PPTX 生成器与校验器。

python-pptx 不可用时的真实兜底：只用 zipfile + 手写 OOXML，从
deck_spec.json（见 references/deck-spec.md）构建可打开、可编辑的 .pptx，
包含：标题文本框、正文项目符号、每页讲稿备注（notes slide）、可选 PNG 插图。

用法：
  python3 minipptx.py build deck_spec.json -o deck.pptx
  python3 minipptx.py verify deck.pptx

退出码（两个子命令一致）：
  0  成功 / 校验通过
  1  校验发现结构性违例（verify）/ spec 内容违例（build）
  2  用法 / IO 错误（文件缺失、JSON 损坏、缺字段等）

verify 检查：zip 完整性、[Content_Types].xml/_rels/presentation.xml 必备件、
每个 .xml/.rels 部件 XML well-formed、slide 数与 presentation.xml 的
sldIdLst 一致且 rels 可解析、每个 slide 都有对应 notesSlide 部件。
"""

import argparse
import json
import os
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

RT_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def T(tail):
    """relationship Type URI：office 部件类型挂在 officeDocument 命名空间下；
    core-properties 等包级元数据挂在 package 命名空间下。"""
    if tail.startswith("metadata/"):
        return NS_REL + "/" + tail
    return RT_OFFICE + "/" + tail

EMU = 914400  # 1 inch
DEFAULT_CX = 9144000   # 10in (4:3)
DEFAULT_CY = 6858000   # 7.5in


class SpecError(Exception):
    """deck_spec 内容违例 → build exit 1。"""


class UsageError(Exception):
    """用法 / IO 错误 → exit 2。"""


# ------------------------------------------------------------ XML 片段

def _decl(body):
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + body


def content_types_xml(n_slides, has_png):
    parts = [
        '<Types xmlns="{}">'.format(NS_CT),
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    if has_png:
        parts.append('<Default Extension="png" ContentType="image/png"/>')
    parts += [
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
        '<Override PartName="/ppt/theme/theme2.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    for i in range(1, n_slides + 1):
        parts.append('<Override PartName="/ppt/slides/slide{}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'.format(i))
        parts.append('<Override PartName="/ppt/notesSlides/notesSlide{}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'.format(i))
    parts.append('</Types>')
    return _decl("".join(parts))


def rels_xml(entries):
    """entries: [(Id, Type_tail, Target)]"""
    body = "".join(
        '<Relationship Id="{}" Type="{}" Target="{}"/>'.format(rid, T(tail), target)
        for rid, tail, target in entries)
    return _decl('<Relationships xmlns="{}">{}</Relationships>'.format(NS_REL, body))


def core_xml(title):
    return _decl(
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>{}</dc:title>'
        '<dc:creator>minipptx.py</dc:creator>'
        '</cp:coreProperties>'.format(escape(title)))


def app_xml(n_slides):
    return _decl(
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>minipptx.py</Application>'
        '<Slides>{}</Slides>'
        '<Notes>{}</Notes>'
        '</Properties>'.format(n_slides, n_slides))


def presentation_xml(n_slides, cx, cy):
    sld_ids = "".join(
        '<p:sldId id="{}" r:id="{}"/>'.format(255 + i, "rId{}".format(i + 2))
        for i in range(1, n_slides + 1))
    return _decl(
        '<p:presentation xmlns:a="{a}" xmlns:r="{r}" xmlns:p="{p}">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        '<p:notesMasterIdLst><p:notesMasterId r:id="rId2"/></p:notesMasterIdLst>'
        '<p:sldIdLst>{sld}</p:sldIdLst>'
        '<p:sldSz cx="{cx}" cy="{cy}" type="screen4x3"/>'
        '<p:notesSz cx="6858000" cy="9144000"/>'
        '<p:defaultTextStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr></p:defaultTextStyle>'
        '</p:presentation>'.format(a=NS_A, r=NS_R, p=NS_P, sld=sld_ids, cx=cx, cy=cy))


def theme_xml(name):
    return _decl(
        '<a:theme xmlns:a="{a}" name="{n}">'
        '<a:themeElements>'
        '<a:clrScheme name="{n}">'
        '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
        '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
        '<a:dk2><a:srgbClr val="1F497D"/></a:dk2>'
        '<a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
        '<a:accent1><a:srgbClr val="4F81BD"/></a:accent1>'
        '<a:accent2><a:srgbClr val="C0504D"/></a:accent2>'
        '<a:accent3><a:srgbClr val="9BBB59"/></a:accent3>'
        '<a:accent4><a:srgbClr val="8064A2"/></a:accent4>'
        '<a:accent5><a:srgbClr val="4BACC6"/></a:accent5>'
        '<a:accent6><a:srgbClr val="F79646"/></a:accent6>'
        '<a:hlink><a:srgbClr val="0000FF"/></a:hlink>'
        '<a:folHlink><a:srgbClr val="800080"/></a:folHlink>'
        '</a:clrScheme>'
        '<a:fontScheme name="{n}">'
        '<a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
        '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
        '</a:fontScheme>'
        '<a:fmtScheme name="{n}">'
        '<a:fillStyleLst>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
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
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '</a:bgFillStyleLst>'
        '</a:fmtScheme>'
        '</a:themeElements>'
        '</a:theme>'.format(a=NS_A, n=escape(name)))


_CLR_MAP = ('<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
            'accent1="accent1" accent2="accent2" accent3="accent3" '
            'accent4="accent4" accent5="accent5" accent6="accent6" '
            'hlink="hlink" folHlink="folHlink"/>')

_EMPTY_GRP = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
              '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
              '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')


def slide_master_xml():
    return _decl(
        '<p:sldMaster xmlns:a="{a}" xmlns:r="{r}" xmlns:p="{p}">'
        '<p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
        '<p:spTree>{grp}</p:spTree></p:cSld>'
        '{clrmap}'
        '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
        '<p:txStyles>'
        '<p:titleStyle><a:lvl1pPr algn="l"><a:defRPr sz="3200" b="1"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill></a:defRPr></a:lvl1pPr></p:titleStyle>'
        '<p:bodyStyle><a:lvl1pPr marL="342900" indent="-342900"><a:defRPr sz="2000"/></a:lvl1pPr></p:bodyStyle>'
        '<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle>'
        '</p:txStyles>'
        '</p:sldMaster>'.format(a=NS_A, r=NS_R, p=NS_P, grp=_EMPTY_GRP, clrmap=_CLR_MAP))


def slide_layout_xml():
    return _decl(
        '<p:sldLayout xmlns:a="{a}" xmlns:r="{r}" xmlns:p="{p}" type="blank" preserve="1">'
        '<p:cSld name="Blank"><p:spTree>{grp}</p:spTree></p:cSld>'
        '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
        '</p:sldLayout>'.format(a=NS_A, r=NS_R, p=NS_P, grp=_EMPTY_GRP))


def notes_master_xml():
    ph = ('<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder 1"/>'
          '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
          '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
          '<p:spPr><a:xfrm><a:off x="685800" y="4343400"/><a:ext cx="5486400" cy="4114800"/></a:xfrm>'
          '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
          '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>')
    return _decl(
        '<p:notesMaster xmlns:a="{a}" xmlns:r="{r}" xmlns:p="{p}">'
        '<p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
        '<p:spTree>{grp}{ph}</p:spTree></p:cSld>'
        '{clrmap}'
        '<p:notesStyle><a:lvl1pPr><a:defRPr sz="1200"/></a:lvl1pPr></p:notesStyle>'
        '</p:notesMaster>'.format(a=NS_A, r=NS_R, p=NS_P, grp=_EMPTY_GRP, ph=ph,
                                  clrmap=_CLR_MAP))


def _text_sp(sp_id, name, x, y, cx, cy, paragraphs, font_sz, bold=False):
    """paragraphs: [str]；每个字符串一个 <a:p>。"""
    paras = []
    for text in paragraphs:
        paras.append(
            '<a:p><a:pPr marL="342900" indent="-342900"><a:buChar char="\u2022"/></a:pPr>'
            '<a:r><a:rPr lang="en-US" sz="{sz}"{b}/><a:t>{t}</a:t></a:r></a:p>'.format(
                sz=font_sz, b=' b="1"' if bold else "", t=escape(text)))
    if not paras:
        paras.append('<a:p><a:endParaRPr lang="en-US"/></a:p>')
    return (
        '<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{n}"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square"><a:normAutofit/></a:bodyPr><a:lstStyle/>'
        '{paras}</p:txBody></p:sp>'.format(i=sp_id, n=escape(name), x=x, y=y,
                                           cx=cx, cy=cy, paras="".join(paras)))


def _title_sp(sp_id, x, y, cx, cy, title):
    return (
        '<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="Title {i}"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square"/><a:lstStyle/>'
        '<a:p><a:r><a:rPr lang="en-US" sz="3200" b="1">'
        '<a:solidFill><a:srgbClr val="1F497D"/></a:solidFill></a:rPr>'
        '<a:t>{t}</a:t></a:r></a:p></p:txBody></p:sp>'.format(
            i=sp_id, x=x, y=y, cx=cx, cy=cy, t=escape(title)))


def _pic(sp_id, name, rel_id, x, y, cx, cy):
    return (
        '<p:pic><p:nvPicPr><p:cNvPr id="{i}" name="{n}"/>'
        '<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
        '<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'.format(
            i=sp_id, n=escape(name), rid=rel_id, x=x, y=y, cx=cx, cy=cy))


def slide_xml(title, bullets, image_rel_id, image_box, cx, cy):
    margin = 457200  # 0.5in
    title_h = 1005840  # 1.1in
    shapes = [_title_sp(2, margin, 274320, cx - 2 * margin, title_h, title)]
    body_top = 274320 + title_h + 137160
    if image_rel_id:
        half = (cx - 2 * margin) // 2
        shapes.append(_text_sp(3, "Body", margin, body_top,
                               half - 91440, cy - body_top - margin,
                               bullets, 1800))
        shapes.append(_pic(4, "Figure 1", image_rel_id,
                           margin + half + 91440, body_top,
                           image_box[0], image_box[1]))
    else:
        shapes.append(_text_sp(3, "Body", margin, body_top,
                               cx - 2 * margin, cy - body_top - margin,
                               bullets, 1800))
    return _decl(
        '<p:sld xmlns:a="{a}" xmlns:r="{r}" xmlns:p="{p}">'
        '<p:cSld><p:spTree>{grp}{shapes}</p:spTree></p:cSld>'
        '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
        '</p:sld>'.format(a=NS_A, r=NS_R, p=NS_P, grp=_EMPTY_GRP,
                          shapes="".join(shapes)))


def notes_slide_xml(notes_text):
    paras = "".join(
        '<a:p><a:r><a:rPr lang="en-US" sz="1200"/><a:t>{}</a:t></a:r></a:p>'.format(
            escape(line))
        for line in notes_text.split("\n")) or '<a:p><a:endParaRPr lang="en-US"/></a:p>'
    return _decl(
        '<p:notes xmlns:a="{a}" xmlns:r="{r}" xmlns:p="{p}">'
        '<p:cSld><p:spTree>{grp}'
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvSpPr>'
        '<p:nvPr><p:ph type="sldImg" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
        '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        '<p:nvPr><p:ph type="body" idx="2"/></p:nvPr></p:nvSpPr><p:spPr/>'
        '<p:txBody><a:bodyPr/><a:lstStyle/>{paras}</p:txBody></p:sp>'
        '</p:spTree></p:cSld>'
        '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>'
        '</p:notes>'.format(a=NS_A, r=NS_R, p=NS_P, grp=_EMPTY_GRP, paras=paras))


# ------------------------------------------------------------ PNG 尺寸

def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(33)
    if len(head) < 33 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise UsageError("不是合法 PNG 文件：{}".format(path))
    width, height = struct.unpack(">II", head[16:24])
    if width <= 0 or height <= 0:
        raise UsageError("PNG 尺寸非法：{}".format(path))
    return width, height


# ------------------------------------------------------------ build

def load_spec(path):
    if not os.path.isfile(path):
        raise UsageError("deck_spec.json 不存在：{}".format(path))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UsageError("deck_spec.json 读取或解析失败：{}".format(exc))
    if not isinstance(spec, dict):
        raise UsageError("deck_spec.json 顶层必须是对象")
    slides = spec.get("slides")
    if not isinstance(slides, list) or not slides:
        raise SpecError("deck_spec 必须含非空 slides 数组")
    for i, s in enumerate(slides, start=1):
        if not isinstance(s, dict):
            raise SpecError("slides[{}] 必须是对象".format(i))
        if not isinstance(s.get("title"), str) or not s["title"].strip():
            raise SpecError("slides[{}] 缺非空 title".format(i))
        if "bullets" in s and not (isinstance(s["bullets"], list) and
                                   all(isinstance(b, str) for b in s["bullets"])):
            raise SpecError("slides[{}] bullets 必须是字符串数组".format(i))
        if "notes" in s and not isinstance(s["notes"], str):
            raise SpecError("slides[{}] notes 必须是字符串".format(i))
        if "image" in s:
            img = s["image"]
            if not isinstance(img, dict) or not isinstance(img.get("path"), str):
                raise SpecError("slides[{}] image 必须含 path 字符串".format(i))
    size = spec.get("slide_size", {})
    cx = int(size.get("cx", DEFAULT_CX))
    cy = int(size.get("cy", DEFAULT_CY))
    if cx < 1000000 or cy < 1000000:
        raise SpecError("slide_size 过小：cx={} cy={}".format(cx, cy))
    return spec, slides, cx, cy


def build(spec_path, out_path):
    spec, slides, cx, cy = load_spec(spec_path)
    spec_dir = os.path.dirname(os.path.abspath(spec_path))

    # 收集图片（同一张图可能被多页引用）
    image_parts = {}   # spec 相对路径 -> (part_name, abs_path, w_px, h_px)
    for s in slides:
        img = s.get("image")
        if not img:
            continue
        p = img["path"]
        abs_p = p if os.path.isabs(p) else os.path.join(spec_dir, p)
        if not os.path.isfile(abs_p):
            raise UsageError("插图 PNG 不存在：{}".format(abs_p))
        if p not in image_parts:
            w, h = png_size(abs_p)
            image_parts[p] = ("ppt/media/image{}.png".format(len(image_parts) + 1),
                              abs_p, w, h)

    title = spec.get("deck_title") or slides[0]["title"]
    n = len(slides)
    parts = {}  # part_name -> bytes
    put = lambda name, text: parts.__setitem__(name, text.encode("utf-8"))

    put("[Content_Types].xml", content_types_xml(n, bool(image_parts)))
    put("_rels/.rels", rels_xml([
        ("rId1", "officeDocument", "ppt/presentation.xml"),
        ("rId2", "metadata/core-properties", "docProps/core.xml"),
        ("rId3", "extended-properties", "docProps/app.xml"),
    ]))
    put("docProps/core.xml", core_xml(title))
    put("docProps/app.xml", app_xml(n))
    put("ppt/presentation.xml", presentation_xml(n, cx, cy))
    pres_rels = [("rId1", "slideMaster", "slideMasters/slideMaster1.xml"),
                 ("rId2", "notesMaster", "notesMasters/notesMaster1.xml")]
    for i in range(1, n + 1):
        pres_rels.append(("rId{}".format(i + 2), "slide", "slides/slide{}.xml".format(i)))
    put("ppt/_rels/presentation.xml.rels", rels_xml(pres_rels))
    put("ppt/slideMasters/slideMaster1.xml", slide_master_xml())
    put("ppt/slideMasters/_rels/slideMaster1.xml.rels", rels_xml([
        ("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
        ("rId2", "theme", "../theme/theme1.xml"),
    ]))
    put("ppt/slideLayouts/slideLayout1.xml", slide_layout_xml())
    put("ppt/slideLayouts/_rels/slideLayout1.xml.rels", rels_xml([
        ("rId1", "slideMaster", "../slideMasters/slideMaster1.xml"),
    ]))
    put("ppt/notesMasters/notesMaster1.xml", notes_master_xml())
    put("ppt/notesMasters/_rels/notesMaster1.xml.rels", rels_xml([
        ("rId1", "theme", "../theme/theme2.xml"),
    ]))
    put("ppt/theme/theme1.xml", theme_xml("minipptx"))
    put("ppt/theme/theme2.xml", theme_xml("minipptx-notes"))

    for i, s in enumerate(slides, start=1):
        img = s.get("image")
        img_rel_id = None
        img_box = (0, 0)
        slide_rels = [("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
                      ("rId2", "notesSlide", "../notesSlides/notesSlide{}.xml".format(i))]
        if img:
            part_name, abs_p, w_px, h_px = image_parts[img["path"]]
            img_rel_id = "rId3"
            slide_rels.append((img_rel_id, "image", "../media/" + os.path.basename(part_name)))
            # 图放右半栏，保持纵横比
            half = (cx - 2 * 457200) // 2 - 91440
            box_w = half
            box_h = int(box_w * h_px / w_px)
            max_h = cy - 274320 - 1005840 - 137160 - 457200
            if box_h > max_h:
                box_h = max_h
                box_w = int(box_h * w_px / h_px)
            img_box = (box_w, box_h)
        put("ppt/slides/slide{}.xml".format(i),
            slide_xml(s["title"], s.get("bullets", []), img_rel_id, img_box, cx, cy))
        put("ppt/slides/_rels/slide{}.xml.rels".format(i), rels_xml(slide_rels))
        put("ppt/notesSlides/notesSlide{}.xml".format(i),
            notes_slide_xml(s.get("notes", "")))
        put("ppt/notesSlides/_rels/notesSlide{}.xml.rels".format(i), rels_xml([
            ("rId1", "notesMaster", "../notesMasters/notesMaster1.xml"),
            ("rId2", "slide", "../slides/slide{}.xml".format(i)),
        ]))

    for part_name, abs_p, _w, _h in image_parts.values():
        with open(abs_p, "rb") as fh:
            parts[part_name] = fh.read()

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(parts):
            zf.writestr(name, parts[name])
    return len(parts), n


# ------------------------------------------------------------ verify

def verify(pptx_path):
    problems = []
    if not os.path.isfile(pptx_path):
        raise UsageError("pptx 不存在：{}".format(pptx_path))
    try:
        zf = zipfile.ZipFile(pptx_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise UsageError("无法作为 zip 打开：{}".format(exc))
    with zf:
        if zf.testzip() is not None:
            problems.append("zip CRC 校验失败：{}".format(zf.testzip()))
        names = set(zf.namelist())
        for required in ("[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"):
            if required not in names:
                problems.append("缺必备部件：{}".format(required))
        # 全部 XML 部件 well-formed
        parsed = {}
        for name in sorted(names):
            if name.endswith(".xml") or name.endswith(".rels"):
                try:
                    parsed[name] = ET.fromstring(zf.read(name))
                except ET.ParseError as exc:
                    problems.append("XML 损坏：{}: {}".format(name, exc))
        # slide 数
        slide_parts = sorted(
            n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
        pres = parsed.get("ppt/presentation.xml")
        sld_ids = []
        if pres is not None:
            sld_ids = pres.findall(
                "{{{}}}sldIdLst/{{{}}}sldId".format(NS_P, NS_P))
        if pres is not None and len(sld_ids) != len(slide_parts):
            problems.append("slide 数不一致：presentation.xml 声明 {} 个，"
                            "实际 {} 个 slide 部件".format(len(sld_ids), len(slide_parts)))
        if not slide_parts:
            problems.append("没有任何 slide 部件")
        # presentation rels 中每个 sldId 的 r:id 可解析
        pres_rels = parsed.get("ppt/_rels/presentation.xml.rels")
        if pres_rels is not None and sld_ids:
            rel_map = {rel.get("Id"): rel.get("Target")
                       for rel in pres_rels.findall("{{{}}}Relationship".format(NS_REL))}
            for sld in sld_ids:
                rid = sld.get("{{{}}}id".format(NS_R))
                target = rel_map.get(rid)
                if not target:
                    problems.append("sldId 引用的 {} 在 presentation.xml.rels 中不存在".format(rid))
                elif "ppt/" + target not in names:
                    problems.append("slide rel 目标缺失：{}".format(target))
        else:
            if sld_ids:
                problems.append("缺 ppt/_rels/presentation.xml.rels")
        # 每个 slide 必须有 notesSlide rel 且部件存在
        notes_parts = sorted(
            n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n))
        for slide_part in slide_parts:
            m = re.search(r"slide(\d+)\.xml$", slide_part)
            idx = m.group(1)
            rels_name = "ppt/slides/_rels/slide{}.xml.rels".format(idx)
            rels = parsed.get(rels_name)
            if rels is None:
                problems.append("缺 {}".format(rels_name))
                continue
            notes_targets = [rel.get("Target") for rel in
                             rels.findall("{{{}}}Relationship".format(NS_REL))
                             if rel.get("Type", "").endswith("/notesSlide")]
            if not notes_targets:
                problems.append("{} 没有 notesSlide 关系".format(slide_part))
            else:
                target = notes_targets[0].replace("../", "ppt/")
                if target not in names:
                    problems.append("notesSlide 部件缺失：{}".format(target))
        if len(notes_parts) != len(slide_parts):
            problems.append("notes 数（{}）与 slide 数（{}）不一致".format(
                len(notes_parts), len(slide_parts)))
    return problems, len(slide_parts) if 'slide_parts' in dir() else 0, len(notes_parts) if 'notes_parts' in dir() else 0


# ------------------------------------------------------------ main

def main(argv=None):
    parser = argparse.ArgumentParser(description="stdlib-only 最小 PPTX 生成器/校验器")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="从 deck_spec.json 构建 pptx")
    p_build.add_argument("spec", help="deck_spec.json 路径")
    p_build.add_argument("-o", "--output", required=True, help="输出 .pptx 路径")
    p_verify = sub.add_parser("verify", help="校验 pptx 结构")
    p_verify.add_argument("pptx", help="待校验 .pptx 路径")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "build":
            n_parts, n_slides = build(args.spec, args.output)
            print("BUILD OK: {} ({} slides, {} parts)".format(
                args.output, n_slides, n_parts))
            return 0
        else:
            problems, n_slides, n_notes = verify(args.pptx)
            for p in problems:
                print("V: {}".format(p))
            if problems:
                print("VERIFY: FAIL ({} 个问题)".format(len(problems)))
                return 1
            print("VERIFY: PASS ({} slides, {} notes slides)".format(n_slides, n_notes))
            return 0
    except SpecError as exc:
        print("deck_spec 内容违例: {}".format(exc), file=sys.stderr)
        return 1
    except UsageError as exc:
        print("用法/IO 错误: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
