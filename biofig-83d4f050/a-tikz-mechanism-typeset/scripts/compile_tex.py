#!/usr/bin/env python3
"""compile_tex.py -- compile a TikZ/pgfplots .tex file to PDF with the best
available LaTeX engine, parse the .log for errors with line numbers, and print
a JSON report.

Usage:
    python3 compile_tex.py --tex FILE --workdir DIR [--engine NAME] [--passes 2]

Engine auto-detection order: latexmk, pdflatex, xelatex (shutil.which).
Missing engine -> honest JSON {"success": false, "error": "no latex engine"},
exit code 3.
Exit codes: 0 success, 1 compile errors, 2 bad args, 3 no engine, 4 other.
Only Python 3 standard library is used.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

ENGINE_ORDER = ["latexmk", "pdflatex", "xelatex"]


def detect_engine(preferred=None):
    """Return (engine_name, engine_path) or (None, None)."""
    candidates = [preferred] if preferred else ENGINE_ORDER
    for name in candidates:
        path = shutil.which(name)
        if path:
            return name, path
    return None, None


def build_command(engine, engine_path, tex_file, passes):
    if engine == "latexmk":
        # latexmk decides passes itself; -pdf uses pdflatex backend.
        return [engine_path, "-pdf", "-interaction=nonstopmode",
                "-halt-on-error", tex_file]
    cmd = [engine_path, "-interaction=nonstopmode", "-halt-on-error", tex_file]
    return [cmd] * max(1, passes)  # list of identical commands (reruns)


def parse_log(log_path):
    """Extract errors with line numbers from a TeX .log file.

    Returns list of {"line": int|None, "message": str}.
    Strategy: find lines starting with "!", then scan forward for "l.<n>".
    Also catch "Emergency stop", "Undefined control sequence" context and
    file-not-found errors.
    """
    errors = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return [{"line": None, "message": "could not read log file: %s" % log_path}]

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("!"):
            message = line.lstrip("! ").rstrip()
            lineno = None
            # scan next few lines for "l.<number> ..."
            for j in range(i, min(i + 8, len(lines))):
                m = re.search(r"^l\.(\d+)", lines[j])
                if m:
                    lineno = int(m.group(1))
                    extra = lines[j].rstrip()
                    if extra and extra not in message:
                        message = message + " | " + extra
                    break
            errors.append({"line": lineno, "message": message})
        i += 1

    # Fallbacks for failures that leave no "!" line nearby.
    if not errors:
        for pat, msg in [
            (r"Emergency stop", "Emergency stop (fatal TeX error, see log)"),
            (r"! LaTeX Error: File `([^']+)' not found",
             "missing file/package"),
        ]:
            if re.search(pat, "".join(lines)):
                errors.append({"line": None, "message": msg})
                break
    return errors


def main():
    ap = argparse.ArgumentParser(description="Compile .tex to PDF, JSON report.")
    ap.add_argument("--tex", required=True, help="path to .tex file")
    ap.add_argument("--workdir", required=True, help="build directory (aux/log/pdf go here)")
    ap.add_argument("--engine", default=None,
                    help="force engine: latexmk|pdflatex|xelatex (default: auto)")
    ap.add_argument("--passes", type=int, default=2,
                    help="compile passes for pdflatex/xelatex (default 2, for pgfplots refs)")
    args = ap.parse_args()

    tex_path = os.path.abspath(args.tex)
    if not os.path.isfile(tex_path):
        print(json.dumps({"success": False, "error": "tex file not found: %s" % tex_path}))
        return 2
    os.makedirs(args.workdir, exist_ok=True)

    engine, engine_path = detect_engine(args.engine)
    if engine is None:
        print(json.dumps({
            "success": False,
            "error": "no latex engine",
            "detail": ("none of %s found on PATH; cannot compile. "
                       "Keep the .tex source as the editable deliverable and "
                       "record this in exceptions." % "/".join(
                           [args.engine] if args.engine else ENGINE_ORDER)),
            "engine": None, "errors": [], "pdf_path": None,
        }))
        return 3

    env = dict(os.environ)
    # Keep texlive non-interactive and reproducible.
    env.setdefault("max_print_line", "1000")

    runs = build_command(engine, engine_path, tex_path, args.passes)
    if runs and isinstance(runs[0], list):
        commands = runs  # pdflatex/xelatex: multiple passes
    else:
        commands = [runs]  # latexmk: single invocation

    last = None
    for cmd in commands:
        try:
            last = subprocess.run(
                cmd, cwd=args.workdir, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=180, text=True, errors="replace")
        except subprocess.TimeoutExpired:
            print(json.dumps({"success": False, "engine": engine,
                              "error": "compile timed out (180s)",
                              "errors": [], "pdf_path": None}))
            return 4

    base = os.path.splitext(os.path.basename(tex_path))[0]
    pdf_path = os.path.join(args.workdir, base + ".pdf")
    log_path = os.path.join(args.workdir, base + ".log")

    errors = parse_log(log_path) if os.path.isfile(log_path) else []
    ok = os.path.isfile(pdf_path) and last is not None and last.returncode == 0 \
        and not errors
    # A PDF that exists despite nonzero rc (halt-on-error after shipping pages)
    # is still reported, but success stays false and errors are listed.
    report = {
        "engine": engine,
        "success": bool(ok),
        "errors": errors,
        "pdf_path": os.path.abspath(pdf_path) if os.path.isfile(pdf_path) else None,
        "log_path": os.path.abspath(log_path) if os.path.isfile(log_path) else None,
        "returncode": last.returncode if last else None,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
