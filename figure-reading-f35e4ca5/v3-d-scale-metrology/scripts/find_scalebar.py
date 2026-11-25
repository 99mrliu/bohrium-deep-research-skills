#!/usr/bin/env python3
"""find_scalebar.py -- detect scale-bar candidates in a microscopy figure.

Thresholds the grayscale image both dark-on-light and light-on-dark, labels
connected components (pure-numpy BFS, no scipy), and keeps components that
look like a scale bar: long thin near-axis rectangle, high fill ratio,
located in the outer 40% of the image, length a plausible fraction of the
image width.  For every candidate a zoomed label crop (region just
above/below the bar, 3x upscaled, contrast-stretched) is saved as PNG so the
agent can read the label verbatim.

Exit codes: 0 = at least one candidate (or manual bar accepted),
            2 = no candidate found (fallback instructions printed),
            1 = error.

Dependencies: python3 stdlib + numpy + PIL.  No network.
"""

import argparse
import json
import math
import os
import sys
from collections import deque

import numpy as np
from PIL import Image

# --- candidate selection constants -----------------------------------------
MIN_ASPECT = 4.0        # long/short side of bounding box
MIN_FILL = 0.6          # component pixels / bbox area
OUTER_FRAC = 0.4        # bar centroid must lie in the outer 40% band ...
MIN_LEN_FRAC = 0.15     # ... and be 15-60% of the image width.  The nominal
MAX_LEN_FRAC = 0.60     # window is 20-60%; the lower edge is widened slightly
                        # so bars sitting just under 20% of the width are not
                        # silently dropped.
ENDPOINT_UNC_PX = 2     # +-2 px per endpoint, recorded for every candidate
FILL_TILT = 0.85        # below this fill the bar may be tilted -> PCA length

# --- label crop constants ---------------------------------------------------
CROP_UP = 40            # pixels above the bar included in the label crop
CROP_DOWN = 14          # pixels below the bar
CROP_PAD_X = 14         # horizontal padding
UPSCALE = 3             # zoom factor for the label crop


def load_gray(path):
    img = Image.open(path).convert("L")
    return np.asarray(img, dtype=np.float64)


def connected_components(mask):
    """4-connected component labeling via BFS. Returns (label_array, n)."""
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


def polarity_masks(gray):
    """Return (dark_mask, light_mask) using a robust background estimate.

    The background level is the peak of the (lightly smoothed) histogram;
    the noise scale is the MAD of pixels near that peak.  This survives
    images where dark objects cover close to half of the frame, where a
    plain mean/std or median estimate would be dragged into the object
    population.
    """
    hist, edges = np.histogram(gray, bins=256, range=(0, 256))
    smooth = np.convolve(hist.astype(np.float64), np.ones(3) / 3.0, mode="same")
    peak = int(np.argmax(smooth))
    bg = 0.5 * (edges[peak] + edges[peak + 1])
    near = gray[np.abs(gray - bg) < 40]
    if near.size < 100:
        near = gray.ravel()
    noise = 1.4826 * np.median(np.abs(near - np.median(near)))
    noise = max(float(noise), 1.0)
    dark = gray < bg - max(5.0 * noise, 25.0)
    light = gray > bg + max(5.0 * noise, 20.0)
    return dark, light, {"bg_level": float(bg), "noise": float(noise)}


def component_stats(labels, n):
    """Yield per-component dicts with bbox, area, centroid."""
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(labels == i)
        if ys.size == 0:
            continue
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        out.append({
            "label": i,
            "bbox": [x0, y0, x1 - x0, y1 - y0],
            "area_px": int(ys.size),
            "centroid": [float(xs.mean()), float(ys.mean())],
            "pixels": (ys, xs),
        })
    return out


def pca_length(pixels):
    """Length of the component along its principal axis (for tilted bars)."""
    ys, xs = pixels
    pts = np.stack([xs.astype(np.float64), ys.astype(np.float64)], axis=1)
    pts -= pts.mean(axis=0)
    cov = pts.T @ pts / max(len(pts) - 1, 1)
    vals, vecs = np.linalg.eigh(cov)
    axis = vecs[:, int(np.argmax(vals))]
    proj = pts @ axis
    angle = math.degrees(math.atan2(axis[1], axis[0]))
    return float(proj.max() - proj.min()), float(angle)


def evaluate(comp, W, H, polarity, idx):
    x0, y0, w, h = comp["bbox"]
    if w < 2 or h < 2:
        return None
    long_side, short_side = max(w, h), min(w, h)
    aspect = long_side / short_side
    fill = comp["area_px"] / float(w * h)
    if aspect < MIN_ASPECT or fill < MIN_FILL:
        return None
    cx, cy = comp["centroid"]
    in_outer = (cx < OUTER_FRAC * W or cx > (1 - OUTER_FRAC) * W or
                cy < OUTER_FRAC * H or cy > (1 - OUTER_FRAC) * H)
    if not in_outer:
        return None
    if not (MIN_LEN_FRAC * W <= long_side <= MAX_LEN_FRAC * W):
        return None
    if fill >= FILL_TILT:
        orientation = "horizontal" if w >= h else "vertical"
        length_px = float(long_side)
        tilt_angle_deg = 0.0
    else:
        # possible tilted bar: measure along the principal axis
        length_px, tilt_angle_deg = pca_length(comp["pixels"])
        orientation = "tilted"
    return {
        "index": idx,
        "polarity": polarity,
        "bbox": [x0, y0, w, h],
        "length_px": round(length_px, 2),
        "orientation": orientation,
        "tilt_angle_deg": round(tilt_angle_deg, 1),
        "aspect_ratio": round(aspect, 2),
        "fill_ratio": round(fill, 3),
        "centroid": [round(cx, 1), round(cy, 1)],
        "endpoint_uncertainty_px": ENDPOINT_UNC_PX,
        "note": "Read the label VERBATIM from label_crop_png, then write "
                "calibration.json with length_value + unit from the label and "
                "length_px / endpoint_uncertainty_px / bar_bbox from this candidate.",
    }


def make_label_crop(gray, cand, work_dir):
    """Zoomed, contrast-stretched crop of the region around the bar."""
    x0, y0, w, h = cand["bbox"]
    H, W = gray.shape
    if cand["orientation"] == "vertical":
        cx0 = max(0, x0 - CROP_UP)
        cx1 = min(W, x0 + w + CROP_DOWN)
        cy0 = max(0, y0 - CROP_PAD_X)
        cy1 = min(H, y0 + h + CROP_PAD_X)
    else:
        cx0 = max(0, x0 - CROP_PAD_X)
        cx1 = min(W, x0 + w + CROP_PAD_X)
        cy0 = max(0, y0 - CROP_UP)
        cy1 = min(H, y0 + h + CROP_DOWN)
    crop = gray[cy0:cy1, cx0:cx1]
    lo, hi = float(crop.min()), float(crop.max())
    if hi > lo:
        crop = (crop - lo) * (255.0 / (hi - lo))
    img = Image.fromarray(crop.astype(np.uint8), "L")
    img = img.resize((img.width * UPSCALE, img.height * UPSCALE), Image.LANCZOS)
    path = os.path.join(work_dir, "label_crop_cand%d.png" % cand["index"])
    img.save(path)
    return path, [cx0, cy0, cx1 - cx0, cy1 - cy0]


def run_detection(image_path, work_dir):
    gray = load_gray(image_path)
    H, W = gray.shape
    dark, light, bginfo = polarity_masks(gray)
    candidates = []
    idx = 0
    for polarity, mask in (("dark-on-light", dark), ("light-on-dark", light)):
        labels, n = connected_components(mask)
        for comp in component_stats(labels, n):
            c = evaluate(comp, W, H, polarity, idx)
            if c is not None:
                candidates.append(c)
                idx += 1
    for c in candidates:
        crop_path, region = make_label_crop(gray, c, work_dir)
        c["label_crop_png"] = os.path.abspath(crop_path)
        c["label_region"] = region
    return gray, candidates, bginfo


def manual_bar_candidate(gray, manual):
    p0, p1 = manual["p0"], manual["p1"]
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    angle = abs(math.degrees(math.atan2(dy, dx)))
    if angle > 90:
        angle = 180 - angle
    orientation = "horizontal" if angle < 15 else ("vertical" if angle > 75 else "tilted")
    x0 = int(max(0, min(p0[0], p1[0]) - 6))
    y0 = int(max(0, min(p0[1], p1[1]) - 6))
    x1 = int(min(gray.shape[1], max(p0[0], p1[0]) + 7))
    y1 = int(min(gray.shape[0], max(p0[1], p1[1]) + 7))
    return {
        "index": 0,
        "polarity": "agent-marked",
        "bbox": [x0, y0, x1 - x0, y1 - y0],
        "length_px": round(length, 2),
        "orientation": orientation,
        "tilt_angle_deg": round(angle, 1),
        "aspect_ratio": None,
        "fill_ratio": None,
        "centroid": [(p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0],
        "endpoint_uncertainty_px": ENDPOINT_UNC_PX,
        "verbatim_label_hint": manual.get("verbatim_label"),
        "note": "Agent-marked bar endpoints (fallback path). Verify the label "
                "verbatim in label_crop_png before writing calibration.json.",
    }


def main():
    ap = argparse.ArgumentParser(description="Detect scale-bar candidates in a microscopy figure.")
    ap.add_argument("--image", required=True, help="path to the figure image")
    ap.add_argument("--work", required=True, help="working directory (label crops go here)")
    ap.add_argument("--out", required=True, help="output directory for scalebar_candidates.json")
    ap.add_argument("--manual-bar", default=None,
                    help="fallback: JSON file {\"p0\": [x,y], \"p1\": [x,y], "
                         "\"verbatim_label\": optional} with agent-marked bar endpoints")
    args = ap.parse_args()

    try:
        os.makedirs(args.work, exist_ok=True)
        os.makedirs(args.out, exist_ok=True)
        if not os.path.isfile(args.image):
            print("ERROR: image not found: %s" % args.image, file=sys.stderr)
            return 1
        gray = load_gray(args.image)
        H, W = gray.shape

        if args.manual_bar:
            with open(args.manual_bar, "r", encoding="utf-8") as f:
                manual = json.load(f)
            cand = manual_bar_candidate(gray, manual)
            crop_path, region = make_label_crop(gray, cand, args.work)
            cand["label_crop_png"] = os.path.abspath(crop_path)
            cand["label_region"] = region
            candidates, bginfo = [cand], {}
        else:
            _, candidates, bginfo = run_detection(args.image, args.work)

        result = {
            "image": os.path.abspath(args.image),
            "image_size": [W, H],
            "background_estimate": bginfo,
            "n_candidates": len(candidates),
            "candidates": candidates,
            "endpoint_uncertainty_px": ENDPOINT_UNC_PX,
            "next_step": "Read each label_crop_png, transcribe the label verbatim, "
                         "and write calibration.json (see SKILL.md step 2).",
        }
        out_path = os.path.join(args.out, "scalebar_candidates.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        if not candidates:
            print("NO CANDIDATE FOUND. Fallback options:")
            print("  1) Look at the figure yourself. If a bar is visible, mark its")
            print("     endpoints in a JSON file, e.g.")
            print("       {\"p0\": [x0, y0], \"p1\": [x1, y1], \"verbatim_label\": \"500 nm\"}")
            print("     and rerun with --manual-bar <file>.")
            print("  2) If the figure has NO scale bar, no calibration is possible;")
            print("     keep status 'partial' and state that explicitly. Never guess.")
            print("Wrote %s" % out_path)
            return 2
        print("Found %d candidate(s). Wrote %s" % (len(candidates), out_path))
        for c in candidates:
            print("  cand %d: %s len=%.1f px bbox=%s crop=%s"
                  % (c["index"], c["orientation"], c["length_px"], c["bbox"],
                     c["label_crop_png"]))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI must map any failure to exit 1
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
