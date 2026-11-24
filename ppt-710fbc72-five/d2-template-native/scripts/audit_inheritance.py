#!/usr/bin/env python3
"""XML-level template-inheritance audit (THE SPIKE of template-native-deck).

Pure stdlib (zipfile + xml.etree). Unzips the built deck and verifies, per
slide, against the original template:

  (a) slide -> layout -> master -> theme relationship chain resolves
      (every r:id target exists in the package; nothing dangles);
  (b) every placeholder idx used on the slide exists in its layout
      (no invented idx);
  (c) the layout's name is a member of the template inventory;
  (d) slide dimensions equal the template's;
  (e) the theme part reached through the chain is byte-identical to the
      template's theme (sha256 fingerprint match -> theme fonts/colors
      preserved);
  (f) the slide's layout part is byte-identical to one of the template's
      own layout parts (no foreign/default-template layout).

Writes inheritance_report.json: {per_slide: [...], theme_preserved,
overall_pass, ...}. overall_pass=false must block delivery (see SKILL.md).

Usage:
    python3 audit_inheritance.py --deck deck.pptx --template template.pptx \
        --inventory template_inventory.json --out inheritance_report.json
"""
import argparse
import hashlib
import json
import posixpath
import sys
import zipfile
from xml.etree import ElementTree as ET

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
RT_SLIDE_LAYOUT = R_NS + "/slideLayout"
RT_SLIDE_MASTER = R_NS + "/slideMaster"
RT_THEME = R_NS + "/theme"
RT_SLIDE = R_NS + "/slide"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rels_path_for(part: str) -> str:
    d = posixpath.dirname(part)
    return posixpath.join(d, "_rels", posixpath.basename(part) + ".rels")


def load_rels(zf: zipfile.ZipFile, part: str) -> dict:
    """rId -> {type, target(abs part path)} for a part; {} if no rels."""
    path = rels_path_for(part)
    if path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(path))
    base = posixpath.dirname(part)
    rels = {}
    for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        target = rel.get("Target")
        if rel.get("TargetMode") == "External":
            resolved = target
        else:
            resolved = posixpath.normpath(posixpath.join(base, target))
        rels[rel.get("Id")] = {"type": rel.get("Type"), "target": resolved}
    return rels


def placeholders_of(xml_bytes: bytes) -> set:
    """Set of (idx, type) for every p:ph in a slide/layout part.
    OOXML defaults: idx defaults to 0, type defaults to 'body'."""
    root = ET.fromstring(xml_bytes)
    out = set()
    for ph in root.iter(f"{{{P_NS}}}ph"):
        idx = int(ph.get("idx", "0"))
        ptype = ph.get("type", "body")
        out.add((idx, ptype))
    return out


def layout_name_of(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    csld = root.find(f"{{{P_NS}}}cSld")
    return csld.get("name") if csld is not None else None


def slide_size(zf: zipfile.ZipFile):
    root = ET.fromstring(zf.read("ppt/presentation.xml"))
    sldsz = root.find(f"{{{P_NS}}}sldSz")
    return (int(sldsz.get("cx")), int(sldsz.get("cy"))) if sldsz is not None \
        else None


def ordered_slide_parts(zf: zipfile.ZipFile):
    """Slide parts in presentation order via presentation.xml rels."""
    root = ET.fromstring(zf.read("ppt/presentation.xml"))
    rels = load_rels(zf, "ppt/presentation.xml")
    parts = []
    lst = root.find(f"{{{P_NS}}}sldIdLst")
    if lst is None:
        return parts
    for sldId in lst.findall(f"{{{P_NS}}}sldId"):
        rid = sldId.get(f"{{{R_NS}}}id")
        rel = rels.get(rid)
        if rel and rel["type"] == RT_SLIDE:
            parts.append(rel["target"])
    return parts


def template_facts(zf: zipfile.ZipFile) -> dict:
    layout_parts = sorted(n for n in zf.namelist()
                          if n.startswith("ppt/slideLayouts/slideLayout")
                          and n.endswith(".xml"))
    layout_hashes = {}
    layout_names = set()
    for part in layout_parts:
        data = zf.read(part)
        layout_hashes[sha(data)] = part
        name = layout_name_of(data)
        if name:
            layout_names.add(name)
    themes = {n: sha(zf.read(n)) for n in sorted(zf.namelist())
              if n.startswith("ppt/theme/") and n.endswith(".xml")}
    return {"slide_size": slide_size(zf),
            "layout_hashes": layout_hashes,
            "layout_names": layout_names,
            "theme_fingerprints": themes}


def audit(deck_path: str, template_path: str) -> dict:
    report = {"deck": deck_path, "template": template_path,
              "per_slide": [], "checks": {}, "theme_preserved": False,
              "overall_pass": False, "failures": []}

    with zipfile.ZipFile(template_path) as tz:
        tfacts = template_facts(tz)
    report["template_theme_fingerprints"] = tfacts["theme_fingerprints"]

    with zipfile.ZipFile(deck_path) as dz:
        names = set(dz.namelist())
        deck_size = slide_size(dz)
        slides = ordered_slide_parts(dz)

        # (d) slide dimensions
        size_ok = deck_size == tfacts["slide_size"]
        report["checks"]["slide_size"] = {
            "deck": deck_size, "template": tfacts["slide_size"],
            "equal": size_ok}
        if not size_ok:
            report["failures"].append("slide_size_mismatch")

        deck_themes = {n: sha(dz.read(n)) for n in sorted(names)
                       if n.startswith("ppt/theme/") and n.endswith(".xml")}
        report["deck_theme_fingerprints"] = deck_themes

        for i, part in enumerate(slides, start=1):
            entry = {"slide": i, "part": part, "ok": True,
                     "chain": {}, "placeholders_used": [],
                     "unknown_placeholder_idx": [], "warnings": []}

            def fail(msg):
                entry["ok"] = False
                report["failures"].append(f"slide{i}:{msg}")

            # (a) relationship chain slide -> layout -> master -> theme
            srels = load_rels(dz, part)
            lay_rel = next((r for r in srels.values()
                            if r["type"] == RT_SLIDE_LAYOUT), None)
            if lay_rel is None:
                fail("no_slideLayout_relationship")
                report["per_slide"].append(entry)
                continue
            lay_part = lay_rel["target"]
            entry["chain"]["layout_part"] = lay_part
            entry["chain"]["layout_exists"] = lay_part in names
            if lay_part not in names:
                fail("dangling_layout_target")
                report["per_slide"].append(entry)
                continue

            lrels = load_rels(dz, lay_part)
            mas_rel = next((r for r in lrels.values()
                            if r["type"] == RT_SLIDE_MASTER), None)
            entry["chain"]["master_part"] = mas_rel["target"] if mas_rel \
                else None
            entry["chain"]["master_exists"] = bool(
                mas_rel and mas_rel["target"] in names)

            theme_part = None
            if entry["chain"]["master_exists"]:
                mrels = load_rels(dz, mas_rel["target"])
                th_rel = next((r for r in mrels.values()
                               if r["type"] == RT_THEME), None)
                theme_part = th_rel["target"] if th_rel else None
            entry["chain"]["theme_part"] = theme_part
            entry["chain"]["theme_exists"] = bool(
                theme_part and theme_part in names)
            if not (entry["chain"]["master_exists"]
                    and entry["chain"]["theme_exists"]):
                fail("broken_master_or_theme_chain")

            # (e) per-slide theme fingerprint via the resolved chain
            if theme_part and theme_part in names:
                th_sha = sha(dz.read(theme_part))
                entry["chain"]["theme_sha256"] = th_sha
                entry["chain"]["theme_matches_template"] = \
                    th_sha in set(tfacts["theme_fingerprints"].values())

            # (b) placeholder idx subset check
            slide_xml = dz.read(part)
            lay_xml = dz.read(lay_part)
            slide_phs = placeholders_of(slide_xml)
            lay_phs = placeholders_of(lay_xml)
            lay_idx = {idx for idx, _ in lay_phs}
            entry["placeholders_used"] = [
                {"idx": idx, "type": t} for idx, t in sorted(slide_phs)]
            for idx, t in sorted(slide_phs):
                if idx not in lay_idx:
                    entry["unknown_placeholder_idx"].append(idx)
                    fail(f"invented_placeholder_idx:{idx}")
                elif (idx, t) not in lay_phs:
                    entry["warnings"].append(
                        f"placeholder idx {idx} type '{t}' differs from "
                        "layout type (idx exists; inherited semantics)")

            # (c) layout name in template inventory
            lname = layout_name_of(lay_xml)
            entry["layout_name"] = lname
            entry["layout_in_template_names"] = \
                lname in tfacts["layout_names"]
            if not entry["layout_in_template_names"]:
                fail(f"layout_name_not_in_template:{lname}")

            # (f) layout part must be one of the template's own layouts
            lhash = sha(lay_xml)
            entry["layout_sha256"] = lhash
            entry["layout_is_template_part"] = \
                lhash in tfacts["layout_hashes"]
            if not entry["layout_is_template_part"]:
                fail("foreign_or_modified_layout_part")

            entry["ok"] = entry["ok"] and not \
                entry["unknown_placeholder_idx"]
            report["per_slide"].append(entry)

    # (e) global theme preservation: deck theme1 fingerprint vs template's
    tpl_fp = tfacts["theme_fingerprints"].get("ppt/theme/theme1.xml")
    dek_fp = deck_themes.get("ppt/theme/theme1.xml")
    report["checks"]["theme"] = {
        "template_fingerprint": tpl_fp, "deck_fingerprint": dek_fp,
        "match": bool(tpl_fp and tpl_fp == dek_fp)}
    report["theme_preserved"] = report["checks"]["theme"]["match"]
    if not report["theme_preserved"]:
        report["failures"].append("theme_fingerprint_mismatch")

    slides_ok = bool(report["per_slide"]) and all(
        s["ok"] for s in report["per_slide"])
    report["checks"]["per_slide_all_ok"] = slides_ok
    report["checks"]["n_slides"] = len(report["per_slide"])
    if not report["per_slide"]:
        report["failures"].append("deck_has_no_slides")

    report["overall_pass"] = bool(
        slides_ok and size_ok and report["theme_preserved"])
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--inventory", default=None,
                    help="optional template_inventory.json for cross-check")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    report = audit(args.deck, args.template)

    if args.inventory:
        try:
            with open(args.inventory, encoding="utf-8") as f:
                inv = json.load(f)
            inv_names = {l["name"] for l in inv.get("layouts", [])}
            inv_fp = inv.get("theme_fingerprint")
            report["inventory_crosscheck"] = {
                "layout_names_match": bool(
                    inv_names and all(
                        s.get("layout_name") in inv_names
                        for s in report["per_slide"])),
                "theme_fingerprint": inv_fp,
                "fingerprint_matches_template": bool(
                    inv_fp and inv_fp in set(
                        report["template_theme_fingerprints"].values())),
            }
        except Exception as exc:  # cross-check is best-effort
            report["inventory_crosscheck"] = {"error": str(exc)}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    status = "PASS" if report["overall_pass"] else "FAIL"
    print(f"[audit_inheritance] {status}: slides={len(report['per_slide'])} "
          f"theme_preserved={report['theme_preserved']} "
          f"failures={len(report['failures'])} -> {args.out}")
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
