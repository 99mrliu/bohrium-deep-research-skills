#!/usr/bin/env python3
"""render_preview.py — P3: deck -> PDF (soffice headless) -> per-slide PNGs (pdftoppm).

Locates soffice via $SOFFICE_PATH, PATH, then common install locations. Uses an
isolated LibreOffice user profile so headless runs never collide. If soffice is
unavailable, writes render_manifest.json with status "renderer_unavailable" and
exits 0 — the agent MUST disclose this in result.json (uncertainty list) and
rely on validate_output.py as the fallback integrity check.

Usage:
  python3 render_preview.py --deck /app/output/deck.pptx --outdir /app/output/preview \
      [--manifest /app/output/render_manifest.json] [--dpi 150]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

SOFFICE_CANDIDATES = [
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/opt/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
]


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_tool(names, env_var=None, extra=()):
    if env_var and os.environ.get(env_var):
        p = os.environ[env_var]
        if os.path.exists(p):
            return p
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for p in extra:
        if os.path.exists(p):
            return p
    return None


def version_of(cmd, flag="--version"):
    try:
        r = subprocess.run([cmd, flag], capture_output=True, text=True, timeout=30)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return out[0] if out else "unknown"
    except Exception as e:
        return "unavailable (%s)" % e


def font_summary():
    fc = shutil.which("fc-list")
    if not fc:
        return {"fc_list": "unavailable"}
    try:
        r = subprocess.run([fc, ":", "family"], capture_output=True, text=True, timeout=30)
        fams = sorted({ln.strip().split(",")[0] for ln in r.stdout.splitlines() if ln.strip()})
        return {"fc_list": "ok", "font_family_count": len(fams),
                "sample_families": fams[:20]}
    except Exception as e:
        return {"fc_list": "error (%s)" % e}


def count_slides(deck):
    import zipfile, re
    with zipfile.ZipFile(deck) as z:
        return len([n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render deck to PDF + per-slide PNG previews")
    ap.add_argument("--deck", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--manifest", default=None,
                    help="default: <deck-dir>/render_manifest.json")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args(argv)

    manifest_path = args.manifest or os.path.join(os.path.dirname(os.path.abspath(args.deck)),
                                                  "render_manifest.json")
    manifest = {"deck": os.path.abspath(args.deck), "preview_dir": os.path.abspath(args.outdir),
                "generated_at": utcnow(), "dpi": args.dpi, "status": "pending"}

    if not os.path.exists(args.deck):
        sys.stderr.write("ERROR: deck not found: %s\n" % args.deck)
        return 2
    try:
        manifest["slide_count"] = count_slides(args.deck)
    except Exception as e:
        sys.stderr.write("ERROR: deck unreadable: %s\n" % e)
        return 2

    soffice = find_tool(["soffice", "libreoffice"], "SOFFICE_PATH", SOFFICE_CANDIDATES)
    manifest["tools"] = {"soffice": soffice or "not found"}
    if not soffice:
        manifest["status"] = "renderer_unavailable"
        manifest["message"] = ("soffice/LibreOffice not found; deck was NOT render-verified. "
                               "Disclose this in result.json uncertainty; validate_output.py "
                               "remains the structural integrity check.")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print("renderer_unavailable — manifest written to", manifest_path)
        print("DISCLOSE in result.json: no render verification performed.")
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    manifest["tools"]["soffice_version"] = version_of(soffice)
    pdftoppm = find_tool(["pdftoppm"], "PDFTOPPM_PATH")
    manifest["tools"]["pdftoppm"] = pdftoppm or "not found"
    if pdftoppm:
        manifest["tools"]["pdftoppm_version"] = version_of(pdftoppm, "-v")
    manifest["fonts"] = font_summary()

    tmp = tempfile.mkdtemp(prefix="render_")
    profile = tempfile.mkdtemp(prefix="loprofile_")
    try:
        cmd = [soffice, "--headless", "--norestore", "--nologo",
               "-env:UserInstallation=file://" + profile,
               "--convert-to", "pdf", "--outdir", tmp, args.deck]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        pdfs = [f for f in os.listdir(tmp) if f.lower().endswith(".pdf")]
        if r.returncode != 0 or not pdfs:
            manifest["status"] = "render_failed"
            manifest["message"] = (r.stderr or r.stdout or "soffice produced no PDF")[:500]
        else:
            pdf = os.path.join(tmp, pdfs[0])
            kept_pdf = os.path.join(args.outdir, "deck.pdf")
            shutil.copy(pdf, kept_pdf)
            manifest["pdf"] = os.path.abspath(kept_pdf)
            if pdftoppm:
                prefix = os.path.join(args.outdir, "slide")
                r2 = subprocess.run([pdftoppm, "-png", "-r", str(args.dpi), pdf, prefix],
                                    capture_output=True, text=True, timeout=300)
                if r2.returncode != 0:
                    manifest["status"] = "render_failed"
                    manifest["message"] = ("pdftoppm: " + (r2.stderr or ""))[:500]
                else:
                    pngs = sorted(f for f in os.listdir(args.outdir) if f.endswith(".png"))
                    manifest["status"] = "ok"
                    manifest["png_count"] = len(pngs)
                    manifest["pngs"] = pngs
            else:
                manifest["status"] = "ok"
                manifest["message"] = "pdftoppm missing; PDF preview only (no PNGs)"
    except subprocess.TimeoutExpired:
        manifest["status"] = "render_failed"
        manifest["message"] = "soffice timed out"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(profile, ignore_errors=True)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("render status:", manifest["status"], "->", manifest_path)
    if manifest["status"] == "ok":
        print("  previews in", args.outdir)
    else:
        print("  message:", manifest.get("message", ""))
    return 0 if manifest["status"] in ("ok", "renderer_unavailable") else 1


if __name__ == "__main__":
    sys.exit(main())
