#!/usr/bin/env python3
"""deck_io.py — read/write academic .pptx decks via pure-stdlib XML surgery.

CENTER OF GRAVITY: edit only what the work order names.  This module reads
a pptx into a flat JSON model and writes a model back to a pptx by touching
ONLY slide parts whose text actually changed (plus the structural parts
presentation.xml / presentation.xml.rels / [Content_Types].xml when slides
are added, deleted or reordered).  Untouched slide XML bytes are copied
unchanged from the source package.

Text-edit policy (simplest lossless-styling approach, documented):
  * every surviving run keeps its run properties (a:rPr) untouched;
  * when a paragraph's text changes, the FULL new text goes into the FIRST
    run (a:r/a:t) and the remaining runs are blanked (a:t = "");
  * a paragraph with no runs gets one synthetic run (a:rPr lang="en-US").

Namespaces are registered explicitly so output never contains ns0: prefixes.
Paragraphs are matched POSITIONALLY between model and part (pids encode the
enumeration order s<slideidx>p<n>; slide body paras and notes paras are
enumerated separately per part, so writing matches per-part by position).

CLI:
  deck_io.py read  --deck X.pptx --out model.json
  deck_io.py write --model model.json --src original.pptx --out new.pptx
"""

import argparse
import hashlib
import json
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

ET.register_namespace("a", A_NS)
ET.register_namespace("p", P_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006")
ET.register_namespace("p14", "http://schemas.microsoft.com/office/powerpoint/2010/main")
ET.register_namespace("a14", "http://schemas.microsoft.com/office/drawing/2010/main")

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def _xml_bytes(root, default_ns=None):
    if default_ns:
        ET.register_namespace("", default_ns)
    return ET.tostring(root, xml_declaration=True, encoding="UTF-8")


# ---------------------------------------------------------------------------
# rels helpers
# ---------------------------------------------------------------------------

def _rels_name(part):
    return posixpath.join(posixpath.dirname(part), "_rels",
                          posixpath.basename(part) + ".rels")


def _read_rels_bytes(data):
    out = {}
    if data is None:
        return out
    root = ET.fromstring(data)
    for rel in root.findall("{%s}Relationship" % REL_NS):
        out[rel.get("Id")] = {"type": rel.get("Type", ""),
                              "target": rel.get("Target")}
    return out


def _resolve(base_part, target):
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_part), target))


def _slide_number(part):
    m = re.search(r"slide(\d+)\.xml$", part, re.IGNORECASE)
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def _para_text(p_elem):
    return "".join((t.text or "")
                   for t in p_elem.findall("{%s}r/{%s}t" % (A_NS, A_NS)))


def _shape_paras(root):
    """Yield (is_title, para_element) for each a:p inside a p:sp, in order."""
    for sp in root.iter("{%s}sp" % P_NS):
        ph = sp.find(".//{%s}nvPr/{%s}ph" % (P_NS, P_NS))
        ptype = ph.get("type") if ph is not None else None
        is_title = ptype in ("title", "ctrTitle")
        # txBody lives in the presentationml namespace; paragraphs in drawingml
        for p in sp.findall("{%s}txBody/{%s}p" % (P_NS, A_NS)):
            yield is_title, p


def read_deck(path):
    """Read a .pptx into the JSON model described in the module docstring."""
    zf = zipfile.ZipFile(path)
    pres_root = ET.fromstring(zf.read("ppt/presentation.xml"))
    sld_sz = pres_root.find("{%s}sldSz" % P_NS)
    slide_size = [int(sld_sz.get("cx")), int(sld_sz.get("cy"))] if sld_sz is not None else None

    try:
        pres_rels = _read_rels_bytes(zf.read("ppt/_rels/presentation.xml.rels"))
    except KeyError:
        pres_rels = {}
    sld_id_lst = pres_root.find("{%s}sldIdLst" % P_NS)

    slides = []
    for idx, sld_id in enumerate(list(sld_id_lst)):
        rid = sld_id.get("{%s}id" % R_NS)
        part = _resolve("ppt/presentation.xml", pres_rels[rid]["target"])
        root = ET.fromstring(zf.read(part))

        paras, counter = [], 0
        for is_title, p in _shape_paras(root):
            paras.append({
                "pid": "s{0}p{1}".format(idx, counter),
                "role": "title" if is_title else "body",
                "text": _para_text(p),
                "runs": len(p.findall("{%s}r" % A_NS)),
            })
            counter += 1

        layout_part = None
        notes_part = None
        try:
            slide_rels = _read_rels_bytes(zf.read(_rels_name(part)))
        except KeyError:
            slide_rels = {}
        for rel in slide_rels.values():
            if rel["type"].endswith("/slideLayout"):
                layout_part = _resolve(part, rel["target"])
            elif rel["type"].endswith("/notesSlide"):
                notes_part = _resolve(part, rel["target"])

        if notes_part is not None:
            try:
                notes_root = ET.fromstring(zf.read(notes_part))
            except KeyError:
                notes_root = None
            if notes_root is not None:
                for _t, p in _shape_paras(notes_root):
                    paras.append({
                        "pid": "s{0}p{1}".format(idx, counter),
                        "role": "notes",
                        "text": _para_text(p),
                        "runs": len(p.findall("{%s}r" % A_NS)),
                    })
                    counter += 1

        text_hash = hashlib.sha256(
            "\n".join(p["text"] for p in paras).encode("utf-8")).hexdigest()
        slides.append({
            "index": idx,
            "part": part,
            "layout_part": layout_part,
            "notes_part": notes_part,
            "text_hash": text_hash,
            "paras": paras,
        })

    zf.close()
    return {"slide_size": slide_size, "slides": slides}


# ---------------------------------------------------------------------------
# text surgery
# ---------------------------------------------------------------------------

def _set_para_text(p_elem, text):
    """Full new text into the first run, blank the rest; keep all rPr."""
    runs = p_elem.findall("{%s}r" % A_NS)
    if not runs:
        r = ET.Element("{%s}r" % A_NS)
        rpr = ET.SubElement(r, "{%s}rPr" % A_NS)
        rpr.set("lang", "en-US")
        t = ET.SubElement(r, "{%s}t" % A_NS)
        t.text = text
        t.set(XML_SPACE, "preserve")
        endpr = p_elem.find("{%s}endParaRPr" % A_NS)
        if endpr is not None:
            p_elem.insert(list(p_elem).index(endpr), r)
        else:
            p_elem.append(r)
        return
    for i, r in enumerate(runs):
        t = r.find("{%s}t" % A_NS)
        if t is None:
            t = ET.SubElement(r, "{%s}t" % A_NS)
        t.text = text if i == 0 else ""
        t.set(XML_SPACE, "preserve")


def apply_para_seq(root, texts):
    """Set the i-th shape paragraph's text to texts[i] (positional)."""
    for i, (_is_title, p) in enumerate(_shape_paras(root)):
        if i < len(texts) and _para_text(p) != texts[i]:
            _set_para_text(p, texts[i])


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

SLIDE_CT = ("application/vnd.openxmlformats-officedocument."
            "presentationml.slide+xml")
NOTES_CT = ("application/vnd.openxmlformats-officedocument."
            "presentationml.notesSlide+xml")
SLIDE_REL = ("http://schemas.openxmlformats.org/officeDocument/2006/"
             "relationships/slide")


def _texts(slide, role):
    return [p["text"] for p in slide.get("paras", []) if p["role"] == role]


def _main_texts(slide):
    """Non-notes paragraphs in document order (positional matching)."""
    return [p["text"] for p in slide.get("paras", []) if p["role"] != "notes"]


def write_deck(model, src, out):
    """Write model back to a pptx; touch only slide parts whose text changed.

    Model slides may carry "new": true + "donor_part": <part> to clone a
    donor slide.  Slides absent from the model are fully removed (part,
    rels, notes, content-type override, sldId entry).
    """
    zin = zipfile.ZipFile(src)
    parts = {}
    for name in zin.namelist():
        parts.setdefault(name, zin.read(name))
    zin.close()

    src_model = read_deck(src)
    src_by_part = {s["part"]: s for s in src_model["slides"]}

    model_slides = model["slides"]
    keep_parts = [s["part"] for s in model_slides if not s.get("new")]
    deleted_parts = [p for p in src_by_part if p not in keep_parts]

    # ---- name the new slide parts (donor clone) ---------------------------
    max_num = max([_slide_number(p) for p in src_by_part] + [0])
    max_notes = max([_slide_number(p) for p in parts
                     if p.startswith("ppt/notesSlides/notesSlide")] + [0])
    new_entries = []
    seq = 0
    for s in model_slides:
        if s.get("new"):
            seq += 1
            s["part"] = "ppt/slides/slide%d.xml" % (max_num + seq)
            s["_notes_name"] = "ppt/notesSlides/notesSlide%d.xml" % (max_notes + seq)
            new_entries.append(s)

    # ---- collect parts that must disappear with deleted slides ------------
    drop = set(deleted_parts)
    for part in deleted_parts:
        drop.add(_rels_name(part))
        for rel in _read_rels_bytes(parts.get(_rels_name(part))).values():
            if rel["type"].endswith("/notesSlide"):
                np_ = _resolve(part, rel["target"])
                drop.add(np_)
                drop.add(_rels_name(np_))

    # ---- structural roots --------------------------------------------------
    pres_root = ET.fromstring(parts["ppt/presentation.xml"])
    pres_rels_root = ET.fromstring(parts["ppt/_rels/presentation.xml.rels"])
    ct_root = ET.fromstring(parts["[Content_Types].xml"])

    pres_rels = {rel.get("Id"): rel
                 for rel in pres_rels_root.findall("{%s}Relationship" % REL_NS)}
    sld_id_lst = pres_root.find("{%s}sldIdLst" % P_NS)
    existing = {}
    for sld_id in list(sld_id_lst):
        rid = sld_id.get("{%s}id" % R_NS)
        existing[_resolve("ppt/presentation.xml",
                          pres_rels[rid].get("Target"))] = sld_id
        sld_id_lst.remove(sld_id)

    used_ids = [int(e.get("id")) for e in existing.values()] or [255]
    max_rid = max([int(re.sub(r"\D", "", r) or 0) for r in pres_rels] + [0])

    for s in new_entries:
        max_rid += 1
        rid = "rId%d" % max_rid
        rel = ET.SubElement(pres_rels_root, "{%s}Relationship" % REL_NS)
        rel.set("Id", rid)
        rel.set("Type", SLIDE_REL)
        rel.set("Target", posixpath.relpath(s["part"], "ppt"))
        el = ET.Element("{%s}sldId" % P_NS)
        el.set("id", str(max(used_ids) + 1))
        used_ids.append(max(used_ids) + 1)
        el.set("{%s}id" % R_NS, rid)
        existing[s["part"]] = el

    for s in model_slides:
        sld_id_lst.append(existing[s["part"]])

    def _remove_override(part):
        for ov in ct_root.findall("{%s}Override" % CT_NS):
            if ov.get("PartName") == "/" + part:
                ct_root.remove(ov)

    def _add_override(part, ctype):
        ov = ET.SubElement(ct_root, "{%s}Override" % CT_NS)
        ov.set("PartName", "/" + part)
        ov.set("ContentType", ctype)

    for part in deleted_parts:
        _remove_override(part)
        for rel in _read_rels_bytes(parts.get(_rels_name(part))).values():
            if rel["type"].endswith("/notesSlide"):
                _remove_override(_resolve(part, rel["target"]))

    for rid, rel in list(pres_rels.items()):
        if rel.get("Type", "").endswith("/slide") and \
           _resolve("ppt/presentation.xml", rel.get("Target")) in deleted_parts:
            pres_rels_root.remove(rel)

    # ---- slide part surgery ------------------------------------------------
    changed = {}

    for s in model_slides:
        part = s["part"]
        if s.get("new"):
            donor = s.get("donor_part")
            if donor not in parts:
                raise SystemExit("add_slide: donor part %s not in source" % donor)
            root = ET.fromstring(parts[donor])
            apply_para_seq(root, _main_texts(s))
            changed[part] = _xml_bytes(root)
            _add_override(part, SLIDE_CT)
            donor_notes = src_by_part.get(donor, {}).get("notes_part")
            nn = None
            if donor_notes and donor_notes in parts:
                # clone the donor notes part under a fresh notes number
                notes_root = ET.fromstring(parts[donor_notes])
                apply_para_seq(notes_root, _texts(s, "notes"))
                nn = s["_notes_name"]
                changed[nn] = _xml_bytes(notes_root)
                _add_override(nn, NOTES_CT)
            donor_rels = _rels_name(donor)
            if donor_rels in parts:
                nroot = ET.fromstring(parts[donor_rels])
                for rel in nroot.findall("{%s}Relationship" % REL_NS):
                    if rel.get("Type", "").endswith("/notesSlide") and nn:
                        rel.set("Target", posixpath.relpath(
                            nn, posixpath.dirname(part)))
                changed[_rels_name(part)] = _xml_bytes(nroot, REL_NS)
            if nn:
                donor_notes_rels = _rels_name(donor_notes)
                if donor_notes_rels in parts:
                    nnroot = ET.fromstring(parts[donor_notes_rels])
                    for rel in nnroot.findall("{%s}Relationship" % REL_NS):
                        if rel.get("Type", "").endswith("/slide"):
                            rel.set("Target", posixpath.relpath(
                                part, posixpath.dirname(nn)))
                    changed[_rels_name(nn)] = _xml_bytes(nnroot, REL_NS)
        else:
            src_slide = src_by_part.get(part)
            if src_slide is None:
                raise SystemExit("write: part %s not present in source" % part)
            want = _main_texts(s)
            have = _main_texts(src_slide)
            if want != have:
                root = ET.fromstring(parts[part])
                apply_para_seq(root, want)
                changed[part] = _xml_bytes(root)
            np_ = src_slide.get("notes_part")
            if np_:
                want_n = _texts(s, "notes")
                have_n = _texts(src_slide, "notes")
                if want_n != have_n and want_n:
                    notes_root = ET.fromstring(parts[np_])
                    apply_para_seq(notes_root, want_n)
                    changed[np_] = _xml_bytes(notes_root)

    parts["ppt/presentation.xml"] = _xml_bytes(pres_root)
    parts["ppt/_rels/presentation.xml.rels"] = _xml_bytes(pres_rels_root, REL_NS)
    parts["[Content_Types].xml"] = _xml_bytes(ct_root, CT_NS)
    parts.update(changed)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            if name in drop:
                continue
            zout.writestr(name, data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="pptx <-> JSON model via XML surgery")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("read")
    r.add_argument("--deck", required=True)
    r.add_argument("--out", required=True)

    w = sub.add_parser("write")
    w.add_argument("--model", required=True)
    w.add_argument("--src", required=True)
    w.add_argument("--out", required=True)

    args = ap.parse_args(argv)
    if args.cmd == "read":
        model = read_deck(args.deck)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(model, f, ensure_ascii=False, indent=1)
        print("read %s: %d slides, %d paras" % (
            args.deck, len(model["slides"]),
            sum(len(s["paras"]) for s in model["slides"])))
    else:
        with open(args.model, encoding="utf-8") as f:
            model = json.load(f)
        write_deck(model, args.src, args.out)
        print("wrote %s (%d slides)" % (args.out, len(model["slides"])))


if __name__ == "__main__":
    main()
