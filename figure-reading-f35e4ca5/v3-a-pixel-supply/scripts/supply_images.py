#!/usr/bin/env python3
"""supply_images.py — pixel-supply triage for scientific figure reading.

Inventories case materials, locates the ONE original figure image (rendering
PDF-shipped figures with pdftoppm when needed), computes per-image quality
metrics, and writes image_supply.json. Pure stdlib + numpy + PIL; optional
poppler tools. No network, no ML, no OCR.

Exit codes: 0 ok / 2 degraded-partial / 1 fatal.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
TABLE_EXTS = {".csv", ".tsv", ".xlsx", ".xls"}
TEXT_EXTS = {".md", ".txt", ".json"}
PDF_RENDER_DPI = 400

# Triage thresholds (keep in sync with references/image_quality.md)
DPI_EQUIV_LOW = 150.0          # below this dpi-equivalent -> low_resolution
VERY_LOW_MP = 0.1
LOW_MP = 0.5
HIGH_MP = 2.0
OVEREXPOSE_FRAC = 0.20         # fraction of pixels > 250 luminance
UNDEREXPOSE_FRAC = 0.60        # fraction of pixels < 5 luminance
LOW_CONTRAST_SPREAD = 40.0     # p95 - p5 below this -> low_contrast
BLUR_PROXY_MIN = 30.0          # gradient-magnitude variance below this -> blurry
ASSUMED_FIGURE_WIDTH_IN = 6.5  # heuristic for dpi-equivalent estimate


def find_case_json(input_dir):
    path = os.path.join(input_dir, "case.json")
    if os.path.isfile(path):
        return path
    for root, _dirs, files in os.walk(input_dir):
        for f in files:
            if f == "case.json":
                return os.path.join(root, f)
    return None


def load_materials(input_dir):
    """Return (case_id, list of absolute material paths)."""
    materials = []
    case_id = None
    cj = find_case_json(input_dir)
    if cj:
        try:
            with open(cj, "r", encoding="utf-8") as fh:
                case = json.load(fh)
            case_id = case.get("case_id")
            for m in case.get("materials", []) or []:
                mpath = m if isinstance(m, str) else (
                    m.get("path") or m.get("file") or m.get("filename") or "")
                if not mpath:
                    continue
                if not os.path.isabs(mpath):
                    mpath = os.path.join(input_dir, mpath)
                if os.path.isfile(mpath):
                    materials.append(os.path.normpath(mpath))
        except Exception as exc:  # case.json unreadable: fall back to scan
            print(f"warning: could not parse case.json ({exc}); scanning dir",
                  file=sys.stderr)
    if not materials:
        for root, _dirs, files in os.walk(input_dir):
            for f in sorted(files):
                p = os.path.join(root, f)
                if os.path.normpath(p) == (cj or ""):
                    continue
                materials.append(os.path.normpath(p))
    return case_id, materials


def classify(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in TABLE_EXTS:
        return "table"
    if ext in TEXT_EXTS:
        return "text"
    return "other"


def render_pdf(pdf_path, work_dir, degraded):
    """Render a PDF to PNGs with pdftoppm; returns list of PNG paths."""
    exe = shutil.which("pdftoppm")
    if not exe:
        degraded.append("pdftoppm_missing")
        print("warning: pdftoppm not found; cannot render PDF figure",
              file=sys.stderr)
        return []
    os.makedirs(work_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    prefix = os.path.join(work_dir, f"pdfrender_{stem}")
    try:
        subprocess.run(
            [exe, "-png", "-r", str(PDF_RENDER_DPI), pdf_path, prefix],
            check=True, capture_output=True, timeout=300)
    except Exception as exc:
        degraded.append("pdftoppm_failed")
        print(f"warning: pdftoppm failed on {pdf_path}: {exc}", file=sys.stderr)
        return []
    outs = sorted(p for p in os.listdir(work_dir)
                  if p.startswith(f"pdfrender_{stem}") and p.endswith(".png"))
    return [os.path.join(work_dir, o) for o in outs]


def luminance(arr):
    """arr: HxWx3 uint8 -> HxW float luminance (Rec. 601)."""
    a = arr.astype(np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def image_metrics(path):
    """Quality triage metrics for one image. Returns (metrics, verdicts)."""
    with Image.open(path) as im:
        rgb = np.asarray(im.convert("RGB"))
    h, w = rgb.shape[:2]
    lum = luminance(rgb)
    mp = (w * h) / 1e6
    if mp >= HIGH_MP:
        res_class = "high"
    elif mp >= LOW_MP:
        res_class = "medium"
    elif mp >= VERY_LOW_MP:
        res_class = "low"
    else:
        res_class = "very_low"

    flat = lum.ravel()
    sample = flat if flat.size <= 2_000_000 else flat[::flat.size // 2_000_000]
    p5, p95 = np.percentile(sample, [5, 95])
    over_frac = float(np.mean(sample > 250.0))
    under_frac = float(np.mean(sample < 5.0))

    # Background estimate: median luminance of the outer 5-px frame. Line-art
    # figures have white backgrounds; a high clipped fraction then is normal
    # and must NOT raise an overexposure verdict (same for dark backgrounds).
    frame = np.concatenate([lum[:5].ravel(), lum[-5:].ravel(),
                            lum[:, :5].ravel(), lum[:, -5:].ravel()])
    border_median = float(np.median(frame))

    gy, gx = np.gradient(lum)
    mag = np.hypot(gx, gy)
    blur_proxy = float(np.var(mag))

    dpi_equiv = w / ASSUMED_FIGURE_WIDTH_IN

    metrics = {
        "width": int(w),
        "height": int(h),
        "megapixels": round(mp, 3),
        "resolution_class": res_class,
        "dpi_equivalent_estimate": round(dpi_equiv, 1),
        "luminance_mean": round(float(np.mean(sample)), 2),
        "luminance_std": round(float(np.std(sample)), 2),
        "overexposed_fraction": round(over_frac, 4),
        "underexposed_fraction": round(under_frac, 4),
        "border_median_luminance": round(border_median, 2),
        "blur_proxy": round(blur_proxy, 2),
        "contrast_spread": round(float(p95 - p5), 2),
    }
    verdicts = []
    if dpi_equiv < DPI_EQUIV_LOW or res_class in ("low", "very_low"):
        verdicts.append("low_resolution")
    if min(w, h) < 200:
        verdicts.append("tiny_dimension")
    if over_frac > 0.95:
        verdicts.append("mostly_blank")
    elif border_median <= 250.0 and over_frac > OVEREXPOSE_FRAC:
        # photo-like background with large clipped highlight regions
        verdicts.append("overexposed")
    if under_frac > 0.95:
        verdicts.append("mostly_blank")
    elif border_median >= 5.0 and under_frac > UNDEREXPOSE_FRAC:
        verdicts.append("underexposed")
    if (p95 - p5) < LOW_CONTRAST_SPREAD:
        verdicts.append("low_contrast")
    if blur_proxy < BLUR_PROXY_MIN:
        verdicts.append("blurry")
    if h > w * 1.8:
        # tall-and-narrow: possibly a rotated landscape figure; flag only
        verdicts.append("possibly_rotated")
    if not verdicts:
        verdicts.append("ok")
    return metrics, verdicts


def main():
    ap = argparse.ArgumentParser(description="Pixel-supply triage for figures.")
    ap.add_argument("--input-dir", required=True, help="case dir with case.json and materials")
    ap.add_argument("--work", required=True, help="work dir (PDF renders land here)")
    ap.add_argument("--out", required=True, help="output dir for image_supply.json")
    args = ap.parse_args()

    degraded, warnings = [], []
    fatal = None

    if not os.path.isdir(args.input_dir):
        print(json.dumps({"fatal": f"input dir not found: {args.input_dir}"}))
        return 1
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    case_id, materials = load_materials(args.input_dir)
    inventory = [{"path": p, "kind": classify(p)} for p in materials]

    figure_candidates = []
    for item in inventory:
        if item["kind"] == "image":
            figure_candidates.append({"path": item["path"], "source": "direct"})
        elif item["kind"] == "pdf":
            for png in render_pdf(item["path"], args.work, degraded):
                figure_candidates.append({"path": png, "source": "pdf_render",
                                          "rendered_from": item["path"]})

    images, verdicts = {}, {}
    for cand in figure_candidates:
        try:
            m, v = image_metrics(cand["path"])
        except Exception as exc:
            warnings.append(f"unreadable image {cand['path']}: {exc}")
            continue
        images[cand["path"]] = m
        verdicts[cand["path"]] = v

    if not figure_candidates:
        degraded.append("no_image_materials")
    if not images and figure_candidates:
        fatal = "all candidate images unreadable"

    # Figures mentioned in text but shipped without pixels: declared gaps.
    declared_gaps = []
    cj = find_case_json(args.input_dir)
    if cj:
        try:
            with open(cj, "r", encoding="utf-8") as fh:
                case = json.load(fh)
            for g in case.get("declared_gaps", []) or []:
                declared_gaps.append(g)
        except Exception:
            pass

    report = {
        "case_id": case_id,
        "input_dir": os.path.abspath(args.input_dir),
        "inventory": inventory,
        "figure_candidates": figure_candidates,
        "images": images,
        "verdicts": verdicts,
        "declared_gaps": declared_gaps,
        "degraded": sorted(set(degraded)),
        "warnings": warnings,
        "fatal": fatal,
    }
    out_path = os.path.join(args.out, "image_supply.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    summary = {
        "image_supply": out_path,
        "n_materials": len(inventory),
        "n_figure_candidates": len(figure_candidates),
        "verdicts": {os.path.basename(k): v for k, v in verdicts.items()},
        "degraded": report["degraded"],
        "fatal": fatal,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if fatal:
        return 1
    if not figure_candidates:
        return 1
    if degraded or warnings:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
