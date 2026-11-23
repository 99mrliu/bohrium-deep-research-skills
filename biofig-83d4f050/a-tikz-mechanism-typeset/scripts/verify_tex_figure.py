#!/usr/bin/env python3
"""verify_tex_figure.py -- programmatic verification of a compiled/exported
TikZ figure. Prints JSON {"checks": [{"name", "status", "detail"}]}.

Usage:
    python3 verify_tex_figure.py --pdf FILE --png FILE \
        --labels-file FILE.json [--legend-colors FILE.json]

Checks:
  (a) fonts_embedded : run pdffonts; every font must say "yes" in the emb
      column. If pdffonts is missing -> status "skipped" with a note (never
      a silent pass).
  (b) labels_present : run pdftotext; each expected label string must appear
      in the extracted text. Missing ones are listed. If pdftotext missing
      -> "skipped".
  (c) pixel_probe    : with PIL (optional): PNG opens, is non-empty, and the
      probe grid contains >=2 distinct colors (i.e. not a blank canvas).
      Without PIL -> "skipped" with note.
  (d) legend_color_match (optional, needs --legend-colors json of the form
      {"swatch_xy": [[x,y],...], "expected_rgb": [r,g,b], "tolerance": 30}):
      mean color at swatch coordinates vs expected RGB.

labels-file format: ["IL-6", "JAK1", "STAT3", ...]
status values: pass | fail | skipped
Exit code: 0 if no check "fail", 1 otherwise, 2 bad args.
Only stdlib + optional PIL.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

try:
    from PIL import Image  # optional
    HAVE_PIL = True
except Exception:
    Image = None
    HAVE_PIL = False


def check(name, status, detail):
    return {"name": name, "status": status, "detail": detail}


def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, text=True, errors="replace")
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)


def check_fonts(pdf):
    if not shutil.which("pdffonts"):
        return check("fonts_embedded", "skipped",
                     "pdffonts not on PATH; font embedding not verified "
                     "(record in exceptions)")
    rc, out = run(["pdffonts", pdf])
    if rc != 0:
        return check("fonts_embedded", "fail", "pdffonts failed: %s" % out[:300])
    lines = [ln for ln in out.splitlines() if ln.strip()]
    # header is 2 lines; data rows follow. "emb" column: find its index.
    unembedded = []
    for ln in lines[2:]:
        parts = ln.split()
        # pdffonts columns: name type encoding emb sub uni object ID
        # name may contain no spaces in practice from tikz/latin modern; be
        # defensive and search for the yes/no triple.
        yesno = [t for t in parts if t in ("yes", "no")]
        if yesno and yesno[0] == "no":
            unembedded.append(parts[0])
    if unembedded:
        return check("fonts_embedded", "fail",
                     "unembedded fonts: %s" % ", ".join(unembedded))
    n = max(0, len(lines) - 2)
    return check("fonts_embedded", "pass",
                 "all %d fonts embedded (pdffonts)" % n)


def normalize(text):
    return " ".join(text.split())


def check_labels(pdf, labels):
    if not shutil.which("pdftotext"):
        return check("labels_present", "skipped",
                     "pdftotext not on PATH; label readback not verified "
                     "(record in exceptions)")
    rc, out = run(["pdftotext", pdf, "-"])
    if rc != 0:
        return check("labels_present", "fail", "pdftotext failed: %s" % out[:300])
    flat = normalize(out)
    missing = [lb for lb in labels if normalize(lb) not in flat]
    if missing:
        return check("labels_present", "fail",
                     "missing labels in extracted text: %s" % "; ".join(missing))
    return check("labels_present", "pass",
                 "all %d expected labels found via pdftotext" % len(labels))


def check_pixels(png):
    if not HAVE_PIL:
        return check("pixel_probe", "skipped",
                     "PIL not available; pixel probe not run")
    if not os.path.isfile(png):
        return check("pixel_probe", "fail", "png not found: %s" % png)
    try:
        with Image.open(png) as im:
            im = im.convert("RGB")
            w, h = im.size
            if w == 0 or h == 0:
                return check("pixel_probe", "fail", "image has zero size")
            # probe a coarse grid, count distinct colors
            step_x, step_y = max(1, w // 40), max(1, h // 40)
            colors = set()
            for x in range(0, w, step_x):
                for y in range(0, h, step_y):
                    colors.add(im.getpixel((x, y)))
            nonwhite = [c for c in colors if c != (255, 255, 255)]
            if len(colors) < 2 or not nonwhite:
                return check("pixel_probe", "fail",
                             "image appears blank: %d distinct probe colors" % len(colors))
            return check("pixel_probe", "pass",
                         "%dx%d px, %d distinct probe colors, %d non-white"
                         % (w, h, len(colors), len(nonwhite)))
    except Exception as exc:
        return check("pixel_probe", "fail", "PIL error: %s" % exc)


def check_legend_colors(png, spec):
    if not HAVE_PIL:
        return check("legend_color_match", "skipped", "PIL not available")
    if not os.path.isfile(png):
        return check("legend_color_match", "fail", "png not found: %s" % png)
    try:
        swatches = spec["swatch_xy"]
        expected = tuple(spec["expected_rgb"])
        tol = int(spec.get("tolerance", 30))
    except (KeyError, TypeError, ValueError) as exc:
        return check("legend_color_match", "fail",
                     "bad --legend-colors spec: %s" % exc)
    try:
        with Image.open(png) as im:
            im = im.convert("RGB")
            w, h = im.size
            samples = []
            for xy in swatches:
                x, y = int(xy[0]), int(xy[1])
                if 0 <= x < w and 0 <= y < h:
                    samples.append(im.getpixel((x, y)))
            if not samples:
                return check("legend_color_match", "fail",
                             "all swatch coordinates out of range (%dx%d)" % (w, h))
            mean = tuple(sum(c[i] for c in samples) // len(samples) for i in range(3))
            diff = max(abs(mean[i] - expected[i]) for i in range(3))
            if diff <= tol:
                return check("legend_color_match", "pass",
                             "swatch mean %s within tol %d of expected %s"
                             % (mean, tol, expected))
            return check("legend_color_match", "fail",
                         "swatch mean %s differs from expected %s by %d (> tol %d)"
                         % (mean, expected, diff, tol))
    except Exception as exc:
        return check("legend_color_match", "fail", "PIL error: %s" % exc)


def main():
    ap = argparse.ArgumentParser(description="Verify compiled TikZ figure.")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--png", required=True)
    ap.add_argument("--labels-file", required=True,
                    help="JSON file: list of expected label strings")
    ap.add_argument("--legend-colors", default=None,
                    help="JSON file: {swatch_xy, expected_rgb, tolerance}")
    args = ap.parse_args()

    if not os.path.isfile(args.pdf):
        print(json.dumps({"checks": [check("args", "fail",
                                           "pdf not found: %s" % args.pdf)]}))
        return 2
    try:
        with open(args.labels_file, "r", encoding="utf-8") as fh:
            labels = json.load(fh)
        assert isinstance(labels, list)
    except Exception as exc:
        print(json.dumps({"checks": [check("args", "fail",
                                           "labels-file unreadable: %s" % exc)]}))
        return 2

    checks = [
        check_fonts(args.pdf),
        check_labels(args.pdf, labels),
        check_pixels(args.png),
    ]
    if args.legend_colors:
        try:
            with open(args.legend_colors, "r", encoding="utf-8") as fh:
                spec = json.load(fh)
            checks.append(check_legend_colors(args.png, spec))
        except Exception as exc:
            checks.append(check("legend_color_match", "fail",
                                "legend-colors file unreadable: %s" % exc))

    failed = [c["name"] for c in checks if c["status"] == "fail"]
    print(json.dumps({
        "overall": "fail" if failed else "pass",
        "failed_checks": failed,
        "checks": checks,
    }, ensure_ascii=False, indent=1))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
