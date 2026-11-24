#!/usr/bin/env python3
"""render_check.py — 用 LibreOffice 真实渲染最终 deck：PDF + PNG 预览。

用法:
    python3 render_check.py <final.pptx> --out-dir render/ --report render_report.json \
        [--soffice /path/to/soffice] [--profile-key e]

渲染链：soffice --headless --convert-to pdf，再 pdftoppm -png 出逐页预览。
soffice 缺失时 rendered=false + tool_missing 诚实降级（退出码 3），禁止谎报渲染通过。
并发运行务必使用不同 -env:UserInstallation（--profile-key）。
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_common as dc

SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
]


def find_soffice(cli_path: str | None) -> str | None:
    if cli_path and os.path.exists(cli_path):
        return cli_path
    w = shutil.which("soffice")
    if w:
        return w
    for c in SOFFICE_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def pdf_page_count(pdf_path: str) -> int | None:
    try:
        import pymupdf  # type: ignore

        doc = pymupdf.open(pdf_path)
        n = doc.page_count
        doc.close()
        return n
    except ImportError:
        pass
    except Exception:
        return None
    try:
        from pypdf import PdfReader  # type: ignore

        return len(PdfReader(pdf_path).pages)
    except ImportError:
        return None
    except Exception:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="soffice 渲染 pptx -> PDF -> PNG 预览")
    ap.add_argument("deck", help="最终 pptx")
    ap.add_argument("--out-dir", required=True, help="渲染产物目录")
    ap.add_argument("--report", required=True, help="render_report.json")
    ap.add_argument("--soffice", default=None, help="soffice 路径（可选）")
    ap.add_argument("--profile-key", default="e", help="UserInstallation 隔离 key（并发用）")
    ap.add_argument("--dpi", type=int, default=110, help="PNG 渲染分辨率")
    args = ap.parse_args(argv)

    if not os.path.exists(args.deck):
        print(f"error: deck not found: {args.deck}", file=sys.stderr)
        return 2
    os.makedirs(args.out_dir, exist_ok=True)

    soffice = find_soffice(args.soffice)
    pdftoppm = shutil.which("pdftoppm")
    missing = [t for t, p in (("soffice", soffice), ("pdftoppm", pdftoppm)) if not p]
    if missing:
        report = {
            "deck": os.path.abspath(args.deck), "rendered": False,
            "pdf": None, "previews": [], "pages": None,
            "tool_missing": missing, "engine": "tool_missing",
        }
        dc.dump_json(report, args.report)
        print(f"tool_missing: {', '.join(missing)}; rendered=false written to {args.report}",
              file=sys.stderr)
        return 3

    profile = f"-env:UserInstallation=file:///tmp/lo-{args.profile_key}"
    cmd = [soffice, "--headless", profile, "--convert-to", "pdf",
           "--outdir", args.out_dir, args.deck]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    stem = os.path.splitext(os.path.basename(args.deck))[0]
    pdf_path = os.path.join(args.out_dir, stem + ".pdf")
    if proc.returncode != 0 or not os.path.exists(pdf_path):
        report = {
            "deck": os.path.abspath(args.deck), "rendered": False,
            "pdf": None, "previews": [], "pages": None,
            "tool_missing": [], "engine": "soffice",
            "error": (proc.stderr or proc.stdout or "soffice conversion failed").strip()[:500],
        }
        dc.dump_json(report, args.report)
        print(f"error: soffice conversion failed: {report['error']}", file=sys.stderr)
        return 4

    previews = []
    try:
        subprocess.run(
            [pdftoppm, "-png", "-r", str(args.dpi), pdf_path,
             os.path.join(args.out_dir, "preview")],
            capture_output=True, text=True, timeout=600, check=True,
        )
        previews = sorted(
            os.path.abspath(p)
            for p in glob.glob(os.path.join(args.out_dir, "preview-*.png"))
        )
    except (subprocess.SubprocessError, OSError) as e:
        print(f"warning: pdftoppm failed: {e}", file=sys.stderr)

    pages = pdf_page_count(pdf_path)
    if pages is None:
        pages = len(previews) if previews else None
    report = {
        "deck": os.path.abspath(args.deck),
        "rendered": True,
        "engine": f"soffice+pdftoppm(dpi={args.dpi})",
        "pdf": os.path.abspath(pdf_path),
        "previews": previews,
        "pages": pages,
        "tool_missing": [],
    }
    dc.dump_json(report, args.report)
    print(f"render ok: pdf={pdf_path} pages={pages} previews={len(previews)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
