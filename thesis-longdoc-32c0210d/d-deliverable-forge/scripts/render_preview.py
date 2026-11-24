#!/usr/bin/env python3
"""render_preview.py — render edited markdown chapters into a REAL preview.

Probe order (first success wins, each attempt has a timeout):
  1. pandoc   (markdown -> PDF directly)
  2. xelatex  (stdlib markdown -> minimal LaTeX, then compile; ctexart first,
               plain article as retry)
  3. soffice  (stdlib markdown -> HTML, then headless LibreOffice -> PDF)

On success: <out-dir>/edited_chapters.pdf plus a first-page
<out-dir>/edited_chapters.png via pdftoppm. Existing previews are listed in
result.json "artifacts" (relative paths).

If NO renderer can produce a PDF: record "renderer_unavailable" in result.json
"limits", list NO preview in "artifacts" — preview files are never fabricated.
Set FORGE_NO_RENDER=1 to skip rendering entirely (deterministic test branch);
the skip is recorded in "limits".

Exit codes: 0 = preview rendered OR skip mode; 1 = no renderer succeeded or no
chapters found (result.json limits updated either way); 2 = bad arguments
(result.json unreadable etc.).
"""
import argparse
import glob
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile

PREVIEW_BASENAME = "edited_chapters"
SOFFICE_FALLBACKS = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/opt/homebrew/bin/soffice",
)


def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def find_renderers():
    """Return [(name, path)] in probe order; only renderers actually present."""
    found = []
    for name in ("pandoc", "xelatex"):
        path = shutil.which(name)
        if path:
            found.append((name, path))
    soffice = shutil.which("soffice")
    if not soffice:
        for cand in SOFFICE_FALLBACKS:
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                soffice = cand
                break
    if soffice:
        found.append(("soffice", soffice))
    return found


# --------------------------------------------------------------------------
# minimal stdlib markdown converters (preview-grade, not publication-grade)
# --------------------------------------------------------------------------
def md_to_html(md_text, title):
    body, in_code, in_list = [], False, False
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append("</code></pre>" if in_code else "<pre><code>")
            in_code = not in_code
            continue
        if in_code:
            body.append(html.escape(line))
            continue
        if stripped.startswith("#"):
            if in_list:
                body.append("</ul>")
                in_list = False
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            body.append("<h%d>%s</h%d>" % (level, html.escape(stripped[level:].strip()), level))
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append("<li>%s</li>" % html.escape(stripped[2:].strip()))
        elif not stripped:
            if in_list:
                body.append("</ul>")
                in_list = False
        else:
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append("<p>%s</p>" % html.escape(stripped))
    if in_list:
        body.append("</ul>")
    if in_code:
        body.append("</code></pre>")
    return ("<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            "<title>%s</title></head><body>\n%s\n</body></html>"
            % (html.escape(title), "\n".join(body)))


_TEX_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
            "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
            "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def _tex_escape(text):
    return "".join(_TEX_ESC.get(ch, ch) for ch in text)


def md_to_tex(md_text, title, documentclass):
    out = [r"\documentclass[12pt]{%s}" % documentclass,
           r"\usepackage[margin=2.5cm]{geometry}",
           r"\setlength{\parindent}{0pt}\setlength{\parskip}{6pt}",
           r"\begin{document}",
           r"\section*{%s}" % _tex_escape(title)]
    in_code = False
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            out.append(r"\end{verbatim}" if in_code else r"\begin{verbatim}")
            in_code = not in_code
            continue
        if in_code:
            out.append(line)
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            cmd = {1: "section", 2: "subsection"}.get(level, "subsubsection")
            out.append(r"\%s*{%s}" % (cmd, _tex_escape(stripped[level:].strip())))
        elif stripped.startswith(("- ", "* ")):
            out.append(r"\begin{itemize}\item %s\end{itemize}" % _tex_escape(stripped[2:].strip()))
        elif stripped:
            out.append(_tex_escape(stripped) + "\n")
    if in_code:
        out.append(r"\end{verbatim}")
    out.append(r"\end{document}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# renderer attempts; each returns (ok, detail)
# --------------------------------------------------------------------------
def run_cmd(cmd, timeout, cwd=None):
    try:
        proc = subprocess.run(cmd, cwd=cwd, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return None, "timeout after %ds" % timeout
    except OSError as e:
        return None, "exec failed: %s" % e


def try_pandoc(path, md_path, pdf_path, timeout, tmp):
    rc, log = run_cmd([path, md_path, "-o", pdf_path, "--standalone"], timeout)
    ok = rc == 0 and os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0
    return ok, ("pandoc rc=%s" % rc) if ok else "pandoc rc=%s: %s" % (rc, log.strip()[-300:])


def try_xelatex(path, md_text, title, pdf_path, timeout, tmp):
    log_tail = ""
    for docclass in ("ctexart", "article"):
        tex_path = os.path.join(tmp, "preview-%s.tex" % docclass)
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(md_to_tex(md_text, title, docclass))
        rc, log = run_cmd([path, "-interaction=nonstopmode", "-halt-on-error",
                           "-output-directory", tmp, tex_path], timeout, cwd=tmp)
        log_tail = "%s rc=%s: %s" % (docclass, rc, log.strip()[-300:])
        made = os.path.join(tmp, "preview-%s.pdf" % docclass)
        if rc == 0 and os.path.isfile(made) and os.path.getsize(made) > 0:
            shutil.copyfile(made, pdf_path)
            return True, "xelatex ok (documentclass=%s)" % docclass
    return False, "xelatex failed: %s" % log_tail


def try_soffice(path, md_text, title, pdf_path, timeout, tmp):
    html_path = os.path.join(tmp, "preview.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(md_to_html(md_text, title))
    profile = os.path.join(tmp, "lo-profile")
    rc, log = run_cmd([path, "--headless", "--norestore",
                       "-env:UserInstallation=file://" + profile,
                       "--convert-to", "pdf", "--outdir", tmp, html_path], timeout, cwd=tmp)
    made = os.path.join(tmp, "preview.pdf")
    ok = rc == 0 and os.path.isfile(made) and os.path.getsize(made) > 0
    if ok:
        shutil.copyfile(made, pdf_path)
    return ok, ("soffice ok" if ok else "soffice rc=%s: %s" % (rc, log.strip()[-300:]))


def make_png(pdf_path, png_path, timeout, tmp):
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return False, "pdftoppm not found; PNG skipped (PDF is still real)"
    prefix = os.path.join(tmp, "page")
    rc, log = run_cmd([pdftoppm, "-png", "-f", "1", "-l", "1", "-r", "110", pdf_path, prefix], timeout)
    pages = sorted(glob.glob(prefix + "-*.png"))
    if rc == 0 and pages and os.path.getsize(pages[0]) > 0:
        shutil.copyfile(pages[0], png_path)
        return True, "pdftoppm ok"
    return False, "pdftoppm rc=%s: %s" % (rc, log.strip()[-200:])


# --------------------------------------------------------------------------
def update_result(result_path, mutate):
    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)
    mutate(result)
    for key in ("limits", "artifacts"):
        if isinstance(result.get(key), list):
            seen, deduped = set(), []
            for item in result[key]:
                marker = json.dumps(item, ensure_ascii=False, sort_keys=True)
                if marker not in seen:
                    seen.add(marker)
                    deduped.append(item)
            result[key] = deduped
    atomic_write_json(result_path, result)


def main():
    ap = argparse.ArgumentParser(description="Render edited chapters into a real PDF/PNG preview.")
    ap.add_argument("--chapters-dir", required=True, help="dir with edited *.md chapters")
    ap.add_argument("--out-dir", required=True, help="preview output dir (e.g. /app/output/preview)")
    ap.add_argument("--result", required=True, help="existing result.json to update (limits/artifacts)")
    ap.add_argument("--report", required=True, help="path to write render_report.json")
    ap.add_argument("--timeout", type=int, default=120, help="per-renderer timeout in seconds")
    ap.add_argument("--title", default="Edited chapters preview", help="preview document title")
    ap.add_argument("--note", default=None, help="optional note copied into the render report")
    args = ap.parse_args()

    try:
        with open(args.result, encoding="utf-8") as f:
            json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print("ERROR: result.json unreadable (%s): %s" % (args.result, e), file=sys.stderr)
        return 2

    os.makedirs(args.out_dir, exist_ok=True)
    report = {"generated_by": "render_preview.py"}
    if args.note:
        report["note"] = args.note

    # ---- deterministic skip branch ------------------------------------------
    if os.environ.get("FORGE_NO_RENDER") == "1":
        report.update({"skipped": True, "reason": "FORGE_NO_RENDER=1",
                       "previews": []})
        atomic_write_json(args.report, report)

        def mutate_skip(result):
            result.setdefault("limits", []).append(
                "render skipped via FORGE_NO_RENDER=1 (deterministic mode); no preview generated, none claimed")
        update_result(args.result, mutate_skip)
        print("render: FORGE_NO_RENDER=1 -> skipped, recorded in limits")
        return 0

    # ---- gather chapters ------------------------------------------------------
    chapter_files = sorted(glob.glob(os.path.join(args.chapters_dir, "*.md")))
    if not chapter_files:
        report.update({"skipped": False, "renderer": None, "previews": [],
                       "attempts": [], "error": "no *.md chapters in %s" % args.chapters_dir})
        atomic_write_json(args.report, report)

        def mutate_noch(result):
            result.setdefault("limits", []).append(
                "render skipped: no chapter markdown found in %s" % args.chapters_dir)
        update_result(args.result, mutate_noch)
        print("render: no chapters found; recorded in limits", file=sys.stderr)
        return 1

    combined = []
    for path in chapter_files:
        with open(path, encoding="utf-8") as f:
            combined.append(f.read())
    md_text = "\n\n".join(combined)

    # ---- probe + attempt renderers in order ----------------------------------
    renderers = find_renderers()
    attempts = [{"renderer": name, "path": path} for name, path in renderers]
    pdf_path = os.path.join(args.out_dir, PREVIEW_BASENAME + ".pdf")
    png_path = os.path.join(args.out_dir, PREVIEW_BASENAME + ".png")
    winner, previews, notes = None, [], []

    with tempfile.TemporaryDirectory(prefix="forge-render-") as tmp:
        md_path = os.path.join(tmp, "combined.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        for name, path in renderers:
            if name == "pandoc":
                ok, detail = try_pandoc(path, md_path, pdf_path, args.timeout, tmp)
            elif name == "xelatex":
                ok, detail = try_xelatex(path, md_text, args.title, pdf_path, args.timeout, tmp)
            else:
                ok, detail = try_soffice(path, md_text, args.title, pdf_path, args.timeout, tmp)
            attempts[renderers.index((name, path))]["ok"] = ok
            attempts[renderers.index((name, path))]["detail"] = detail
            print("render: tried %s -> %s" % (name, detail))
            if ok:
                winner = name
                break
        if winner:
            previews.append(os.path.basename(pdf_path))
            png_ok, png_detail = make_png(pdf_path, png_path, args.timeout, tmp)
            print("render: png -> %s" % png_detail)
            if png_ok:
                previews.append(os.path.basename(png_path))
            else:
                notes.append(png_detail)

    report.update({"skipped": False, "renderer": winner, "attempts": attempts,
                   "chapters": [os.path.basename(p) for p in chapter_files],
                   "previews": ["preview/" + p for p in previews]})
    if notes:
        report["notes"] = notes
    atomic_write_json(args.report, report)

    if winner:
        def mutate_ok(result):
            result.setdefault("artifacts", []).extend("preview/" + p for p in previews)
            for note in notes:
                result.setdefault("limits", []).append(note)
        update_result(args.result, mutate_ok)
        print("render: preview via %s -> %s" % (winner, ", ".join(report["previews"])))
        return 0

    tried = ", ".join(name for name, _ in renderers) or "none found on this machine"
    def mutate_fail(result):
        result.setdefault("limits", []).append(
            "renderer_unavailable: tried pandoc -> xelatex -> soffice (%s); no PDF produced. "
            "No preview listed in artifacts — previews are never fabricated." % tried)
    update_result(args.result, mutate_fail)
    print("render: renderer_unavailable (%s); recorded in limits, no fake preview" % tried,
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
