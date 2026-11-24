"""deck_common.py — ppt-deck-surgery 共享工具：pptx 软导入加载、逐页文本哈希、主题字节。

所有脚本共用同一套哈希配方，保证 probe / ops / diff / lint / result 口径一致。
引擎优先级：python-pptx（完整） -> stdlib zipfile+ElementTree（只读降级）。
任何情况下本模块本身不崩溃；缺依赖时 load_deck 返回 engine="stdlib-fallback" 的结果。
"""
from __future__ import annotations

import hashlib
import os
import re
import zipfile
import xml.etree.ElementTree as ET

try:
    from pptx import Presentation  # type: ignore

    HAS_PPTX = True
except ImportError:  # 软导入：缺 python-pptx 时降级
    Presentation = None  # type: ignore
    HAS_PPTX = False

_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def slide_text_hash(title: str, body_texts: list[str]) -> str:
    """页文本哈希：仅标题 + 正文形状文本（不含备注）。

    set_notes 类 op 不改变该哈希，因此 surgery_lint 可用它证明未涉及页文本不变。
    """
    h = hashlib.sha1()
    h.update((title or "").encode("utf-8"))
    for t in body_texts:
        h.update(b"\x00")
        h.update((t or "").encode("utf-8"))
    return h.hexdigest()


def slide_full_hash(title: str, body_texts: list[str], notes: str) -> str:
    h = hashlib.sha1()
    h.update(slide_text_hash(title, body_texts).encode("ascii"))
    h.update(b"\x00notes\x00")
    h.update((notes or "").encode("utf-8"))
    return h.hexdigest()


def _load_with_pptx(path: str) -> dict:
    prs = Presentation(path)
    slides = []
    for i, slide in enumerate(prs.slides, start=1):
        title = ""
        body_texts: list[str] = []
        placeholders = []
        for shape in slide.shapes:
            if shape.is_placeholder:
                ph = shape.placeholder_format
                ph_type = str(ph.type)
                text = shape.text_frame.text if shape.has_text_frame else ""
                placeholders.append(
                    {"idx": ph.idx, "type": ph_type, "name": shape.name,
                     "text_preview": (text or "")[:80]}
                )
                if ph.idx == 0 or "TITLE" in ph_type:
                    if not title:
                        title = text or ""
                    continue
            if shape.has_text_frame:
                body_texts.append(shape.text_frame.text or "")
        notes = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text or ""
        slides.append(
            {
                "index": i,
                "layout": slide.slide_layout.name,
                "title": title,
                "body_texts": body_texts,
                "notes": notes,
                "placeholders": placeholders,
                "n_pictures": sum(1 for s in slide.shapes if s.shape_type == 13),
                "text_hash": slide_text_hash(title, body_texts),
                "full_hash": slide_full_hash(title, body_texts, notes),
            }
        )
    return {
        "engine": "python-pptx",
        "path": os.path.abspath(path),
        "slide_count": len(slides),
        "slides": slides,
        "theme": theme_info(path),
    }


def _texts_from_slide_xml(xml_bytes: bytes) -> tuple[str, list[str]]:
    root = ET.fromstring(xml_bytes)
    title = ""
    bodies: list[str] = []
    for sp in root.iter(_P_NS + "sp"):
        texts = [t.text or "" for t in sp.iter(_A_NS + "t")]
        joined = "\n".join(x for x in texts if x)
        is_title = False
        for ph in sp.iter(_P_NS + "ph"):
            if ph.get("type") in ("title", "ctrTitle"):
                is_title = True
                break
        if is_title and not title:
            title = joined
        elif joined:
            bodies.append(joined)
    return title, bodies


def _load_with_stdlib(path: str) -> dict:
    slides = []
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        slide_names = sorted(
            (n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.search(r"(\d+)", n).group(1)),
        )
        notes_map = {}
        for n in names:
            m = re.fullmatch(r"ppt/notesSlides/notesSlide(\d+)\.xml", n)
            if m:
                root = ET.fromstring(zf.read(n))
                notes_map[int(m.group(1))] = "\n".join(
                    t.text or "" for t in root.iter(_A_NS + "t")
                )
        for i, n in enumerate(slide_names, start=1):
            title, bodies = _texts_from_slide_xml(zf.read(n))
            notes = notes_map.get(i, "")
            slides.append(
                {
                    "index": i,
                    "layout": "unknown(stdlib-fallback)",
                    "title": title,
                    "body_texts": bodies,
                    "notes": notes,
                    "placeholders": [],
                    "n_pictures": 0,
                    "text_hash": slide_text_hash(title, bodies),
                    "full_hash": slide_full_hash(title, bodies, notes),
                }
            )
    return {
        "engine": "stdlib-fallback",
        "path": os.path.abspath(path),
        "slide_count": len(slides),
        "slides": slides,
        "theme": theme_info(path),
    }


def theme_bytes(path: str) -> bytes | None:
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if re.fullmatch(r"ppt/theme/theme\d+\.xml", name):
                    return zf.read(name)
    except (zipfile.BadZipFile, OSError):
        return None
    return None


def theme_info(path: str) -> dict:
    data = theme_bytes(path)
    if data is None:
        return {"present": False, "sha1": None, "major_font": None, "minor_font": None}
    text = data.decode("utf-8", errors="replace")
    major = re.search(r"<a:majorFont>\s*<a:latin[^>]*typeface=\"([^\"]*)\"", text)
    minor = re.search(r"<a:minorFont>\s*<a:latin[^>]*typeface=\"([^\"]*)\"", text)
    return {
        "present": True,
        "sha1": hashlib.sha1(data).hexdigest(),
        "major_font": major.group(1) if major else None,
        "minor_font": minor.group(1) if minor else None,
    }


def load_deck(path: str) -> dict:
    """加载 pptx 为结构化 dict。缺 python-pptx 时自动降级只读模式。"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"deck not found: {path}")
    if HAS_PPTX:
        return _load_with_pptx(path)
    return _load_with_stdlib(path)


def dump_json(obj, path: str) -> None:
    import json

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_json(path: str):
    import json

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
