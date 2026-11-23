#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
svg_conventions.py — shared conventions + parsing helpers for the
figure-audit-loop skill.

Every producer (mini_svg_builder, the agent's own hand-written SVG, etc.)
and every auditor in this bundle agree on the following machine-readable
conventions (documented in references/svg-conventions.md):

  * Layer groups:      <g id="layer-compartments">, <g id="layer-entities">,
                       <g id="layer-edges">, <g id="layer-legend">
  * Entity group:      <g id="entity:<id>" class="entity"
                          data-entity-type="protein" data-compartment="cytosol"
                          data-source="Fig.2A">
                          containing a rect/ellipse (class "entity-box") and a
                          <text class="entity-label">LABEL</text>
  * Edge group:        <g id="edge:<id>" class="edge"
                          data-edge-kind="activates" data-from="A" data-to="B"
                          data-evidence="confirmed" data-source="Fig.2A">
                          containing a <line>/<path class="edge-line"
                          marker-end="url(#marker-...)"/> and optionally a
                          <text class="edge-badge">P</text>
  * Legend:            <g id="legend"> with items
                       <g id="legend-swatch:<item>" class="legend-item">
                          <rect class="swatch" fill="#..."/>
                          <text class="legend-label">meaning</text></g>
  * Compartments:      <rect id="compartment:<name>" class="compartment-band">

Auditors read the data-* attributes FIRST (authoritative) and fall back to
marker/style heuristics only when attributes are absent (and then record a
warning instead of guessing silently).

This module is pure stdlib so every script in the bundle can import it.
"""

import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"

ENTITY_PREFIX = "entity:"
EDGE_PREFIX = "edge:"
SWATCH_PREFIX = "legend-swatch:"
COMPARTMENT_PREFIX = "compartment:"
LEGEND_ID = "legend"

LAYER_IDS = [
    "layer-compartments",
    "layer-entities",
    "layer-edges",
    "layer-legend",
]

EDGE_KINDS = [
    "activates", "inhibits", "binds", "phosphorylates",
    "ubiquitinates", "transports", "recruits", "modifies",
]

# kind -> marker id used in <defs> (binds has no arrowhead by convention)
EDGE_MARKERS = {
    "activates": "marker-activates",
    "inhibits": "marker-inhibits",
    "binds": None,
    "phosphorylates": "marker-arrow",
    "ubiquitinates": "marker-arrow",
    "transports": "marker-arrow",
    "recruits": "marker-arrow",
    "modifies": "marker-arrow",
}

# kind -> small badge text drawn near the edge midpoint ("" = none)
EDGE_BADGES = {
    "phosphorylates": "P",
    "ubiquitinates": "Ub",
}

EVIDENCE_VALUES = ["confirmed", "uncertain"]
UNCERTAIN_DASH = "6,4"  # stroke-dasharray marking uncertain evidence

# font families auditors accept as portable/generic
GENERIC_FONT_FAMILIES = {
    "sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui",
    "arial", "helvetica", "dejavu sans", "dejavu serif", "dejavu sans mono",
    "liberation sans", "liberation serif", "times new roman", "times",
    "courier", "courier new", "noto sans", "noto serif",
}


# --------------------------------------------------------------------------
# generic XML helpers (namespace tolerant)
# --------------------------------------------------------------------------

def register_ns():
    """Make ElementTree write clean default-namespace SVG."""
    ET.register_namespace("", SVG_NS)


def localname(tag):
    """'{ns}g' -> 'g'; 'g' -> 'g'."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def parse_svg(path):
    """Parse an SVG file; raises ET.ParseError if malformed."""
    register_ns()
    return ET.parse(path)


def iter_elements(root, tagname=None):
    for el in root.iter():
        if tagname is None or localname(el.tag) == tagname:
            yield el


def find_by_id(root, elid):
    for el in root.iter():
        if el.get("id") == elid:
            return el
    return None


def find_child_by_class(el, classname, tagname=None):
    for ch in el.iter():
        if el is ch:
            continue
        if tagname and localname(ch.tag) != tagname:
            continue
        if classname in (ch.get("class") or "").split():
            return ch
    return None


def all_texts(root):
    """All visible <text> strings in document order (stripped, non-empty)."""
    out = []
    for t in iter_elements(root, "text"):
        s = "".join(t.itertext()).strip()
        if s:
            out.append(s)
    return out


# --------------------------------------------------------------------------
# record extractors (the figure graph)
# --------------------------------------------------------------------------

def _first_text_of_class(group, classname):
    t = find_child_by_class(group, classname, "text")
    if t is not None:
        return "".join(t.itertext()).strip()
    return None


def _box_fill(group):
    for cls in ("entity-box", "swatch"):
        box = find_child_by_class(group, cls)
        if box is not None and box.get("fill"):
            return box.get("fill")
    for tag in ("rect", "ellipse", "circle"):
        for ch in group.iter():
            if localname(ch.tag) == tag and ch.get("fill"):
                return ch.get("fill")
    return None


def entity_records(root):
    """List of {id, label, type, compartment, source, fill}."""
    recs = []
    for g in iter_elements(root, "g"):
        gid = g.get("id") or ""
        if not gid.startswith(ENTITY_PREFIX):
            continue
        recs.append({
            "id": gid[len(ENTITY_PREFIX):],
            "label": _first_text_of_class(g, "entity-label"),
            "type": g.get("data-entity-type"),
            "compartment": g.get("data-compartment"),
            "source": g.get("data-source"),
            "fill": _box_fill(g),
        })
    return recs


def _marker_kind(line_el):
    m = line_el.get("marker-end") or ""
    m = re.search(r"#([A-Za-z0-9_-]+)", m)
    if not m:
        return "binds"  # convention: no arrowhead => binding/association
    name = m.group(1)
    if "inhibits" in name:
        return "inhibits"
    if "activates" in name:
        return "activates"
    return None  # generic arrow; kind must come from data-edge-kind


def edge_records(root):
    """List of {id, kind, from, to, evidence, source, badge,
    kind_inferred, evidence_inferred}."""
    recs = []
    for g in iter_elements(root, "g"):
        gid = g.get("id") or ""
        if not gid.startswith(EDGE_PREFIX):
            continue
        line = find_child_by_class(g, "edge-line")
        if line is None:
            for tag in ("line", "path", "polyline"):
                line = next((c for c in g.iter()
                             if localname(c.tag) == tag and c is not g), None)
                if line is not None:
                    break
        kind = g.get("data-edge-kind")
        kind_inferred = False
        if not kind and line is not None:
            kind = _marker_kind(line) or "activates"
            kind_inferred = True
        evidence = g.get("data-evidence")
        evidence_inferred = False
        if not evidence:
            dash = (line.get("stroke-dasharray") if line is not None else None)
            evidence = "uncertain" if dash else "confirmed"
            evidence_inferred = True
        frm, to = g.get("data-from"), g.get("data-to")
        recs.append({
            "id": gid[len(EDGE_PREFIX):],
            "kind": kind,
            "from": frm,
            "to": to,
            "evidence": evidence,
            "source": g.get("data-source"),
            "badge": _first_text_of_class(g, "edge-badge"),
            "kind_inferred": kind_inferred,
            "evidence_inferred": evidence_inferred,
            "endpoints_machine_readable": bool(frm and to),
        })
    return recs


def legend_records(root):
    """List of {item, meaning, color}."""
    recs = []
    leg = find_by_id(root, LEGEND_ID)
    if leg is None:
        # tolerate layer-legend wrapper
        leg = find_by_id(root, "layer-legend")
    if leg is None:
        return recs
    for g in leg.iter():
        gid = g.get("id") or ""
        if not gid.startswith(SWATCH_PREFIX):
            continue
        recs.append({
            "item": gid[len(SWATCH_PREFIX):],
            "meaning": _first_text_of_class(g, "legend-label"),
            "color": _box_fill(g),
        })
    return recs


def compartment_records(root):
    recs = []
    for el in root.iter():
        cid = el.get("id") or ""
        if cid.startswith(COMPARTMENT_PREFIX):
            recs.append({"id": cid[len(COMPARTMENT_PREFIX):]})
    return recs


# --------------------------------------------------------------------------
# geometry helpers (pixel auditor + fix loop)
# --------------------------------------------------------------------------

def element_bbox(root, elid):
    """Return (x, y, w, h) in SVG user units for an element id, or None.

    Works for rect, circle, ellipse, or a <g> containing one of those
    (e.g. entity:<id> / legend-swatch:<item> groups)."""
    el = find_by_id(root, elid)
    if el is None:
        return None
    cands = [el] + list(el.iter())
    for c in cands:
        tag = localname(c.tag)
        try:
            if tag == "rect":
                return (float(c.get("x", 0)), float(c.get("y", 0)),
                        float(c.get("width", 0)), float(c.get("height", 0)))
            if tag == "circle":
                cx, cy, r = (float(c.get(k, 0)) for k in ("cx", "cy", "r"))
                return (cx - r, cy - r, 2 * r, 2 * r)
            if tag == "ellipse":
                cx, cy = float(c.get("cx", 0)), float(c.get("cy", 0))
                rx, ry = float(c.get("rx", 0)), float(c.get("ry", 0))
                return (cx - rx, cy - ry, 2 * rx, 2 * ry)
        except (TypeError, ValueError):
            continue
    return None


def svg_canvas_size(root):
    """(width, height) from root attributes, floats."""
    w = root.get("width") or "0"
    h = root.get("height") or "0"
    w = float(re.sub(r"[a-zA-Z%]+$", "", w) or 0)
    h = float(re.sub(r"[a-zA-Z%]+$", "", h) or 0)
    return w, h


def hex_to_rgb(s):
    """'#rrggbb' or '#rgb' -> (r, g, b) ints; None if unparsable."""
    if not s:
        return None
    s = s.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def lerp_color(hex_a, hex_b, t):
    """Linear RGB interpolation, t in [0,1]."""
    a, b = hex_to_rgb(hex_a), hex_to_rgb(hex_b)
    if a is None or b is None:
        return hex_a
    t = max(0.0, min(1.0, t))
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def swap_line_endpoints(line_el):
    """Swap the two ends of a <line> in place (used by fix ops)."""
    for a, b in (("x1", "x2"), ("y1", "y2")):
        va, vb = line_el.get(a), line_el.get(b)
        if va is not None and vb is not None:
            line_el.set(a, vb)
            line_el.set(b, va)


def serialize_element(el):
    """Canonical 'own' signature for edit-diff comparison (attrs sorted).

    Descendants that carry their own id are replaced by a stub, so a change
    inside an id-bearing child is reported once (on that child) instead of
    propagating up to every id-bearing ancestor (e.g. layer groups)."""
    def rec(node):
        parts = [localname(node.tag)]
        for k in sorted(node.attrib):
            parts.append("%s=%s" % (k, node.attrib[k]))
        text = (node.text or "").strip()
        if text:
            parts.append("text:" + text)
        kids = []
        for c in list(node):
            if c.get("id"):
                kids.append("<stub id=%s>" % c.get("id"))
            else:
                kids.append(rec(c))
        if kids:
            parts.append("[" + "|".join(kids) + "]")
        return "<" + " ".join(parts) + ">"
    return rec(el)
