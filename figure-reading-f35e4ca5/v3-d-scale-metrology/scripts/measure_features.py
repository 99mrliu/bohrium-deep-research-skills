#!/usr/bin/env python3
"""measure_features.py -- calibrated measurement on a microscopy figure.

Two modes (can run together):

1. Particle mode (default): background flattening (large-box mean via an
   integral image), Otsu threshold, connected components; per object it
   reports area, equivalent diameter, centroid and bbox, converted to
   physical units.  Objects touching the panel border or smaller than
   3x3 px are excluded and listed with their exclusion reason.

2. Marked-segment mode (--marks JSON): Euclidean length of agent-drawn
   segments [{"id", "p0": [x,y], "p1": [x,y], "note"}] in physical units.

Uncertainty: the relative error of the bar (endpoint_unc / length_px) is
propagated x1 to every length and x2 to every area; marked segments add a
+-1.5 px endpoint error per endpoint (in quadrature).

Exit codes: 0 = at least one object or segment measured,
            2 = valid run but nothing measurable,
            1 = error.

Dependencies: python3 stdlib + numpy + PIL.  No network.
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import deque

import numpy as np
from PIL import Image

MIN_OBJ_DIM_PX = 3          # objects with bbox side < 3 px are excluded
SEG_ENDPOINT_UNC_PX = 1.5   # +-1.5 px per endpoint of an agent-marked segment
MASK_PAD_PX = 4             # padding when masking the bar/label region

UNIT_ALIASES = {
    "nm": "nm",
    "um": "µm", "µm": "µm", "μm": "µm",
    "micron": "µm", "microns": "µm",
    "mm": "mm",
    "pm": "pm",
}


def normalize_unit(unit):
    if unit is None:
        return None, None
    raw = str(unit)
    return UNIT_ALIASES.get(raw.strip().lower(), raw.strip()), raw


def load_gray(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.float64)


def connected_components(mask):
    H, W = mask.shape
    labels = np.zeros((H, W), dtype=np.int32)
    n = 0
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if labels[y0, x0] != 0:
            continue
        n += 1
        labels[y0, x0] = n
        q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and labels[ny, nx] == 0:
                    labels[ny, nx] = n
                    q.append((ny, nx))
    return labels, n


def box_mean(a, k):
    """Large-box mean via integral image (k forced odd, reflect padding)."""
    k = int(k) | 1
    pad = k // 2
    ap = np.pad(a, pad, mode="reflect")
    S = ap.cumsum(axis=0).cumsum(axis=1)
    S2 = np.pad(S, ((1, 0), (1, 0)), mode="constant")
    win = S2[k:, k:] - S2[:-k, k:] - S2[k:, :-k] + S2[:-k, :-k]
    H, W = a.shape
    return win[:H, :W] / float(k * k)


def otsu_threshold(vals):
    hist, edges = np.histogram(vals, bins=256)
    centers = 0.5 * (edges[:-1] + edges[1:])
    p = hist.astype(np.float64)
    total = p.sum()
    if total <= 0:
        return 0.0
    p /= total
    omega = np.cumsum(p)
    mu = np.cumsum(p * centers)
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    denom[denom < 1e-12] = np.nan
    sigma_b2 = (mu_t * omega - mu) ** 2 / denom
    return float(centers[int(np.nanargmax(sigma_b2))])


def rect_to_local(rect, origin, shape):
    """Clip a global [x, y, w, h] rect into panel-local slices; None if empty."""
    x, y, w, h = rect
    ox, oy = origin
    H, W = shape
    x0 = int(max(0, x - MASK_PAD_PX - ox))
    y0 = int(max(0, y - MASK_PAD_PX - oy))
    x1 = int(min(W, x + w + MASK_PAD_PX - ox))
    y1 = int(min(H, y + h + MASK_PAD_PX - oy))
    if x1 <= x0 or y1 <= y0:
        return None
    return (slice(y0, y1), slice(x0, x1))


def measure_particles(gray, calib, scale, u_rel, unit):
    panel = calib.get("panel_bbox")
    ox, oy = 0, 0
    region = gray
    if panel:
        ox, oy = int(panel[0]), int(panel[1])
        region = gray[oy:oy + int(panel[3]), ox:ox + int(panel[2])]
    H, W = region.shape

    k = max(H, W) // 4
    flat = region - box_mean(region, k)
    thr = otsu_threshold(flat)
    fg = flat < thr
    if fg.mean() > 0.5:  # objects must be the minority class
        fg = ~fg
    # never segment the scale bar or its label as "particles"
    for key in ("bar_bbox", "label_region"):
        rect = calib.get(key)
        if rect:
            sl = rect_to_local(rect, (ox, oy), (H, W))
            if sl:
                fg[sl] = False

    labels, n = connected_components(fg)
    objects, excluded = [], []
    oid = 0
    for i in range(1, n + 1):
        ys, xs = np.nonzero(labels == i)
        if ys.size == 0:
            continue
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        w, h = x1 - x0, y1 - y0
        area_px = int(ys.size)
        bbox_global = [x0 + ox, y0 + oy, w, h]
        if x0 == 0 or y0 == 0 or x1 == W or y1 == H:
            excluded.append({"bbox": bbox_global, "area_px": area_px,
                             "reason": "touches panel/image border"})
            continue
        if w < MIN_OBJ_DIM_PX or h < MIN_OBJ_DIM_PX:
            excluded.append({"bbox": bbox_global, "area_px": area_px,
                             "reason": "smaller than %dx%d px" % (MIN_OBJ_DIM_PX, MIN_OBJ_DIM_PX)})
            continue
        oid += 1
        d_px = math.sqrt(4.0 * area_px / math.pi)
        d_phys = d_px * scale
        a_phys = area_px * scale * scale
        objects.append({
            "id": "obj-%03d" % oid,
            "centroid": [round(float(xs.mean()) + ox, 2), round(float(ys.mean()) + oy, 2)],
            "bbox": bbox_global,
            "area_px": area_px,
            "area": {"value": a_phys, "unc": 2.0 * a_phys * u_rel, "unit": unit + "^2"},
            "equiv_diameter_px": round(d_px, 2),
            "equiv_diameter": {"value": d_phys, "unc": d_phys * u_rel, "unit": unit},
        })
    return objects, excluded


def measure_segments(marks, scale, u_rel, unit):
    out = []
    for m in marks:
        p0, p1 = m["p0"], m["p1"]
        d_px = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        u_px = math.sqrt((d_px * u_rel) ** 2 + 2.0 * SEG_ENDPOINT_UNC_PX ** 2)
        out.append({
            "id": m.get("id", "seg-%d" % (len(out) + 1)),
            "p0": list(p0), "p1": list(p1),
            "note": m.get("note", ""),
            "length_px": round(d_px, 2),
            "length": {"value": d_px * scale, "unc": u_px * scale, "unit": unit},
        })
    return out


def summarize(objects, u_rel, unit):
    if not objects:
        return {"count": 0}
    ds = np.array([o["equiv_diameter"]["value"] for o in objects], dtype=np.float64)
    n = int(ds.size)
    mean = float(ds.mean())
    sd = float(ds.std(ddof=1)) if n > 1 else 0.0
    return {
        "count": n,
        "mean_diameter": {
            "value": mean,
            "sd": sd,
            "sem": sd / math.sqrt(n) if n > 1 else None,
            "calibration_unc": mean * u_rel,
            "unit": unit,
            "n": n,
        },
        "median_diameter": {"value": float(np.median(ds)), "unit": unit},
        "exclusion_criteria": ("objects touching the panel/image border or with a "
                               "bbox side < %d px are excluded and listed under "
                               "'excluded'; the scale bar and its label region are "
                               "masked out before segmentation" % MIN_OBJ_DIM_PX),
    }


def main():
    ap = argparse.ArgumentParser(description="Calibrated feature measurement on a microscopy figure.")
    ap.add_argument("--image", required=True)
    ap.add_argument("--calibration", required=True,
                    help="calibration.json: {length_value, unit, length_px, "
                         "endpoint_uncertainty_px, panel_bbox?, bar_bbox?, label_region?, "
                         "verbatim_label?, candidate_index?}")
    ap.add_argument("--marks", default=None,
                    help="optional JSON: [{\"id\", \"p0\": [x,y], \"p1\": [x,y], \"note\"}]")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    try:
        os.makedirs(args.work, exist_ok=True)
        os.makedirs(args.out, exist_ok=True)
        if not os.path.isfile(args.image):
            print("ERROR: image not found: %s" % args.image, file=sys.stderr)
            return 1
        with open(args.calibration, "r", encoding="utf-8") as f:
            calib = json.load(f)
        for key in ("length_value", "length_px"):
            if key not in calib or not isinstance(calib[key], (int, float)) or calib[key] <= 0:
                print("ERROR: calibration.json needs a positive numeric '%s'" % key, file=sys.stderr)
                return 1
        unit, unit_raw = normalize_unit(calib.get("unit"))
        if not unit:
            print("ERROR: calibration.json needs 'unit' (e.g. nm, um/µm/μm, mm)", file=sys.stderr)
            return 1
        u_px = float(calib.get("endpoint_uncertainty_px", 2))
        length_px = float(calib["length_px"])
        length_val = float(calib["length_value"])
        u_rel = u_px / length_px
        scale = length_val / length_px  # physical units per pixel

        gray = load_gray(args.image)
        objects, excluded = measure_particles(gray, calib, scale, u_rel, unit)

        segments = []
        if args.marks:
            with open(args.marks, "r", encoding="utf-8") as f:
                marks = json.load(f)
            segments = measure_segments(marks, scale, u_rel, unit)

        calib_echo = dict(calib)
        calib_echo.update({
            "unit": unit,
            "unit_raw": unit_raw,
            "scale_unit_per_px": scale,
            "relative_uncertainty": u_rel,
            "provenance": ("agent read verbatim label '%s' from the zoomed label crop "
                           "of scale-bar candidate %s; bar bbox %s; length %.2f px ± %.1f px"
                           % (calib.get("verbatim_label", "<not recorded>"),
                              calib.get("candidate_index", "<manual>"),
                              calib.get("bar_bbox", "<not recorded>"),
                              length_px, u_px)),
        })
        mode = []
        if objects or excluded:
            mode.append("particles")
        if segments:
            mode.append("segments")
        result = {
            "image": os.path.abspath(args.image),
            "mode": "+".join(mode) if mode else "none",
            "calibration": calib_echo,
            "objects": objects,
            "excluded": excluded,
            "segments": segments,
            "summary": summarize(objects, u_rel, unit),
        }
        if segments and not objects:
            result["summary"]["note"] = "segment-only measurement; no particle statistics"

        out_json = os.path.join(args.out, "measurements.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        out_csv = os.path.join(args.out, "measurements.csv")
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["type", "id", "centroid_x", "centroid_y", "bbox_x", "bbox_y",
                        "bbox_w", "bbox_h", "area_px", "area_value", "area_unc",
                        "length_or_diam_px", "length_or_diam_value", "length_or_diam_unc",
                        "unit", "note"])
            for o in objects:
                w.writerow(["particle", o["id"], o["centroid"][0], o["centroid"][1],
                            o["bbox"][0], o["bbox"][1], o["bbox"][2], o["bbox"][3],
                            o["area_px"], "%.4g" % o["area"]["value"], "%.4g" % o["area"]["unc"],
                            o["equiv_diameter_px"], "%.4g" % o["equiv_diameter"]["value"],
                            "%.4g" % o["equiv_diameter"]["unc"], unit, ""])
            for s in segments:
                w.writerow(["segment", s["id"], s["p0"][0], s["p0"][1], "", "", "", "",
                            "", "", "", s["length_px"], "%.4g" % s["length"]["value"],
                            "%.4g" % s["length"]["unc"], unit, s["note"]])
        print("Wrote %s and %s" % (out_json, out_csv))
        print("  objects: %d (excluded: %d), segments: %d" % (len(objects), len(excluded), len(segments)))
        if objects:
            s = result["summary"]
            m = s["mean_diameter"]
            print("  count=%d  mean diameter=%.4g ± %.3g (sd) %s  median=%.4g %s  (calibration rel. unc %.2f%%)"
                  % (s["count"], m["value"], m["sd"], unit,
                     s["median_diameter"]["value"], unit, 100 * u_rel))
        if not objects and not segments:
            print("Nothing measurable survived filtering. If the preview shows the")
            print("segmentation failed, fall back to --marks with agent-drawn segments.")
            return 2
        return 0
    except Exception as exc:  # noqa: BLE001
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
