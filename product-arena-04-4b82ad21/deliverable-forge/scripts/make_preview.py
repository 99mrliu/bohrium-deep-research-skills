#!/usr/bin/env python3
"""make_preview.py -- render a real, inspectable preview of the deliverable.

Evaluators must be able to LOOK at the artifact, not only read its source.
This script renders a Markdown manuscript to a PDF preview using the first
available renderer, and is honest when none exists:

  1. pdflatex / xelatex / tectonic (best: typeset PDF)
  2. python3 + matplotlib (basic wrapped-text PDF), if importable
  3. otherwise: a plain-text preview file and status "not_verifiable",
     so the run degrades honestly instead of fabricating a preview.

Usage:
  python3 make_preview.py --md introduction.md --out-dir /app/output [--title T]

Outputs: preview.pdf (renderer 1-2) or preview.txt (renderer 3), plus
preview_report.json recording renderer, status and artifact path.

Exit codes: 0 preview produced, 1 only text fallback possible, 2 usage error.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

PAGE_W = 90  # chars per line for the text fallback


def latex_escape(t):
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                 ("}", r"\}")]:
        t = t.replace(a, b)
    return t


def md_to_tex(md, title):
    out = [r"\documentclass[11pt]{article}", r"\usepackage[margin=1in]{geometry}",
           r"\usepackage[T1]{fontenc}", r"\setlength{\parskip}{6pt}",
           r"\setlength{\parindent}{0pt}", r"\begin{document}"]
    if title:
        out.append(r"\section*{%s}" % latex_escape(title))
    for ln in md.splitlines():
        s = ln.strip()
        if not s:
            out.append("")
            continue
        if s.startswith("### "):
            out.append(r"\subsubsection*{%s}" % latex_escape(s[4:]))
        elif s.startswith("## "):
            out.append(r"\subsection*{%s}" % latex_escape(s[3:]))
        elif s.startswith("# "):
            out.append(r"\section*{%s}" % latex_escape(s[2:]))
        elif s.startswith(("- ", "* ")):
            out.append(r"\begin{itemize}\item %s\end{itemize}" % latex_escape(s[2:]))
        else:
            s = s.replace("**", "").replace("*", "")
            out.append(latex_escape(s))
    out.append(r"\end{document}")
    return "\n".join(out)


def render_latex(md, title, out_pdf):
    tex = md_to_tex(md, title)
    engine = next((e for e in ("pdflatex", "xelatex", "tectonic")
                   if shutil.which(e)), None)
    if not engine:
        return None
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td) / "preview.tex"
        tp.write_text(tex, encoding="utf-8")
        cmd = [engine, "-interaction=nonstopmode", "-halt-on-error", str(tp)]
        if engine == "tectonic":
            cmd = [engine, str(tp)]
        p = subprocess.run(cmd, cwd=td, capture_output=True, text=True, timeout=180)
        produced = Path(td) / "preview.pdf"
        if p.returncode == 0 and produced.is_file():
            out_pdf.write_bytes(produced.read_bytes())
            return engine
    return None


def render_matplotlib(md, title, out_pdf):
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.backends.backend_pdf import PdfPages
        import matplotlib.pyplot as plt
    except Exception:
        return None
    lines = []
    if title:
        lines += [title, "=" * min(len(title), PAGE_W), ""]
    for ln in md.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            lines += ["", s.lstrip("# ").strip(), ""]
        elif s:
            lines += textwrap.wrap(s, PAGE_W) or [""]
        else:
            lines.append("")
    per_page, pages = 46, [lines[i:i + 46] for i in range(0, len(lines), 46)] or [[]]
    with PdfPages(str(out_pdf)) as pdf:
        for chunk in pages:
            fig = plt.figure(figsize=(8.5, 11))
            fig.text(0.08, 0.96, "\n".join(chunk), va="top", ha="left",
                     family="monospace", fontsize=9)
            plt.axis("off")
            pdf.savefig(fig)
            plt.close(fig)
    return "matplotlib"


def render_text(md, title, out_txt):
    lines = ["PREVIEW (plain-text fallback — no PDF renderer available)", ""]
    if title:
        lines += [title, "=" * len(title), ""]
    for ln in md.splitlines():
        s = ln.rstrip()
        lines += textwrap.wrap(s, PAGE_W) if s else [""]
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "plain-text"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--title")
    args = ap.parse_args()
    try:
        md = Path(args.md).read_text(encoding="utf-8")
    except Exception as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf, txt = out / "preview.pdf", out / "preview.txt"
    renderer = render_latex(md, args.title, pdf)
    status, code = "complete", 0
    if renderer is None:
        renderer = render_matplotlib(md, args.title, pdf)
    if renderer is None:
        renderer = render_text(md, args.title, txt)
        status, code = "not_verifiable", 1
    artifact = str(pdf if pdf.is_file() else txt)
    report = {"renderer": renderer, "status": status, "artifact": artifact,
              "note": ("real PDF preview rendered with %s" % renderer) if status == "complete"
                      else "no PDF renderer available; plain-text preview delivered instead"}
    (out / "preview_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("preview: %s via %s -> %s" % (status, renderer, artifact))
    return code


if __name__ == "__main__":
    sys.exit(main())
