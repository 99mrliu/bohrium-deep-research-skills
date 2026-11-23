#!/usr/bin/env python3
"""layerize_svg.py - normalize an arbitrary external SVG into semantic layers.

PURE STDLIB.  Never rasterizes.  Never crashes on malformed input: on parse
failure it still writes layer_map.json with status "failed" and a reason.

Two strategies:
  * preserve - the SVG already carries semantic ids (layer/*, series/*,
    annotation/*, axes, legend, xtick_N, ...): keep structure, only assign
    el-NNN ids to id-less graphical elements.
  * restructure - wrap top-level graphical elements in new groups
    layer/axes, layer/labels, layer/legend, layer/artwork-N using id/class
    hints first, geometry heuristics second (long thin paths -> axes;
    <text> clusters -> labels; <image> -> raster; rest -> artwork).

Also ensures width/height/viewBox exist.  Sets editable:false when the figure
contains no <text> (all outlined) or only raster <image> content, with notes
explaining the consequence (value ops will be unbound; relabel impossible on
outlined text).

Usage:
  python3 layerize_svg.py EXISTING.svg --out-svg /app/work/figure.svg \
      --layer-map /app/work/layer_map.json
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
for pfx, uri in [("", SVG_NS), ("xlink", XLINK_NS),
                 ("dc", "http://purl.org/dc/elements/1.1/"),
                 ("cc", "http://creativecommons.org/ns#"),
                 ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
                 ("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd"),
                 ("inkscape", "http://www.inkscape.org/namespaces/inkscape")]:
    try:
        ET.register_namespace(pfx, uri)
    except ValueError:
        pass

GRAPHICAL = {"path", "rect", "circle", "ellipse", "line", "polyline",
             "polygon", "text", "image", "use", "g"}
SKIP = {"defs", "metadata", "title", "desc", "sodipodi:namedview",
        "namedview", "style"}
NUM = r"-?\d+\.?\d*(?:[eE][-+]?\d+)?"


def local(tag):
    return tag.split("}")[-1].split(":")[-1]


def floats(s):
    return [float(t) for t in re.findall(NUM, s or "")]


def bbox_of(el):
    """Rough bbox from geometry attributes; None if not determinable."""
    tag = local(el.tag)
    xs, ys = [], []
    if tag == "path":
        nums = floats(el.get("d"))
        xs, ys = nums[0::2], nums[1::2]
    elif tag in ("polyline", "polygon"):
        nums = floats(el.get("points"))
        xs, ys = nums[0::2], nums[1::2]
    elif tag in ("rect", "image", "use", "text"):
        if el.get("x") is not None:
            xs = [float(el.get("x")), float(el.get("x")) + float(el.get("width", 0) or 0)]
            ys = [float(el.get("y")), float(el.get("y")) + float(el.get("height", 0) or 0)]
    elif tag == "line":
        xs = [float(el.get("x1", 0)), float(el.get("x2", 0))]
        ys = [float(el.get("y1", 0)), float(el.get("y2", 0))]
    elif tag in ("circle", "ellipse"):
        cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
        r = float(el.get("r", el.get("rx", 0)))
        ry = float(el.get("ry", r))
        xs, ys = [cx - r, cx + r], [cy - ry, cy + ry]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def hint_layer(el):
    ident = ((el.get("id") or "") + " " + (el.get("class") or "")).lower()
    if re.search(r"legend", ident):
        return "layer/legend"
    if re.search(r"axis|axes|xtick|ytick|grid|tick", ident):
        return "layer/axes"
    if re.search(r"label|title|caption|text", ident):
        return "layer/labels"
    return None


def classify(el):
    """Return (layer_id, basis) for one top-level element."""
    tag = local(el.tag)
    hint = hint_layer(el)
    if hint:
        return hint, "id/class hint"
    if tag == "text":
        return "layer/labels", "text element"
    if tag == "image":
        return "layer/raster", "raster image"
    if tag == "g":
        # inspect descendants: any text -> labels-ish mixed group; keep as its
        # own artwork layer unless a descendant hint fires
        for sub in el.iter():
            h = hint_layer(sub)
            if h:
                return h, "descendant id/class hint"
        return "layer/artwork", "group without hints"
    bb = bbox_of(el)
    if bb:
        x0, y0, x1, y1 = bb
        w, h = abs(x1 - x0), abs(y1 - y0)
        long_side, short_side = max(w, h), min(w, h)
        if long_side > 40 and (short_side < 2.5 or
                               (short_side > 0 and long_side / short_side > 12)):
            return "layer/axes", "long thin geometry (axis-like)"
    return "layer/artwork", "geometry fallback"


def has_semantic_ids(root):
    for el in root.iter():
        eid = el.get("id") or ""
        if eid in ("axes", "legend", "figure") or re.match(
                r"^(layer|series|annotation|node|edge)/", eid):
            return True
    return False


def assign_missing_ids(root):
    n = 0
    for el in root.iter():
        if local(el.tag) in GRAPHICAL and not el.get("id"):
            n += 1
            el.set("id", "el-%03d" % n)
    return n


def count_text(root):
    return sum(1 for el in root.iter() if local(el.tag) == "text")


def count_images(root):
    return sum(1 for el in root.iter() if local(el.tag) == "image")


def ensure_canvas(root, notes):
    if not root.get("viewBox"):
        w = re.sub(r"[^\d.]", "", root.get("width") or "") or "600"
        h = re.sub(r"[^\d.]", "", root.get("height") or "") or "400"
        root.set("viewBox", "0 0 %s %s" % (w, h))
        notes.append("viewBox was missing; synthesized from width/height")
    if not root.get("width"):
        vb = root.get("viewBox").split()
        root.set("width", vb[2])
        root.set("height", vb[3])
        notes.append("width/height missing; copied from viewBox")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("svg")
    ap.add_argument("--out-svg", required=True)
    ap.add_argument("--layer-map", required=True)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out_svg)), exist_ok=True)
    layer_map = {"source": args.svg, "out_svg": args.out_svg,
                 "status": "failed", "strategy": None, "layers": [],
                 "element_count": 0, "text_elements": 0,
                 "editable": False, "notes": []}
    try:
        tree = ET.parse(args.svg)
    except (ET.ParseError, OSError) as exc:
        layer_map["notes"].append("cannot parse SVG: %s" % exc)
        layer_map["notes"].append(
            "consequence: figure cannot be layerized; treat as raster-only "
            "input and report the limitation honestly")
        with open(args.layer_map, "w", encoding="utf-8") as fh:
            json.dump(layer_map, fh, ensure_ascii=False, indent=2)
        print("FAILED: %s (layer_map written)" % exc, file=sys.stderr)
        return

    root = tree.getroot()
    if local(root.tag) != "svg":
        layer_map["notes"].append("root element is <%s>, not <svg>" % local(root.tag))
        with open(args.layer_map, "w", encoding="utf-8") as fh:
            json.dump(layer_map, fh, ensure_ascii=False, indent=2)
        print("FAILED: root is not <svg>", file=sys.stderr)
        return

    notes = layer_map["notes"]
    ensure_canvas(root, notes)
    n_assigned = assign_missing_ids(root)
    if n_assigned:
        notes.append("assigned stable ids el-001..el-%03d to id-less elements"
                     % n_assigned)

    if has_semantic_ids(root):
        layer_map["strategy"] = "preserve"
        notes.append("existing semantic ids found; structure preserved")
        layers = {}
        for el in root.iter():
            eid = el.get("id") or ""
            m = re.match(r"^(layer|series|annotation|node|edge)/", eid)
            key = (m.group(0).rstrip("/").split("/")[0]
                   if m else ("axes" if eid in ("axes", "axes_1") or
                              re.match(r"^[xy]tick_\d+$", eid)
                              else ("legend" if eid == "legend" else None)))
            if key:
                layers.setdefault("layer/" + key if not key.startswith("layer")
                                  else key, 0)
                layers["layer/" + key if not key.startswith("layer")
                       else key] += 1
        layer_map["layers"] = [{"id": k, "element_count": v,
                                "basis": "pre-existing semantic ids"}
                               for k, v in sorted(layers.items())]
    else:
        layer_map["strategy"] = "restructure"
        buckets = {}
        order = []
        for child in list(root):
            if local(child.tag) in SKIP:
                continue
            layer_id, basis = classify(child)
            if layer_id == "layer/artwork":
                layer_id = "layer/artwork-%d" % (
                    sum(1 for k in buckets if k.startswith("layer/artwork")) + 1)
            if layer_id not in buckets:
                g = ET.Element("{%s}g" % SVG_NS, {"id": layer_id})
                buckets[layer_id] = (g, [])
                order.append(layer_id)
            buckets[layer_id][1].append((child, basis))
        for layer_id in order:
            g, items = buckets[layer_id]
            for child, _basis in items:
                root.remove(child)
                g.append(child)
            root.append(g)
            layer_map["layers"].append(
                {"id": layer_id, "element_count": len(items),
                 "basis": "; ".join(sorted({b for _, b in items}))})

    n_text = count_text(root)
    n_img = count_images(root)
    n_el = sum(1 for el in root.iter() if local(el.tag) in GRAPHICAL)
    layer_map["element_count"] = n_el
    layer_map["text_elements"] = n_text
    if n_text == 0:
        layer_map["editable"] = False
        notes.append("no <text> elements: all labels are outlined paths - "
                     "relabel ops are impossible without re-typing text")
    elif n_img > 0 and n_el == n_img:
        layer_map["editable"] = False
        notes.append("figure contains only raster <image> content - "
                     "no vector geometry to edit; value ops will be unbound")
    else:
        layer_map["editable"] = True
    notes.append("no figmap data binding exists for an external figure: "
                 "value-changing ops will be marked 'unbound - manual "
                 "confirmation required' until a figmap is supplied")
    layer_map["status"] = "ok"
    tree.write(args.out_svg, encoding="utf-8", xml_declaration=True)
    with open(args.layer_map, "w", encoding="utf-8") as fh:
        json.dump(layer_map, fh, ensure_ascii=False, indent=2)
    print("layerize: strategy=%s layers=%d elements=%d text=%d editable=%s"
          % (layer_map["strategy"], len(layer_map["layers"]), n_el, n_text,
             layer_map["editable"]))


if __name__ == "__main__":
    main()
