#!/usr/bin/env python3
"""detect_nondata_ink.py — find ink that is NOT data inside the plot area.

Geometry heuristics on the raster figure (within the plot-area bbox(es) given in
the agent-written figure card):
  * NONDATA_STAR     small high-contrast blobs with ~radial ink distribution
                     (significance stars / stray markers), boosted when floating
                     above a bar from the card's element_inventory
  * NONDATA_BRACKET  long thin horizontal runs with vertical end caps above bars
  * FIT_LINE         long straight thin diagonal lines crossing the plot
                     (RANSAC on ink pixels)
  * INSET_AXIS       small rectangular frames inside the plot area
  * LEGEND_SWAP risk if a card-provided legend_bbox overlaps the plot area

Every candidate is emitted with action="exclude_from_data" AND mirrored into
"agent_confirm": the agent MUST verify each one on the zoomed image. Heuristics
are not proof — a quiet run does not mean the figure is free of non-data ink.

Writes <out> (default <work>/nondata_elements.json).
Exit codes: 0 = no candidates; 2 = >=1 candidate; 1 = error.
Stdlib + numpy + PIL only. Pixel coords: origin top-left, y down.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image

INK_THRESHOLD = 160      # mean channel value below which a pixel may count as ink
INK_NEUTRAL = 45         # max channel spread for "neutral" (black/gray) ink
BORDER_SHAVE = 3         # ignore ink this close to the plot bbox edge (spines)


# ------------------------------------------------------------- components ----
def connected_components(mask):
    """Two-pass union-find labeling of a boolean mask. Returns list of dicts
    {pixels (N,2 int array of (row,col)), bbox [x0,y0,x1,y1], area}."""
    rows, cols = np.nonzero(mask)
    n = len(rows)
    if n == 0:
        return []
    parent = {}

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    labels = {}
    label_of = {}
    next_label = 0
    rset = set(zip(rows.tolist(), cols.tolist()))
    for r, c in zip(rows.tolist(), cols.tolist()):
        neigh = [p for p in ((r, c - 1), (r - 1, c - 1), (r - 1, c), (r - 1, c + 1))
                 if p in label_of]
        if not neigh:
            label_of[(r, c)] = next_label
            parent[next_label] = next_label
            next_label += 1
        else:
            lab = label_of[neigh[0]]
            label_of[(r, c)] = lab
            for p in neigh[1:]:
                union(lab, label_of[p])
    groups = {}
    for px, lab in label_of.items():
        groups.setdefault(find(lab), []).append(px)
    comps = []
    for px_list in groups.values():
        arr = np.asarray(px_list, dtype=np.int32)  # (row, col)
        r0, c0 = arr.min(axis=0)
        r1, c1 = arr.max(axis=0)
        comps.append({"pixels": arr,
                      "bbox": [int(c0), int(r0), int(c1) + 1, int(r1) + 1],
                      "area": int(len(arr))})
    return comps


# ------------------------------------------------------------- classifiers ---
def radial_cv(comp):
    """Coefficient of variation of max ink radius across 8 angular octants;
    low cv + all octants populated ~ star/marker shaped."""
    px = comp["pixels"].astype(float)
    cy, cx = px.mean(axis=0)
    dy, dx = px[:, 0] - cy, px[:, 1] - cx
    ang = np.arctan2(dy, dx)
    rad = np.hypot(dy, dx)
    oct_max = []
    for k in range(8):
        m = (ang >= -math.pi + k * math.pi / 4) & (ang < -math.pi + (k + 1) * math.pi / 4)
        oct_max.append(float(rad[m].max()) if m.any() else 0.0)
    populated = sum(1 for v in oct_max if v > 0)
    arr = np.asarray([v for v in oct_max if v > 0], float)
    cv = float(arr.std() / arr.mean()) if len(arr) and arr.mean() > 0 else 9.9
    return cv, populated


def above_bar(comp, bars):
    """Is the component floating above (smaller y than) a bar's top, x-overlapping?"""
    x0, y0, x1, y1 = comp["bbox"]
    cx = 0.5 * (x0 + x1)
    for b in bars:
        bb = b.get("bbox")
        if not bb or len(bb) != 4:
            continue
        if bb[0] - 6 <= cx <= bb[2] + 6 and y1 <= bb[1] + 4:
            return True
    return False


def classify_star(comp, bars, panel_wh):
    w = comp["bbox"][2] - comp["bbox"][0]
    h = comp["bbox"][3] - comp["bbox"][1]
    if not (4 <= w <= 42 and 4 <= h <= 42):
        return None
    if not (0.5 <= w / max(h, 1) <= 2.0):
        return None
    if comp["area"] < 8:
        return None
    cv, populated = radial_cv(comp)
    if cv < 0.40 and populated >= 7:
        conf = 0.55
        reasons = ["small isolated blob with radial ink distribution "
                   "(octant cv=%.2f, %d/8 octants)" % (cv, populated)]
        if above_bar(comp, bars):
            conf += 0.25
            reasons.append("floats above a bar from element_inventory")
        return {"type": "NONDATA_STAR", "bbox": comp["bbox"],
                "confidence": round(min(conf, 0.95), 2),
                "evidence": "; ".join(reasons)}
    return None


def classify_bracket(comp, bars, panel_wh):
    """Significance bracket: one dominant long horizontal ink row with vertical
    end caps at BOTH run ends. Height/aspect are deliberately unconstrained —
    brackets often merge with the error-bar ink they hover above. The end-cap
    requirement is what separates brackets from legend line samples and plain
    error-bar caps (those have their vertical in the MIDDLE, not at the ends)."""
    x0, y0, x1, y1 = comp["bbox"]
    w, h = x1 - x0, y1 - y0
    if w < 30 or w > 0.95 * panel_wh[0]:
        return None  # too short, or spans the whole panel -> spine/gridline
    px = comp["pixels"]
    rows = px[:, 0] - y0
    cols = px[:, 1] - x0
    counts = np.bincount(rows, minlength=h)
    bar_row = int(np.argmax(counts))
    if counts[bar_row] < 30 or counts[bar_row] < 0.6 * w:
        return None  # no dominant horizontal run
    run_cols = cols[rows == bar_row]
    c_lo, c_hi = int(run_cols.min()), int(run_cols.max())
    caps = 0
    for c in (c_lo, c_hi):
        col_rows = rows[np.abs(cols - c) <= 1]
        if len(col_rows) >= 3 and col_rows.max() - col_rows.min() >= 3:
            caps += 1
    if caps < 2:
        return None
    conf = 0.6
    reasons = ["horizontal run %dpx with vertical end caps at both ends"
               % counts[bar_row]]
    if above_bar(comp, bars):
        conf += 0.25
        reasons.append("floats above bar(s) from element_inventory")
    return {"type": "NONDATA_BRACKET", "bbox": comp["bbox"],
            "confidence": round(min(conf, 0.95), 2),
            "evidence": "; ".join(reasons)}


def classify_inset(comp, panel_wh):
    x0, y0, x1, y1 = comp["bbox"]
    w, h = x1 - x0, y1 - y0
    pw, ph = panel_wh
    if not (0.15 * pw <= w <= 0.65 * pw and 0.15 * ph <= h <= 0.65 * ph):
        return None
    px = comp["pixels"]
    on_border = ((px[:, 1] - x0 <= 2) | (x1 - 1 - px[:, 1] <= 2)
                 | (px[:, 0] - y0 <= 2) | (y1 - 1 - px[:, 0] <= 2)).mean()
    fill = comp["area"] / float(w * h)
    if on_border > 0.8 and fill < 0.30:
        return {"type": "INSET_AXIS", "bbox": comp["bbox"], "confidence": 0.5,
                "evidence": ("rectangular frame %dx%d inside plot area "
                             "(border ink %.2f, fill %.2f)"
                             % (w, h, on_border, fill))}
    return None


def ransac_fit_line(ink_pts, panel_wh):
    """Hough-lite: RANSAC a long straight DIAGONAL line through ink pixels."""
    if len(ink_pts) < 60:
        return None
    pts = ink_pts.astype(float)
    if len(pts) > 4000:
        idx = np.random.default_rng(0).choice(len(pts), 4000, replace=False)
        pts = pts[idx]
    pw, ph = panel_wh
    min_extent = 0.45 * max(pw, ph)
    best = None
    rng = np.random.default_rng(1)
    for _ in range(300):
        i, j = rng.choice(len(pts), 2, replace=False)
        p, q = pts[i], pts[j]
        d = q - p
        L = math.hypot(d[0], d[1])
        if L < min_extent:
            continue
        slope = abs(d[0] / d[1]) if d[1] else 1e9  # dy/dx (row/col)
        if slope < 0.05 or slope > 20:             # skip axis-aligned ink
            continue
        dist = np.abs((pts - p) @ np.array([-d[1], d[0]])) / L
        inl = dist <= 2.0
        n_inl = int(inl.sum())
        if n_inl < 80:
            continue
        t = (pts[inl] - p) @ d / (L * L)
        extent = float(t.max() - t.min()) * L
        if extent < min_extent:
            continue
        # a real drawn line is ~continuous: roughly >=1 ink px per px of length;
        # scattered ink that merely aligns diagonally stays far below this.
        if n_inl < 0.35 * extent:
            continue
        if best is None or n_inl > best[0]:
            best = (n_inl, p.tolist(), d.tolist(), extent)
    if best is None:
        return None
    n_inl, p, d, extent = best
    t = (pts - np.asarray(p)) @ np.asarray(d) / (d[0] ** 2 + d[1] ** 2)
    return {"type": "FIT_LINE", "confidence": 0.5,
            "bbox": None,
            "evidence": ("RANSAC line: %d inliers, extent %.0fpx (%.0f%% of panel "
                         "max dim) — candidate fit/trend line, NOT data"
                         % (n_inl, extent, 100 * extent / max(pw, ph))),
            "line": {"point": p, "direction": d}}


# ------------------------------------------------------------------ driver ---
def bars_from_card(card, panel):
    bars = []
    for el in card.get("element_inventory") or []:
        if el.get("type") == "bar" and el.get("bbox") \
                and el.get("panel") in (None, panel):
            bars.append(el)
    return bars


def ink_mask(rgb):
    """Neutral dark ink (black/gray annotations, text, error bars, brackets).
    Saturated colored data ink (blue/orange bars & lines) is deliberately NOT
    matched: annotation ink is what this detector hunts."""
    rgb = rgb.astype(np.int16)
    spread = rgb.max(axis=2) - rgb.min(axis=2)
    mean = rgb.mean(axis=2)
    return (spread < INK_NEUTRAL) & (mean < INK_THRESHOLD)


def process_panel(rgb, name, bbox, card):
    x0, y0, x1, y1 = [int(round(v)) for v in bbox]
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, rgb.shape[1]), min(y1, rgb.shape[0])
    mask = ink_mask(rgb[y0:y1, x0:x1])
    if BORDER_SHAVE:
        mask[:BORDER_SHAVE, :] = False
        mask[-BORDER_SHAVE:, :] = False
        mask[:, :BORDER_SHAVE] = False
        mask[:, -BORDER_SHAVE:] = False
    panel_wh = (x1 - x0, y1 - y0)
    bars = bars_from_card(card, name)
    comps = connected_components(mask)
    cands = []
    claimed = set()
    for comp in comps:
        hit = classify_star(comp, bars, panel_wh)
        if hit is None:
            hit = classify_bracket(comp, bars, panel_wh)
        if hit is None:
            hit = classify_inset(comp, panel_wh)
        if hit:
            hit["bbox"] = [hit["bbox"][0] + x0, hit["bbox"][1] + y0,
                           hit["bbox"][2] + x0, hit["bbox"][3] + y0]
            hit["panel"] = name
            hit["action"] = "exclude_from_data"
            cands.append(hit)
            claimed.add(tuple(comp["bbox"]))
    rest = [c for c in comps if tuple(c["bbox"]) not in claimed]
    if rest:
        ink = np.concatenate([c["pixels"] for c in rest], axis=0)
        fl = ransac_fit_line(ink, panel_wh)
        if fl:
            fl["panel"] = name
            fl["action"] = "exclude_from_data"
            cands.append(fl)
    return cands


def legend_overlap_check(card, bboxes):
    lb = card.get("legend_bbox")
    if not lb or len(lb) != 4:
        return None
    for name, bb in (bboxes.items() if isinstance(bboxes, dict) else
                     [("main", bboxes)]):
        ix0 = max(lb[0], bb[0]); iy0 = max(lb[1], bb[1])
        ix1 = min(lb[2], bb[2]); iy1 = min(lb[3], bb[3])
        if ix1 > ix0 and iy1 > iy0:
            return {"type": "LEGEND_SWAP", "panel": name, "bbox": lb,
                    "confidence": 0.4, "action": "exclude_from_data",
                    "evidence": ("card legend_bbox overlaps the plot area of panel "
                                 "'%s' — legend markers/line samples sit inside the "
                                 "data region and can be digitized as points"
                                 % name)}
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True)
    ap.add_argument("--card", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    try:
        with open(args.card, encoding="utf-8") as fh:
            card = json.load(fh)
        rgb = np.asarray(Image.open(args.image).convert("RGB"), dtype=np.uint8)
    except Exception as exc:  # noqa: BLE001
        print("error: %s" % exc, file=sys.stderr)
        return 1

    bbox = card.get("plot_area_bbox")
    if isinstance(bbox, dict):
        panels = bbox
    elif isinstance(bbox, list) and len(bbox) == 4:
        panels = {"main": bbox}
    else:
        print("error: card has no usable plot_area_bbox", file=sys.stderr)
        return 1

    candidates = []
    for name, bb in panels.items():
        candidates.extend(process_panel(rgb, name, bb, card))
    lo = legend_overlap_check(card, bbox)
    if lo:
        candidates.append(lo)

    confirm = ["VISUALLY CONFIRM candidate #%d (%s, panel %s, bbox %s) on the "
               "zoomed figure before excluding it" % (i + 1, c["type"],
                                                      c.get("panel"), c.get("bbox"))
               for i, c in enumerate(candidates)]
    confirm.append("Confirm no data series marker was classified as NONDATA_STAR — "
                   "lone markers unconnected to a line look identical to stars")
    confirm.append("Confirm the legend's location; if it overlaps the plot area, "
                   "its markers/line samples must be excluded from digitization")

    out_doc = {
        "tool": "detect_nondata_ink",
        "image": os.path.abspath(args.image),
        "candidates": candidates,
        "n_candidates": len(candidates),
        "agent_confirm": confirm,
        "caveat": ("Geometry heuristics only. A candidate is a suspicion until you "
                   "confirm it on the zoomed image; a quiet run does not prove the "
                   "plot is free of non-data ink."),
    }
    out = args.out or os.path.join(args.work, "nondata_elements.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(out_doc, fh, indent=2, ensure_ascii=False)
    print("wrote %s — %d candidate(s): %s"
          % (out, len(candidates),
             ", ".join(sorted({c['type'] for c in candidates})) or "none"))
    return 2 if candidates else 0


if __name__ == "__main__":
    sys.exit(main())
