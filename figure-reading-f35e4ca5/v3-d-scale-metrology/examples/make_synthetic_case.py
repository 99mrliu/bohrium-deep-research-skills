#!/usr/bin/env python3
"""make_synthetic_case.py -- generate a SYNTHETIC demo case for the
scale-bar-metrology skill.  Everything produced here is artificial and exists
only to exercise the pipeline; no real sample, no real instrument.

Scene (1024x768 grayscale PNG):
  * noisy gray background with a gentle illumination gradient
  * ~40 dark elliptical blobs with known diameters in the 60-160 px range
    (ground truth saved alongside, for the README accuracy note only)
  * a white horizontal scale bar, exactly 200 px long, near the bottom-right,
    with black "500 nm" text drawn above it in the PIL default font

Also written: ground_truth.json, case.json (case_id "synthetic-demo-D"),
task.md (2 questions), imaging_conditions.csv (one small table).

Usage:  python3 make_synthetic_case.py --out /tmp/f35e-d-demo
        (without --out, a tempfile.mkdtemp directory is used and printed)
"""

import argparse
import csv
import json
import math
import os
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1024, 768
N_BLOBS = 40
BAR_LEN_PX = 200
BAR_THICK_PX = 12
BAR_LABEL = "500 nm"
BAR_MARGIN_X = 60
BAR_MARGIN_Y = 70


def place_blobs(rng, forbidden):
    """Rejection-sample non-overlapping ellipse placements.

    Diameters span 60-160 px with a distribution skewed toward smaller sizes
    (d = 60 + 100*u**1.8) so that ~40 non-overlapping blobs fit the frame.
    Returns a list of dicts.
    """
    fx0, fy0 = forbidden
    blobs = []
    tries = 0
    while len(blobs) < N_BLOBS and tries < 60000:
        tries += 1
        d = 60.0 + 100.0 * float(rng.uniform()) ** 1.8
        ar = float(rng.uniform(0.75, 1.0))
        a, b = d, d * ar                      # full axis lengths
        cx = float(rng.uniform(a / 2 + 10, W - a / 2 - 10))
        cy = float(rng.uniform(b / 2 + 10, H - b / 2 - 10))
        # keep clear of the scale-bar / label zone (bottom-right corner)
        if cx + a / 2 + 10 > fx0 and cy + b / 2 + 10 > fy0:
            continue
        # keep clear of other blobs (bounding-circle test + gap)
        ok = True
        for ob in blobs:
            dist = math.hypot(cx - ob["cx"], cy - ob["cy"])
            if dist < (d + ob["d"]) / 2.0 + 8.0:
                ok = False
                break
        if not ok:
            continue
        blobs.append({"id": "blob-%02d" % (len(blobs) + 1), "cx": cx, "cy": cy,
                      "a_px": a, "b_px": b, "d": d})
    return blobs


def main():
    ap = argparse.ArgumentParser(description="Generate a SYNTHETIC scale-bar-metrology demo case.")
    ap.add_argument("--out", default=None, help="output directory (default: a fresh temp dir)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    out = args.out or tempfile.mkdtemp(prefix="f35e-d-demo-")
    os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    # --- background ---------------------------------------------------------
    yy, xx = np.mgrid[0:H, 0:W]
    img = 180.0 + 10.0 * (xx / W - 0.5) + rng.normal(0.0, 6.0, (H, W))
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "L")
    draw = ImageDraw.Draw(pil)

    # --- scale bar geometry (bottom-right) ----------------------------------
    bx0 = W - BAR_MARGIN_X - BAR_LEN_PX
    by0 = H - BAR_MARGIN_Y
    bx1, by1 = bx0 + BAR_LEN_PX, by0 + BAR_THICK_PX
    forbidden = (bx0 - 30, by0 - 70)

    # --- blobs ---------------------------------------------------------------
    blobs = place_blobs(rng, forbidden)
    for bl in blobs:
        fill = int(rng.uniform(45, 75))
        draw.ellipse([bl["cx"] - bl["a_px"] / 2, bl["cy"] - bl["b_px"] / 2,
                      bl["cx"] + bl["a_px"] / 2, bl["cy"] + bl["b_px"] / 2],
                     fill=fill)

    # soften like a real micrograph, then add a little fresh grain
    pil = pil.filter(ImageFilter.GaussianBlur(1.0))
    arr = np.asarray(pil, dtype=np.float64) + rng.normal(0.0, 4.0, (H, W))
    pil = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "L")
    draw = ImageDraw.Draw(pil)

    # --- scale bar + label (crisp, drawn last) -------------------------------
    draw.rectangle([bx0, by0, bx1 - 1, by1 - 1], fill=245)
    font = ImageFont.load_default()
    label_xy = (bx0 + BAR_LEN_PX // 2 - 18, by0 - 16)
    draw.text(label_xy, BAR_LABEL, fill=0, font=font)

    fig_path = os.path.join(out, "synthetic_figure.png")
    pil.save(fig_path)

    # --- ground truth (README accuracy note only; NOT shipped to the agent) --
    gt = {
        "SYNTHETIC": True,
        "note": "ground truth for the synthetic demo; equivalent diameter of an "
                "ellipse with full axes a,b is sqrt(a*b); scale is 500 nm / 200 px "
                "= 2.5 nm/px",
        "image_size": [W, H],
        "bar": {"length_px": BAR_LEN_PX, "thickness_px": BAR_THICK_PX,
                "bbox": [bx0, by0, BAR_LEN_PX, BAR_THICK_PX], "label": BAR_LABEL},
        "blobs": [{"id": b["id"], "cx": round(b["cx"], 1), "cy": round(b["cy"], 1),
                   "a_px": round(b["a_px"], 2), "b_px": round(b["b_px"], 2),
                   "equiv_diameter_px": round(math.sqrt(b["a_px"] * b["b_px"]), 2),
                   "equiv_diameter_nm": round(math.sqrt(b["a_px"] * b["b_px"]) * 2.5, 2)}
                  for b in blobs],
    }
    ds = np.array([b["equiv_diameter_px"] for b in gt["blobs"]])
    gt["summary"] = {
        "count": len(blobs),
        "mean_equiv_diameter_px": float(ds.mean()),
        "mean_equiv_diameter_nm": float(ds.mean() * 2.5),
        "sd_equiv_diameter_nm": float(ds.std(ddof=1) * 2.5),
        "median_equiv_diameter_nm": float(np.median(ds) * 2.5),
    }
    with open(os.path.join(out, "ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump(gt, f, indent=2)

    # --- case.json ------------------------------------------------------------
    case = {
        "case_id": "synthetic-demo-D",
        "SYNTHETIC": True,
        "output_contract": {
            "scale_calibration": "physical units per pixel, with uncertainty, derived "
                                 "from the scale bar (stated magnification is metadata only)",
            "particle_count": "number of fully visible particles (integer)",
            "mean_diameter_nm": "mean equivalent particle diameter in nm, with "
                                "uncertainty and n",
        },
        "materials": [
            {"type": "figure", "path": "synthetic_figure.png",
             "description": "SYNTHETIC SEM-like image: dark particles + white scale bar"},
            {"type": "table", "path": "imaging_conditions.csv",
             "description": "SYNTHETIC nominal imaging conditions"},
        ],
    }
    with open(os.path.join(out, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, indent=2)

    # --- task.md --------------------------------------------------------------
    with open(os.path.join(out, "task.md"), "w", encoding="utf-8") as f:
        f.write("# Synthetic demo task (synthetic-demo-D)\n\n"
                "All materials in this case are SYNTHETIC.\n\n"
                "1. Calibrate the figure's scale from its scale bar: report physical "
                "units per pixel with uncertainty. The stated magnification in the "
                "table is metadata only -- do not use it for measurement.\n"
                "2. Count the fully visible particles and report the mean equivalent "
                "diameter in nm with uncertainty (state n and exclusion criteria).\n")

    # --- one small CSV table ---------------------------------------------------
    with open(os.path.join(out, "imaging_conditions.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["parameter", "value", "note"])
        w.writerow(["instrument", "synthetic-SEM-3000", "SYNTHETIC"])
        w.writerow(["accelerating_voltage_kV", "15.0", "SYNTHETIC"])
        w.writerow(["working_distance_mm", "8.2", "SYNTHETIC"])
        w.writerow(["stated_magnification", "20000x",
                    "metadata only - NOT valid for measurement after rendering"])
        w.writerow(["detector", "secondary electron", "SYNTHETIC"])

    print("SYNTHETIC case written to: %s" % os.path.abspath(out))
    print("  blobs placed: %d (mean equiv diameter %.1f px = %.1f nm)"
          % (len(blobs), gt["summary"]["mean_equiv_diameter_px"],
             gt["summary"]["mean_equiv_diameter_nm"]))
    print("  bar: %d px at bbox %s, label %r"
          % (BAR_LEN_PX, gt["bar"]["bbox"], BAR_LABEL))


if __name__ == "__main__":
    main()
