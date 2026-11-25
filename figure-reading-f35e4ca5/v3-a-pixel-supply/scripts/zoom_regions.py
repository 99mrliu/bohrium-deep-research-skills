#!/usr/bin/env python3
"""zoom_regions.py — high-resolution zoom tiles of tick/legend/label regions.

For each panel listed in panels.json (from tile_panels.py), emits contrast-
normalized zoom tiles in ORIGINAL-image coordinates:

  - left_axis   : left 25% of the panel     (upscaled ~4x)
  - bottom_axis : bottom 15% of the panel   (upscaled ~4x)
  - legend_zone : top-right quadrant        (upscaled ~3x)
  - title_strip : top 12% of the panel      (upscaled ~3x)

Every tile is percentile-stretch contrast-normalized (p2..p98) so faint tick
labels stay legible. zoom_manifest.json maps tile -> {panel, region,
bbox_original, scale}. Scale is relative to the ORIGINAL image, so
orig_xy = bbox_original[:2] + tile_xy / scale.

Exit codes: 0 ok / 2 degraded-partial / 1 fatal.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

# region name -> (x0f, y0f, x1f, y1f) as fractions of the panel bbox.
# left_axis is 25% (wider than a nominal 18% strip) because log-axis tick
# labels with exponents ("3×10⁻¹") overflow an 18% strip and get clipped.
REGIONS = {
    "left_axis":   (0.00, 0.00, 0.25, 1.00),
    "bottom_axis": (0.00, 0.85, 1.00, 1.00),
    "legend_zone": (0.50, 0.00, 1.00, 0.50),
    "title_strip": (0.00, 0.00, 1.00, 0.12),
}
REGION_SCALE = {"left_axis": 4, "bottom_axis": 4, "legend_zone": 3,
                "title_strip": 3}
STRETCH_LO, STRETCH_HI = 2.0, 98.0


def contrast_stretch(pil_img):
    """Percentile-stretch normalization on luminance, per RGB image."""
    arr = np.asarray(pil_img.convert("RGB")).astype(np.float64)
    lo, hi = np.percentile(arr, [STRETCH_LO, STRETCH_HI])
    if hi - lo < 1.0:
        return pil_img.convert("RGB")
    out = np.clip((arr - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def main():
    ap = argparse.ArgumentParser(description="Emit zoom tiles for panels.")
    ap.add_argument("--image", required=True, help="original figure image")
    ap.add_argument("--panels", required=True, help="panels.json from tile_panels.py")
    ap.add_argument("--out", required=True, help="output dir for tiles + zoom_manifest.json")
    args = ap.parse_args()

    if not os.path.isfile(args.image):
        print(json.dumps({"fatal": f"image not found: {args.image}"}))
        return 1
    if not os.path.isfile(args.panels):
        print(json.dumps({"fatal": f"panels.json not found: {args.panels}"}))
        return 1
    os.makedirs(args.out, exist_ok=True)

    try:
        rgb = Image.open(args.image).convert("RGB")
    except Exception as exc:
        print(json.dumps({"fatal": f"cannot open image: {exc}"}))
        return 1
    with open(args.panels, "r", encoding="utf-8") as fh:
        panels_doc = json.load(fh)

    warnings = []
    tiles = {}
    W, H = rgb.size
    for panel in panels_doc.get("panels", []):
        pid = panel["panel_id"]
        x0, y0, x1, y1 = panel["bbox_original"]
        pw, ph = x1 - x0, y1 - y0
        if pw <= 0 or ph <= 0:
            warnings.append(f"{pid}: degenerate bbox, skipped")
            continue
        for region, (fx0, fy0, fx1, fy1) in REGIONS.items():
            rx0 = int(round(x0 + fx0 * pw)); ry0 = int(round(y0 + fy0 * ph))
            rx1 = int(round(x0 + fx1 * pw)); ry1 = int(round(y0 + fy1 * ph))
            rx0 = max(0, min(rx0, W)); rx1 = max(0, min(rx1, W))
            ry0 = max(0, min(ry0, H)); ry1 = max(0, min(ry1, H))
            if rx1 - rx0 < 4 or ry1 - ry0 < 4:
                warnings.append(f"{pid}/{region}: region too small, skipped")
                continue
            crop = rgb.crop((rx0, ry0, rx1, ry1))
            scale = REGION_SCALE[region]
            crop = crop.resize((crop.width * scale, crop.height * scale),
                               Image.LANCZOS)
            crop = contrast_stretch(crop)
            name = f"{pid}_{region}.png"
            crop.save(os.path.join(args.out, name))
            tiles[name] = {
                "panel": pid,
                "region": region,
                "bbox_original": [rx0, ry0, rx1, ry1],
                "scale": float(scale),
            }

    if not tiles:
        print(json.dumps({"fatal": "no tiles produced"}))
        return 1

    manifest = {
        "image": os.path.abspath(args.image),
        "image_size": [int(W), int(H)],
        "panels_source": os.path.abspath(args.panels),
        "coordinate_note": "orig_xy = bbox_original[:2] + tile_xy / scale",
        "tiles": tiles,
        "warnings": warnings,
    }
    with open(os.path.join(args.out, "zoom_manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    print(json.dumps({
        "zoom_manifest": os.path.join(args.out, "zoom_manifest.json"),
        "n_tiles": len(tiles),
        "tiles": sorted(tiles),
        "warnings": warnings,
    }, indent=2, ensure_ascii=False))
    return 2 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
