#!/usr/bin/env python3
"""Side-by-side comparison sheets: [source evidence | rendered transcription].

When a PDF artifact exists, the referenced page is rasterized with pdftoppm
and paired with the previously rendered PNG. Without a PDF, the sheet pairs
the rendering with a text panel carrying the formula's source reference.
Stdlib + matplotlib.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def rasterize_page(pdf_path, page, work):
    prefix = work / ("page_%d" % page)
    p = subprocess.run(
        ["pdftoppm", "-f", str(page), "-l", str(page), "-r", "130", "-png",
         str(pdf_path), str(prefix)],
        capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        return None, (p.stderr or "pdftoppm failed").strip()[:200]
    hits = sorted(work.glob("page_%d-*.png" % page))
    return (str(hits[0]) if hits else None), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input", default=None)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output/render")
    args = ap.parse_args()
    case_path = Path(args.case)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    input_root = Path(args.input) if args.input else case_path.parent
    work, out = Path(args.work), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    artifacts = (case.get("artifacts") or {})

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
    except ImportError:
        print("matplotlib unavailable; comparison sheets skipped")
        return

    formulas = json.loads((work / "formulas.json").read_text(encoding="utf-8")).get("formulas", [])
    render_report = {}
    rp = work / "render_report.json"
    if rp.exists():
        render_report = json.loads(rp.read_text(encoding="utf-8"))
    rendered = {r["id"]: r["png"] for r in render_report.get("rendered", [])}

    pdf = artifacts.get("pdf")
    pdf_path = input_root / pdf if pdf and (input_root / pdf).exists() else None
    page_png, page_err = (None, "no PDF artifact in case")
    if pdf_path:
        page_png, page_err = rasterize_page(pdf_path, 1, work)

    sheets = []
    for f in formulas:
        fid = f.get("id", "unnamed")
        png = rendered.get(fid)
        if not png or not Path(png).exists():
            continue
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.4))
        if page_png:
            axes[0].imshow(mpimg.imread(page_png))
            axes[0].set_title("source: %s page 1" % (pdf or ""), fontsize=9)
        else:
            axes[0].axis("off")
            axes[0].text(0.02, 0.5,
                         "source evidence\n\n%s\n(%s)" % (f.get("source", "unspecified"),
                                                         page_err),
                         va="center", fontsize=10, family="monospace",
                         bbox=dict(boxstyle="round", fc="#f6f6f6", ec="#999"))
            axes[0].set_title("source reference (no raster)", fontsize=9)
        axes[1].imshow(mpimg.imread(png))
        axes[1].set_title("rendered transcription %s" % fid, fontsize=9)
        for ax in axes:
            ax.axis("off")
        target = out / ("compare_%s.png" % fid)
        fig.suptitle("synthetic review sheet — %s" % fid, fontsize=10)
        fig.tight_layout()
        fig.savefig(target, dpi=140, facecolor="white")
        plt.close(fig)
        sheets.append({"id": fid, "png": str(target), "bytes": target.stat().st_size})
    doc = {"sheets": sheets, "source_page_png": page_png,
           "note": ("page rasterized from provided PDF" if page_png
                    else "no source raster: %s" % page_err)}
    (work / "compare_report.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print("comparison sheets: %d -> %s" % (len(sheets), work / "compare_report.json"))


if __name__ == "__main__":
    main()
