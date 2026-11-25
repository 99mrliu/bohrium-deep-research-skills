#!/usr/bin/env python3
"""tile_panels.py — deterministic multi-panel figure segmentation.

No ML: grayscale -> binarize (Otsu) -> row/column ink-projection profiles ->
near-empty gutters become panel boundaries (recursive split with a
min-panel-size guard) -> bbox refinement -> best-effort panel-label detection
(small dark connected clusters near the top-left corner, via our own
scipy-free union-find connected components).

Crops each panel with a margin, upscales 2x (PIL LANCZOS), saves PNGs, and
writes panels.json with every bbox in ORIGINAL image coordinates.

Exit codes: 0 ok / 2 degraded-partial (warnings, single-panel fallback) / 1 fatal.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

PANEL_SCALE = 2            # upscale factor for panel crops
MARGIN_PX = 8              # margin added around each refined panel bbox
MIN_PANEL_FRAC = 0.12      # recursive split guard: min panel side vs full side
GUTTER_INK_FRAC = 0.002    # profile fraction below which a row/col is "empty"
MAX_PANELS_DEFAULT = 16
LABEL_BAND = 0.18          # search band (fraction of panel height) for labels
LABEL_MAX_COMP_FRAC = 0.02 # label components are small vs panel area
LABEL_MIN_COMP_PX = 6      # ignore specks smaller than this


def otsu_threshold(gray):
    """Classic Otsu on a uint8 grayscale array. Returns threshold in [0,255]."""
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = gray.size
    prob = hist / max(total, 1)
    omega = np.cumsum(prob)
    mu = np.cumsum(prob * np.arange(256))
    mu_t = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        sigma_b2 = (mu_t * omega - mu) ** 2 / (omega * (1.0 - omega))
    sigma_b2 = np.nan_to_num(sigma_b2, nan=-1.0)
    return int(np.argmax(sigma_b2))


def ink_mask(pil_img):
    """Boolean HxW mask: True = ink (dark pixel) on a light background."""
    gray = np.asarray(pil_img.convert("L"))
    thr = otsu_threshold(gray)
    # Figures are dark-on-light; ink = clearly darker than threshold.
    mask = gray < max(thr - 10, 0)
    # Safety: if binarization inverted (dark background figure), flip to
    # minority class so "ink" stays the minority content.
    if mask.mean() > 0.5:
        mask = ~mask
    return mask


def _runs_of_empty(profile, empty_thresh, min_len):
    """Return [(start, end)] runs where profile < empty_thresh, len >= min_len."""
    empty = profile < empty_thresh
    runs, start = [], None
    for i, e in enumerate(empty):
        if e and start is None:
            start = i
        elif not e and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(profile) - start >= min_len:
        runs.append((start, len(profile)))
    return runs


def split_recursive(mask, x0, y0, x1, y1, depth, max_panels):
    """Recursively split bbox (x0,y0,x1,y1) of the ink mask on empty gutters."""
    h, w = y1 - y0, x1 - x0
    full_h, full_w = mask.shape
    if depth >= 8:
        return [(x0, y0, x1, y1)]
    if (h < MIN_PANEL_FRAC * full_h and w < MIN_PANEL_FRAC * full_w):
        return [(x0, y0, x1, y1)]

    sub = mask[y0:y1, x0:x1]
    col_profile = sub.mean(axis=0)
    row_profile = sub.mean(axis=1)

    # A gutter must be a wide near-empty band away from the bbox edges.
    min_gutter_v = max(8, int(0.02 * w))
    min_gutter_h = max(8, int(0.02 * h))

    # Prefer the axis with the cleanest single central gutter.
    best = None  # (axis, cut_position)
    for axis, profile, min_gutter, span in (
            ("v", col_profile, min_gutter_v, w),
            ("h", row_profile, min_gutter_h, h)):
        runs = _runs_of_empty(profile, GUTTER_INK_FRAC, min_gutter)
        # ignore runs touching the edges (those are outer margins)
        inner = [r for r in runs if r[0] > 0.05 * span and r[1] < 0.95 * span]
        if inner:
            widest = max(inner, key=lambda r: r[1] - r[0])
            cut = (widest[0] + widest[1]) // 2
            # require both children to respect min panel size
            child_min = MIN_PANEL_FRAC * (full_w if axis == "v" else full_h)
            if cut >= child_min and (span - cut) >= child_min:
                width = widest[1] - widest[0]
                if best is None or width > best[2]:
                    best = (axis, cut, width)
    if best is None:
        return [(x0, y0, x1, y1)]

    axis, cut, _w = best
    if axis == "v":
        left = split_recursive(mask, x0, y0, x0 + cut, y1, depth + 1, max_panels)
        right = split_recursive(mask, x0 + cut, y0, x1, y1, depth + 1, max_panels)
        return left + right
    top = split_recursive(mask, x0, y0, x1, y0 + cut, depth + 1, max_panels)
    bot = split_recursive(mask, x0, y0 + cut, x1, y1, depth + 1, max_panels)
    return top + bot


def refine_bbox(mask, bbox):
    """Tighten bbox to the actual ink extent inside it."""
    x0, y0, x1, y1 = bbox
    sub = mask[y0:y1, x0:x1]
    cols = np.where(sub.any(axis=0))[0]
    rows = np.where(sub.any(axis=1))[0]
    if cols.size == 0 or rows.size == 0:
        return bbox
    return (x0 + int(cols[0]), y0 + int(rows[0]),
            x0 + int(cols[-1]) + 1, y0 + int(rows[-1]) + 1)


def connected_components(binary):
    """Label 4-connected components via union-find. Returns (labels, count)."""
    h, w = binary.shape
    parent = list(range(h * w))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for y in range(h):
        row = binary[y]
        base = y * w
        for x in np.nonzero(row)[0]:
            i = base + x
            if x + 1 < w and binary[y, x + 1]:
                union(i, i + 1)
            if y + 1 < h and binary[y + 1, x]:
                union(i, i + w)
    labels = np.zeros(h * w, dtype=np.int64)
    roots = {}
    n = 0
    for y in range(h):
        for x in np.nonzero(binary[y])[0]:
            i = y * w + x
            r = find(i)
            if r not in roots:
                roots[r] = n
                n += 1
            labels[i] = roots[r]
    return labels.reshape(h, w), n


def guess_panel_label(mask, bbox):
    """Best-effort detection of a panel label like (a)/(b)/A/B near the
    top-left corner inside the panel bbox. Returns string or None."""
    x0, y0, x1, y1 = bbox
    ph, pw = y1 - y0, x1 - x0
    band_h = max(24, int(LABEL_BAND * ph))
    band_w = max(48, int(0.25 * pw))
    region = mask[y0:y0 + band_h, x0:x0 + band_w]
    if region.size == 0 or not region.any():
        return None
    labels, n = connected_components(region)
    if n == 0:
        return None
    max_px = max(LABEL_MIN_COMP_PX, LABEL_MAX_COMP_FRAC * ph * pw)
    # cluster components within the top-left quarter of the search band
    comps = []
    for lab in range(n):
        ys, xs = np.nonzero(labels == lab)
        size = ys.size
        if size < LABEL_MIN_COMP_PX or size > max_px:
            continue
        comps.append((int(xs.min()), int(ys.min()), int(xs.max()) + 1,
                      int(ys.max()) + 1, int(size)))
    if not comps:
        return None
    # label cluster = components whose bbox top is in the upper band and
    # which group tightly together near the left edge
    comps.sort(key=lambda c: (c[1], c[0]))
    anchor = [c for c in comps if c[1] < 0.6 * band_h and c[0] < 0.6 * band_w]
    if not anchor:
        return None
    cx0 = min(c[0] for c in anchor); cy0 = min(c[1] for c in anchor)
    cx1 = max(c[2] for c in anchor); cy1 = max(c[3] for c in anchor)
    cluster_h = cy1 - cy0
    # A plausible label cluster: 1-4 glyphs, modest height vs band.
    if not (1 <= len(anchor) <= 5 and cluster_h <= 0.9 * band_h):
        return None
    return f"label_cluster@({x0 + cx0},{y0 + cy0})-({x0 + cx1},{y0 + cy1}) glyphs={len(anchor)}"


def main():
    ap = argparse.ArgumentParser(description="Segment multi-panel figure (no ML).")
    ap.add_argument("--image", required=True, help="figure image path")
    ap.add_argument("--work", required=True, help="work dir (unused scratch)")
    ap.add_argument("--out", required=True, help="output dir for panel PNGs + panels.json")
    ap.add_argument("--max-panels", type=int, default=MAX_PANELS_DEFAULT)
    args = ap.parse_args()

    if not os.path.isfile(args.image):
        print(json.dumps({"fatal": f"image not found: {args.image}"}))
        return 1
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    warnings = []
    try:
        im = Image.open(args.image)
        rgb = im.convert("RGB")
    except Exception as exc:
        print(json.dumps({"fatal": f"cannot open image: {exc}"}))
        return 1

    w, h = rgb.size
    mask = ink_mask(rgb)
    bboxes = split_recursive(mask, 0, 0, w, h, 0, args.max_panels)
    bboxes = [refine_bbox(mask, b) for b in bboxes]
    # drop degenerate boxes and duplicates
    clean, seen = [], set()
    for (x0, y0, x1, y1) in bboxes:
        if (x1 - x0) < 0.05 * w or (y1 - y0) < 0.05 * h:
            continue
        key = (x0, y0, x1, y1)
        if key not in seen:
            seen.add(key)
            clean.append(key)
    clean.sort(key=lambda b: (b[1] // max(1, h // 4), b[0]))  # reading order

    single_panel = len(clean) <= 1
    if single_panel:
        warnings.append("single_panel_figure: using whole image as one panel")
        clean = [(0, 0, w, h)]
    if len(clean) > args.max_panels:
        warnings.append(f"panel_overflow: {len(clean)} panels > --max-panels; truncating")
        clean = clean[:args.max_panels]

    panels = []
    for i, (x0, y0, x1, y1) in enumerate(clean, start=1):
        label = None if single_panel else guess_panel_label(mask, (x0, y0, x1, y1))
        if label is None and not single_panel:
            warnings.append(f"panel_{i}: no label cluster found (warning only)")
        mx0 = max(0, x0 - MARGIN_PX); my0 = max(0, y0 - MARGIN_PX)
        mx1 = min(w, x1 + MARGIN_PX); my1 = min(h, y1 + MARGIN_PX)
        crop = rgb.crop((mx0, my0, mx1, my1))
        crop = crop.resize((crop.width * PANEL_SCALE, crop.height * PANEL_SCALE),
                           Image.LANCZOS)
        crop_name = f"panel_{i}.png"
        crop.save(os.path.join(args.out, crop_name))
        panels.append({
            "panel_id": f"panel_{i}",
            "label_guess": label,
            "bbox_original": [int(mx0), int(my0), int(mx1), int(my1)],
            "ink_bbox_original": [int(x0), int(y0), int(x1), int(y1)],
            "crop_path": os.path.join(args.out, crop_name),
            "scale": float(PANEL_SCALE),
        })

    doc = {
        "image": os.path.abspath(args.image),
        "image_size": [int(w), int(h)],
        "single_panel": bool(single_panel),
        "n_panels": len(panels),
        "panels": panels,
        "warnings": warnings,
    }
    with open(os.path.join(args.out, "panels.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)

    print(json.dumps({
        "panels_json": os.path.join(args.out, "panels.json"),
        "n_panels": len(panels),
        "single_panel": single_panel,
        "bboxes": [p["bbox_original"] for p in panels],
        "warnings": warnings,
    }, indent=2, ensure_ascii=False))

    return 2 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
