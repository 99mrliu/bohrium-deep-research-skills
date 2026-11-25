#!/usr/bin/env python3
"""metrology_result.py -- assemble the metrology deliverable.

Renders an annotated preview PNG (detected bar in red, measured objects
outlined and numbered, marked segments drawn, calibration caption) for the
agent to inspect, and writes result_fragment.json shaped for easy merging
into the case result.json: units on every number, a provenance block, an
uncertainty block, and a status suggestion.

Exit codes: 0 = fragment written with at least one measurement,
            2 = fragment written but no objects/segments (status 'partial'),
            1 = error.

Dependencies: python3 stdlib + numpy + PIL + matplotlib (Agg backend,
preview rendering only).
"""

import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image


def render_preview(image_path, meas, out_dir):
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    fig, ax = plt.subplots(figsize=(W / 100.0, H / 100.0), dpi=150)
    ax.imshow(img)
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")

    calib = meas.get("calibration", {})
    bar = calib.get("bar_bbox")
    if bar:
        ax.add_patch(Rectangle((bar[0], bar[1]), bar[2], bar[3],
                               fill=False, edgecolor="red", linewidth=2))
        ax.text(bar[0], bar[1] - 4, "scale bar", color="red", fontsize=8,
                fontweight="bold")
    for o in meas.get("objects", []):
        x, y, w, h = o["bbox"]
        ax.add_patch(Rectangle((x, y), w, h, fill=False, edgecolor="lime",
                               linewidth=1))
        ax.text(o["centroid"][0], o["centroid"][1], o["id"].split("-")[-1],
                color="yellow", fontsize=6, ha="center", va="center")
    for s in meas.get("segments", []):
        ax.plot([s["p0"][0], s["p1"][0]], [s["p0"][1], s["p1"][1]],
                color="cyan", linewidth=2)
        ax.text((s["p0"][0] + s["p1"][0]) / 2, (s["p0"][1] + s["p1"][1]) / 2 - 6,
                s["id"], color="cyan", fontsize=8, ha="center")

    caption = "calibration: %s = %.2f px (±%.1f px), %.4g %s/px" % (
        calib.get("verbatim_label", "%g %s" % (calib.get("length_value", 0),
                                               calib.get("unit", "?"))),
        calib.get("length_px", 0.0),
        calib.get("endpoint_uncertainty_px", 0.0),
        calib.get("scale_unit_per_px", 0.0),
        calib.get("unit", "?"),
    )
    fig.text(0.01, 0.01, caption, fontsize=10, color="black",
             bbox=dict(facecolor="white", alpha=0.85, edgecolor="gray"))
    path = os.path.join(out_dir, "annotated_preview.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    return path, caption


def build_fragment(meas, preview_path, caption):
    calib = meas.get("calibration", {})
    summary = meas.get("summary", {})
    unit = calib.get("unit")
    u_rel = calib.get("relative_uncertainty")

    fragment = {
        "scale_calibration": {
            "scale": {"value": calib.get("scale_unit_per_px"),
                      "unit": ("%s/px" % unit)},
            "bar": {"length_value": calib.get("length_value"), "unit": unit,
                    "length_px": calib.get("length_px"),
                    "endpoint_uncertainty_px": calib.get("endpoint_uncertainty_px"),
                    "bbox": calib.get("bar_bbox")},
            "relative_uncertainty": u_rel,
            "verbatim_label": calib.get("verbatim_label"),
        },
        "particle_count": {
            "value": summary.get("count", 0),
            "unit": "count",
            "excluded": len(meas.get("excluded", [])),
            "exclusion_criteria": summary.get("exclusion_criteria"),
        },
        "mean_equivalent_diameter": summary.get("mean_diameter"),
        "median_equivalent_diameter": summary.get("median_diameter"),
        "marked_segments": [
            {"id": s["id"], "length": s["length"], "note": s.get("note", "")}
            for s in meas.get("segments", [])
        ],
    }
    has_meas = bool(meas.get("objects") or meas.get("segments"))
    return {
        "metrology": fragment,
        "provenance": {
            "image": meas.get("image"),
            "calibration": calib.get("provenance"),
            "annotated_preview_png": os.path.abspath(preview_path),
            "measurements_source": "scripts/measure_features.py output (threshold-based "
                                   "segmentation + agent-marked segments)",
            "stated_magnification_policy": "stated magnification, if any, is metadata "
                                           "only and was NOT used for any measurement",
        },
        "uncertainty": {
            "calibration_relative": u_rel,
            "rule": ("lengths carry x1 the bar relative uncertainty "
                     "(endpoint_unc/length_px); areas carry x2; marked segments add "
                     "±1.5 px per endpoint in quadrature; mean diameters additionally "
                     "report the sample sd and sem"),
            "mean_diameter_calibration_unc": (summary.get("mean_diameter") or {}).get("calibration_unc"),
        },
        "status_suggestion": "success" if has_meas else "partial",
        "notes": ([caption,
                   "INSPECT the annotated preview before trusting counts/sizes; "
                   "threshold-based sizing is not semantic segmentation."]
                  + ([] if has_meas else
                     ["no objects or segments measured -- keep status 'partial'"])),
    }


def main():
    ap = argparse.ArgumentParser(description="Assemble annotated preview + result fragment.")
    ap.add_argument("--image", required=True)
    ap.add_argument("--measurements", required=True, help="measurements.json from measure_features.py")
    ap.add_argument("--out", required=True, help="output directory (usually /app/output)")
    args = ap.parse_args()

    try:
        os.makedirs(args.out, exist_ok=True)
        if not os.path.isfile(args.image):
            print("ERROR: image not found: %s" % args.image, file=sys.stderr)
            return 1
        with open(args.measurements, "r", encoding="utf-8") as f:
            meas = json.load(f)

        preview_path, caption = render_preview(args.image, meas, args.out)
        fragment = build_fragment(meas, preview_path, caption)
        frag_path = os.path.join(args.out, "result_fragment.json")
        with open(frag_path, "w", encoding="utf-8") as f:
            json.dump(fragment, f, indent=2, ensure_ascii=False)
        print("Wrote %s" % preview_path)
        print("Wrote %s" % frag_path)
        print("  %s" % caption)
        print("  status_suggestion: %s" % fragment["status_suggestion"])
        if fragment["status_suggestion"] != "success":
            return 2
        return 0
    except Exception as exc:  # noqa: BLE001
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
