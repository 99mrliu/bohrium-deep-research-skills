#!/usr/bin/env python3
"""Dissect a template/starting PPTX into template_inventory.json.

The inventory is the ONLY legal source of layouts for the slide plan:
slide size, every master, every layout (name/index/part), every placeholder
per layout (idx/type/name/geometry), theme fonts (major/minor latin+ea),
theme color scheme, and a sha256 fingerprint over each theme part's raw XML.

Usage:
    python3 inspect_template.py TEMPLATE.pptx OUT.json
"""
import argparse
import hashlib
import json
import sys
import zipfile
from xml.etree import ElementTree as ET

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_theme(xml_bytes: bytes) -> dict:
    """Extract font scheme and color scheme from a theme XML part."""
    root = ET.fromstring(xml_bytes)
    info = {"major_latin": None, "major_ea": None, "minor_latin": None,
            "minor_ea": None, "colors": {}}
    font_scheme = root.find(f".//{{{A_NS}}}fontScheme")
    if font_scheme is not None:
        for kind in ("majorFont", "minorFont"):
            node = font_scheme.find(f"{{{A_NS}}}{kind}")
            if node is None:
                continue
            latin = node.find(f"{{{A_NS}}}latin")
            ea = node.find(f"{{{A_NS}}}ea")
            prefix = "major" if kind == "majorFont" else "minor"
            info[f"{prefix}_latin"] = latin.get("typeface") if latin is not None else None
            info[f"{prefix}_ea"] = ea.get("typeface") if ea is not None else None
    clr_scheme = root.find(f".//{{{A_NS}}}clrScheme")
    if clr_scheme is not None:
        for child in clr_scheme:
            tag = child.tag.split("}")[-1]
            srgb = child.find(f"{{{A_NS}}}srgbClr")
            sysc = child.find(f"{{{A_NS}}}sysClr")
            if srgb is not None:
                info["colors"][tag] = "#" + srgb.get("val", "")
            elif sysc is not None:
                info["colors"][tag] = "#" + sysc.get("lastClr", sysc.get("val", ""))
    return info


def aspect_label(w: int, h: int) -> str:
    from math import gcd
    g = gcd(w, h)
    return f"{w // g}:{h // g}"


def inspect(template_path: str) -> dict:
    from pptx import Presentation  # imported lazily so --help works without deps

    with open(template_path, "rb") as f:
        source_sha = sha256_bytes(f.read())

    prs = Presentation(template_path)
    inv = {
        "source_path": template_path,
        "source_sha256": source_sha,
        "slide_width_emu": prs.slide_width,
        "slide_height_emu": prs.slide_height,
        "slide_size_inches": [round(prs.slide_width / 914400, 3),
                              round(prs.slide_height / 914400, 3)],
        "aspect": aspect_label(prs.slide_width, prs.slide_height),
        "n_existing_slides": len(prs.slides._sldIdLst),
        "masters": [],
        "layouts": [],
        "themes": {},
        "theme_fingerprint": None,
    }

    # --- theme parts straight from the zip (byte-level, for fingerprint) ---
    with zipfile.ZipFile(template_path) as z:
        for name in sorted(n for n in z.namelist()
                           if n.startswith("ppt/theme/") and n.endswith(".xml")):
            data = z.read(name)
            entry = {"sha256": sha256_bytes(data), "bytes": len(data)}
            entry.update(parse_theme(data))
            inv["themes"][name] = entry
    # primary fingerprint = theme of master 1 (theme1.xml in practice)
    primary = "ppt/theme/theme1.xml"
    if primary in inv["themes"]:
        inv["theme_fingerprint"] = inv["themes"][primary]["sha256"]
    elif inv["themes"]:
        inv["theme_fingerprint"] = next(iter(inv["themes"].values()))["sha256"]

    # --- masters / layouts / placeholders via python-pptx ---
    gidx = 0
    for mi, master in enumerate(prs.slide_masters):
        csld = master.element.find(
            "{http://schemas.openxmlformats.org/presentationml/2006/main}cSld")
        m_entry = {
            "index": mi,
            "name": csld.get("name") if csld is not None else None,
            "part": master.part.partname.lstrip("/"),
            "layout_indices": [],
            "theme_part": f"ppt/theme/theme{mi + 1}.xml",
        }
        for li, layout in enumerate(master.slide_layouts):
            phs = []
            for ph in layout.placeholders:
                fmt = ph.placeholder_format
                phs.append({
                    "idx": fmt.idx,
                    "type": str(fmt.type),
                    "name": ph.name,
                    "x": ph.left, "y": ph.top,
                    "cx": ph.width, "cy": ph.height,
                })
            inv["layouts"].append({
                "index": gidx,
                "master_index": mi,
                "layout_index_in_master": li,
                "name": layout.name,
                "part": layout.part.partname.lstrip("/"),
                "placeholders": phs,
            })
            m_entry["layout_indices"].append(gidx)
            gidx += 1
        inv["masters"].append(m_entry)
    return inv


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("template", help="template or starting-deck .pptx path")
    ap.add_argument("out", help="output template_inventory.json path")
    args = ap.parse_args(argv)
    inv = inspect(args.template)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=2)
    print(f"[inspect_template] masters={len(inv['masters'])} "
          f"layouts={len(inv['layouts'])} "
          f"size={inv['slide_size_inches']}in aspect={inv['aspect']} "
          f"theme_fp={inv['theme_fingerprint'][:12]}... -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
