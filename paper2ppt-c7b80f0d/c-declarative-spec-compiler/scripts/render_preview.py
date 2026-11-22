#!/usr/bin/env python3
"""render_preview.py -- export a deck to PDF + per-slide PNGs for visual QA.

Pipeline: soffice (LibreOffice, headless, isolated user profile) -> PDF
          -> pdftoppm -> one PNG per slide. Writes render_manifest.json with
          tool versions, font summary (fc-list), timestamps and output files.

Graceful degradation: if soffice (or pdftoppm) is unavailable, a manifest with
status "renderer_unavailable" (or "partial") is written and the script exits 0
so the pipeline can continue; the missing visual QA is disclosed, never hidden.

Pure Python 3 stdlib.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time


def _run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def _version_soffice(soffice):
    rc, out = _run([soffice, "--version"], timeout=60)
    return out.strip().splitlines()[0] if out.strip() else f"unknown (rc={rc})"


def _version_pdftoppm(pdftoppm):
    rc, out = _run([pdftoppm, "-v"], timeout=30)  # prints to stderr
    return out.strip().splitlines()[0] if out.strip() else f"unknown (rc={rc})"


def _font_summary():
    fc = shutil.which("fc-list")
    if not fc:
        return {"fc_list": "unavailable", "family_count": None, "families_sample": []}
    rc, out = _run([fc, ":", "family"], timeout=60)
    fams = sorted({ln.split(",")[0].strip() for ln in out.splitlines() if ln.strip()})
    return {"fc_list": "ok", "family_count": len(fams), "families_sample": fams[:40]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render a .pptx to PDF + per-slide PNGs.")
    ap.add_argument("--deck", required=True, help="input .pptx")
    ap.add_argument("--outdir", default=None, help="preview dir (default: <deckdir>/preview)")
    ap.add_argument("--manifest", default=None, help="render_manifest.json path (default: <outdir>/render_manifest.json)")
    ap.add_argument("--dpi", type=int, default=110, help="PNG rasterization DPI")
    args = ap.parse_args(argv)

    deck = os.path.abspath(args.deck)
    outdir = args.outdir or os.path.join(os.path.dirname(deck), "preview")
    os.makedirs(outdir, exist_ok=True)
    manifest_path = args.manifest or os.path.join(outdir, "render_manifest.json")

    manifest = {"renderer": "render_preview.py 1.0.0",
                "deck": deck, "outdir": os.path.abspath(outdir),
                "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "pending", "notes": [], "versions": {},
                "fonts": _font_summary(), "files": []}

    def finish(status):
        manifest["status"] = status
        manifest["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for f in sorted(os.listdir(outdir)):
            fp = os.path.join(outdir, f)
            if os.path.isfile(fp) and f != os.path.basename(manifest_path):
                manifest["files"].append({"name": f, "bytes": os.path.getsize(fp)})
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, ensure_ascii=False)
        print(f"render_preview: status={status} manifest={manifest_path}")

    if not os.path.isfile(deck):
        manifest["notes"].append(f"deck not found: {deck}")
        finish("error")
        return 1

    soffice = shutil.which("soffice") or shutil.which("libreoffice") \
        or os.environ.get("SOFFICE")
    if not soffice:
        manifest["notes"].append(
            "soffice (office-renderer) not on PATH; PDF/PNG preview skipped. "
            "The .pptx is still delivered; inspect it in PowerPoint/Keynote/WPS. "
            "Disclosed as renderer_unavailable -- not a content failure.")
        finish("renderer_unavailable")
        return 0
    manifest["versions"]["soffice"] = _version_soffice(soffice)

    profile = tempfile.mkdtemp(prefix="lo-profile-")
    try:
        rc, out = _run([soffice, f"-env:UserInstallation=file://{profile}",
                        "--headless", "--norestore", "--convert-to", "pdf",
                        "--outdir", outdir, deck], timeout=420)
        pdf = os.path.join(outdir, os.path.splitext(os.path.basename(deck))[0] + ".pdf")
        if rc != 0 or not os.path.isfile(pdf):
            manifest["notes"].append(f"soffice conversion failed (rc={rc}): {out[:500]}")
            finish("error")
            return 1
    finally:
        shutil.rmtree(profile, ignore_errors=True)

    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        manifest["notes"].append("pdftoppm not on PATH; PDF written but per-slide PNGs skipped")
        finish("partial")
        return 0
    manifest["versions"]["pdftoppm"] = _version_pdftoppm(pdftoppm)
    rc, out = _run([pdftoppm, "-png", "-r", str(args.dpi), pdf,
                    os.path.join(outdir, "slide")], timeout=300)
    if rc != 0:
        manifest["notes"].append(f"pdftoppm failed (rc={rc}): {out[:500]}")
        finish("partial")
        return 0
    pngs = [f for f in os.listdir(outdir) if f.startswith("slide") and f.endswith(".png")]
    manifest["slide_pngs"] = len(pngs)
    finish("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
