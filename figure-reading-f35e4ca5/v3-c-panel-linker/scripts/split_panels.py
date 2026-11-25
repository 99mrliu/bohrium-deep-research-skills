#!/usr/bin/env python3
"""split_panels.py — deterministic multi-panel figure segmentation.

Segments a figure image into panels using grayscale ink-projection profiles and
recursive gutter splitting (no ML, no network). Detects panel label clusters
((a), a, A, ...) near each panel's top-left via pure-numpy connected components,
refines bboxes, saves panel crops and writes panel_map.json.

CLI: --image PATH --work DIR --out DIR [--override PATH]

Exit codes: 0 = clean, 2 = success with warnings, 1 = fatal error.
"""
import argparse
import json
import os
import string
import sys

import numpy as np
from PIL import Image

INK_THRESHOLD = 200          # grayscale value below which a pixel counts as ink
MIN_GUTTER_FRAC = 0.012      # min gutter width as fraction of the split dimension
MIN_PANEL_FRAC = 0.10        # min panel side as fraction of the full image side
CROP_MARGIN = 6              # px margin added around each crop
LETTERS = string.ascii_lowercase


def fatal(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def load_ink(path):
    if not os.path.isfile(path):
        fatal(f"image not found: {path}")
    try:
        img = Image.open(path).convert("L")
    except Exception as exc:  # noqa: BLE001
        fatal(f"cannot read image {path}: {exc}")
    gray = np.asarray(img, dtype=np.uint8)
    ink = gray < INK_THRESHOLD
    return img, ink


def empty_runs(profile, eps):
    """Return list of (start, length) runs where profile <= eps."""
    runs = []
    start = None
    for i, v in enumerate(profile):
        if v <= eps:
            if start is None:
                start = i
        else:
            if start is not None:
                runs.append((start, i - start))
                start = None
    if start is not None:
        runs.append((start, len(profile) - start))
    return runs


def best_gutter(ink, x0, y0, x1, y1, axis, min_gutter):
    """Best gutter (position, size) along axis 0=horizontal split (rows), 1=vertical."""
    sub = ink[y0:y1, x0:x1]
    dim = sub.shape[axis]
    span = sub.shape[1 - axis]
    eps = max(1, int(0.002 * span))
    profile = sub.sum(axis=1 - axis)
    runs = [(s, l) for (s, l) in empty_runs(profile, eps) if l >= min_gutter]
    if not runs:
        return None
    center = dim / 2.0
    # prefer long gutters near the middle of the region
    best = max(runs, key=lambda r: (r[1], -abs(r[0] + r[1] / 2.0 - center)))
    pos = best[0] + best[1] // 2
    return pos, best[1]


def split_recursive(ink, x0, y0, x1, y1, min_w, min_h, min_gutter, depth=0):
    """Recursively split region; return list of leaf bboxes."""
    if depth > 12:
        return [(x0, y0, x1, y1)]
    candidates = []
    g_h = best_gutter(ink, x0, y0, x1, y1, axis=0, min_gutter=min_gutter)
    if g_h and g_h[0] >= min_h and (y1 - y0) - g_h[0] >= min_h:
        candidates.append(("h", g_h))
    g_v = best_gutter(ink, x0, y0, x1, y1, axis=1, min_gutter=min_gutter)
    if g_v and g_v[0] >= min_w and (x1 - x0) - g_v[0] >= min_w:
        candidates.append(("v", g_v))
    if not candidates:
        return [(x0, y0, x1, y1)]
    # split along the orientation with the wider gutter (ties -> horizontal first)
    orient, (pos, _size) = max(candidates, key=lambda c: (c[1][1], c[0] == "h"))
    if orient == "h":
        cut = y0 + pos
        return (split_recursive(ink, x0, y0, x1, cut, min_w, min_h, min_gutter, depth + 1)
                + split_recursive(ink, x0, cut, x1, y1, min_w, min_h, min_gutter, depth + 1))
    cut = x0 + pos
    return (split_recursive(ink, x0, y0, cut, y1, min_w, min_h, min_gutter, depth + 1)
            + split_recursive(ink, cut, y0, x1, y1, min_w, min_h, min_gutter, depth + 1))


def refine_bbox(ink, x0, y0, x1, y1, pad=4):
    sub = ink[y0:y1, x0:x1]
    rows = np.where(sub.any(axis=1))[0]
    cols = np.where(sub.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return (x0, y0, x1, y1)
    h, w = ink.shape
    return (max(0, x0 + cols[0] - pad), max(0, y0 + rows[0] - pad),
            min(w, x0 + cols[-1] + 1 + pad), min(h, y0 + rows[-1] + 1 + pad))


def reading_order(bboxes):
    """Sort bboxes in reading order (row-major with row clustering)."""
    if not bboxes:
        return []
    heights = sorted(b[3] - b[1] for b in bboxes)
    row_tol = max(10, heights[len(heights) // 2] // 2)
    remaining = sorted(bboxes, key=lambda b: (b[1], b[0]))
    rows = []
    for b in remaining:
        if rows and abs(b[1] - rows[-1][0][1]) <= row_tol:
            rows[-1].append(b)
        else:
            rows.append([b])
    ordered = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda b: b[0]))
    return ordered


def connected_components(mask):
    """Pure-python 4-connectivity components on a small boolean patch.

    Returns list of (x0, y0, x1, y1, area)."""
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    comps = []
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not visited[y, x]:
                stack = [(y, x)]
                visited[y, x] = True
                xs, ys = [], []
                while stack:
                    cy, cx = stack.pop()
                    xs.append(cx)
                    ys.append(cy)
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((ny, nx))
                comps.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1, len(xs)))
    return comps


def detect_label(ink, bbox):
    """Heuristic: is there a short text run (a panel label) near the panel's top-left?

    Character-like components are grouped into horizontal runs (small x-gap,
    aligned baselines, similar heights); a run of >= 2 chars, or one solid
    letter-like blob, counts as a label. Tick labels elsewhere in the patch do
    not poison the check because runs are local, not patch-global."""
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    pw, ph = max(10, int(0.22 * w)), max(10, int(0.18 * h))
    patch = ink[y0:y0 + ph, x0:x0 + pw]
    comps = connected_components(patch)
    plausible = []
    for (cx0, cy0, cx1, cy1, area) in comps:
        cw, ch = cx1 - cx0, cy1 - cy0
        if 2 <= cw <= 0.5 * pw and 4 <= ch <= 0.9 * ph and 4 <= area <= 0.5 * pw * ph:
            plausible.append((cx0, cy0, cx1, cy1, area))
    if not plausible:
        return False
    plausible.sort(key=lambda c: c[0])
    runs = []
    for c in plausible:
        for run in runs:
            last = run[-1]
            gap = c[0] - last[2]
            h1, h2 = last[3] - last[1], c[3] - c[1]
            overlap = min(last[3], c[3]) - max(last[1], c[1])
            if (gap <= max(12, int(1.2 * max(h1, h2)))
                    and overlap >= 0.5 * min(h1, h2)
                    and max(h1, h2) <= 2.2 * min(h1, h2)):
                run.append(c)
                break
        else:
            runs.append([c])
    for run in runs:
        heights = [c[3] - c[1] for c in run]
        run_w = run[-1][2] - run[0][0]
        if len(run) >= 2 and max(heights) >= 8 and run_w <= 0.9 * pw:
            return True
        if len(run) == 1:
            cx0, cy0, cx1, cy1, area = run[0]
            cw, ch = cx1 - cx0, cy1 - cy0
            if 8 <= ch <= 40 and 3 <= cw <= 2.5 * ch and area >= 0.3 * cw * ch:
                return True
    return False


def load_override(work, override_path, warnings):
    path = override_path or os.path.join(work, "panel_override.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        panels = data["panels"]
        boxes = []
        for p in panels:
            b = p["bbox"]
            if len(b) != 4 or b[2] <= b[0] or b[3] <= b[1]:
                raise ValueError(f"bad bbox in override: {b}")
            boxes.append((int(b[0]), int(b[1]), int(b[2]), int(b[3])))
    except Exception as exc:  # noqa: BLE001
        fatal(f"invalid panel override file {path}: {exc}")
    warnings.append(f"manual_bbox_override_used: {path}")
    return boxes


def main():
    ap = argparse.ArgumentParser(description="Segment a multi-panel figure deterministically.")
    ap.add_argument("--image", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--override", default=None,
                    help="manual bbox override JSON (default: <work>/panel_override.json if present)")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    img, ink = load_ink(args.image)
    H, W = ink.shape
    warnings = []

    boxes = load_override(args.work, args.override, warnings)
    if boxes is None:
        min_w = max(40, int(MIN_PANEL_FRAC * W))
        min_h = max(40, int(MIN_PANEL_FRAC * H))
        min_gutter = max(6, int(MIN_GUTTER_FRAC * max(W, H)))
        boxes = split_recursive(ink, 0, 0, W, H, min_w, min_h, min_gutter)
        boxes = [refine_bbox(ink, *b) for b in boxes]

    boxes = reading_order(boxes)
    single_panel = len(boxes) <= 1
    if single_panel:
        warnings.append("single_panel: no gutter split possible; whole image treated as one panel")
    if len(boxes) > 12:
        warnings.append(f"many_panels: {len(boxes)} panels found; check for over-segmentation")

    detected = [detect_label(ink, b) if not single_panel else False for b in boxes]
    any_label = any(detected)
    all_label = all(detected) if boxes else False
    if any_label and not all_label:
        warnings.append("partial_label_detection: labels found on some panels only; "
                        "letters for undetected panels assigned by reading order")

    panels = []
    for idx, bbox in enumerate(boxes):
        label = detected[idx]
        # consistent ids: if any panel shows a label cluster, every panel gets a
        # letter guess by reading order; otherwise positional ids (flagged).
        letter = LETTERS[idx] if any_label and idx < len(LETTERS) else None
        pid = f"p_{letter}" if letter else f"p{idx + 1}"
        x0, y0, x1, y1 = bbox
        cx0, cy0 = max(0, x0 - CROP_MARGIN), max(0, y0 - CROP_MARGIN)
        cx1, cy1 = min(W, x1 + CROP_MARGIN), min(H, y1 + CROP_MARGIN)
        crop_path = os.path.join(args.out, f"{pid}.png")
        img.crop((cx0, cy0, cx1, cy1)).save(crop_path)
        panels.append({
            "id": pid,
            "label_guess": letter,
            "label_guess_basis": "reading_order" if letter else None,
            "label_detected": bool(label),
            "bbox": [int(x0), int(y0), int(x1), int(y1)],
            "crop": crop_path,
        })
    if not any_label and not single_panel:
        warnings.append("no_panel_labels_detected: using positional ids (row-major)")

    panel_map = {
        "schema": "panel_map/1",
        "image": args.image,
        "image_size": [int(W), int(H)],
        "panels": panels,
        "labels_detected": any_label,
        "single_panel": single_panel,
        "warnings": warnings,
    }
    out_path = os.path.join(args.work, "panel_map.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(panel_map, fh, ensure_ascii=False, indent=2)
    print(f"wrote {out_path} with {len(panels)} panel(s); crops in {args.out}")
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    sys.exit(2 if warnings else 0)


if __name__ == "__main__":
    main()
