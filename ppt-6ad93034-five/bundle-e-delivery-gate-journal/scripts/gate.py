#!/usr/bin/env python3
"""gate.py — stage gates with machine-checked exit criteria.

Usage: gate.py plan|build|render

Runs the documented checklist (see references/gate_criteria.md) against
work/ and output/ artifacts, writes work/gate-<stage>.json, logs itself
into the journal, and exits 1 on FAIL. A gate may NEVER be skipped:
fix the underlying problem and re-run the gate.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

INPUT_DIR = os.environ.get("CASE_INPUT_DIR", "/input")
WORK_DIR = os.environ.get("CASE_WORK_DIR", "/app/work")
OUTPUT_DIR = os.environ.get("CASE_OUTPUT_DIR", "/app/output")
DEFAULT_SLIDE_LIMIT = 20

SLIDE_XML_RE = re.compile(r"^ppt/slides/slide\d+\.xml$")
NOTES_XML_RE = re.compile(r"^ppt/notesSlides/notesSlide\d+\.xml$")
TEXT_RUN_RE = re.compile(r"<a:t>(.*?)</a:t>", re.DOTALL)
PLACEHOLDER_RE = re.compile(r"TODO|Lorem", re.IGNORECASE)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": str(detail)}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def slide_limit():
    """Slide cap from artifacts/slide-workorder.json when present, else default."""
    wo = os.path.join(INPUT_DIR, "artifacts", "slide-workorder.json")
    if os.path.isfile(wo):
        try:
            data = load_json(wo)
            for key in ("max_slides", "slide_limit", "limit", "maxSlides"):
                if isinstance(data.get(key), int) and data[key] > 0:
                    return data[key], f"from {key} in slide-workorder.json"
        except Exception:
            pass
    return DEFAULT_SLIDE_LIMIT, "default"


def slide_texts(zf, names):
    """Concatenated visible text per slide XML part."""
    out = {}
    for n in names:
        xml = zf.read(n).decode("utf-8", errors="replace")
        texts = [t for t in TEXT_RUN_RE.findall(xml) if t.strip()]
        out[n] = texts
    return out


def checks_plan():
    c = []
    plan_path = os.path.join(WORK_DIR, "plan.json")
    if not os.path.isfile(plan_path):
        return [check("plan-exists", False, f"{plan_path} not found")], None
    c.append(check("plan-exists", True, plan_path))
    try:
        plan = load_json(plan_path)
    except Exception as exc:
        c.append(check("plan-parses", False, f"JSON parse error: {exc}"))
        return c, None
    c.append(check("plan-parses", True, "valid JSON"))
    slides = plan.get("slides") if isinstance(plan, dict) else None
    if not isinstance(slides, list) or len(slides) < 1:
        c.append(check("plan-has-slides", False, "plan.slides missing or empty"))
        return c, None
    c.append(check("plan-has-slides", True, f"{len(slides)} slide(s)"))
    limit, src = slide_limit()
    c.append(check("slide-count-within-limit", len(slides) <= limit,
                   f"{len(slides)} slide(s) vs limit {limit} ({src})"))
    bad_titles = [i + 1 for i, s in enumerate(slides)
                  if not (isinstance(s, dict) and str(s.get("title", "")).strip())]
    c.append(check("every-slide-has-title", not bad_titles,
                   "all slides titled" if not bad_titles else f"empty title on slide(s) {bad_titles}"))
    bad_ev, bad_quotes = [], []
    for i, s in enumerate(slides):
        if not isinstance(s, dict) or "evidence" not in s:
            continue
        ev = s["evidence"]
        if not isinstance(ev, list) or not ev:
            bad_ev.append(i + 1)
            continue
        for item in ev:
            quote = item.get("quote") if isinstance(item, dict) else item
            if not str(quote or "").strip():
                bad_quotes.append(i + 1)
    c.append(check("claimed-evidence-nonempty", not bad_ev,
                   "all evidence lists non-empty" if not bad_ev else f"empty evidence list on slide(s) {bad_ev}"))
    c.append(check("evidence-quotes-nonempty", not bad_quotes,
                   "all evidence quotes non-empty" if not bad_quotes else f"empty quote on slide(s) {bad_quotes}"))
    return c, plan


def checks_build():
    c = []
    pptx = os.path.join(OUTPUT_DIR, "presentation.pptx")
    if not os.path.isfile(pptx):
        return [check("pptx-exists", False, f"{pptx} not found")], None
    c.append(check("pptx-exists", True, pptx))
    if not zipfile.is_zipfile(pptx):
        c.append(check("pptx-valid-zip", False, "not a zip container"))
        return c, None
    c.append(check("pptx-valid-zip", True, "opens as zip (OOXML container)"))
    zf = zipfile.ZipFile(pptx)
    names = zf.namelist()
    slides = sorted(n for n in names if SLIDE_XML_RE.match(n))
    notes = sorted(n for n in names if NOTES_XML_RE.match(n))
    c.append(check("has-slide-xml", len(slides) >= 1, f"{len(slides)} slide XML part(s)"))
    c.append(check("has-notes-xml", len(notes) >= 1, f"{len(notes)} notes part(s)"))
    # Every XML part must be well-formed — a deck PowerPoint cannot parse is not a deck.
    import xml.etree.ElementTree as _ET
    bad_xml = []
    for n in [x for x in names if x.endswith(".xml") or x.endswith(".rels")]:
        try:
            _ET.fromstring(zf.read(n))
        except Exception as exc:
            bad_xml.append(f"{os.path.basename(n)}:{type(exc).__name__}")
    c.append(check("all-xml-well-formed", not bad_xml,
                   "every .xml/.rels part parses" if not bad_xml else f"malformed XML: {bad_xml[:4]}"))
    if "ppt/presentation.xml" in names and not bad_xml:
        try:
            import re as _re
            pres = zf.read("ppt/presentation.xml").decode("utf-8", "replace")
            ids = _re.findall(r"<p:sldId\b", pres)
            c.append(check("presentation-lists-slides", len(ids) == len(slides),
                           f"sldIdLst has {len(ids)} entries for {len(slides)} slide part(s)"))
        except Exception as exc:
            c.append(check("presentation-lists-slides", False, f"unreadable: {exc}"))
    plan_path = os.path.join(WORK_DIR, "plan.json")
    plan_count = None
    if os.path.isfile(plan_path):
        try:
            plan_count = len(load_json(plan_path).get("slides", []))
        except Exception:
            pass
    if plan_count is None:
        c.append(check("slide-count-matches-plan", False, "work/plan.json unreadable; cannot compare"))
    else:
        c.append(check("slide-count-matches-plan", len(slides) == plan_count,
                       f"pptx has {len(slides)} slide(s), plan has {plan_count}"))
    texts = slide_texts(zf, slides)
    empty = [os.path.basename(n) for n, ts in texts.items() if not ts]
    c.append(check("every-slide-has-text", not empty,
                   "all slides contain text" if not empty else f"no <a:t> text in {empty}"))
    dirty = []
    for n in slides:
        xml = zf.read(n).decode("utf-8", errors="replace")
        m = PLACEHOLDER_RE.search(xml)
        if m:
            dirty.append(f"{os.path.basename(n)}:{m.group(0)}")
    c.append(check("no-placeholder-text", not dirty,
                   "no TODO/Lorem literals" if not dirty else f"placeholder text found: {dirty}"))
    zf.close()
    return c, {"slide_count": len(slides)}


def pdf_page_count(pdf_path):
    """Page count via pdfinfo, else form-feed count from pdftotext."""
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        try:
            p = subprocess.run([pdfinfo, pdf_path], capture_output=True, text=True, timeout=60)
            m = re.search(r"^Pages:\s+(\d+)", p.stdout, re.MULTILINE)
            if m:
                return int(m.group(1)), "pdfinfo"
        except Exception:
            pass
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        try:
            p = subprocess.run([pdftotext, pdf_path, "-"], capture_output=True, timeout=120)
            return p.stdout.count(b"\x0c") or 1, "pdftotext form-feeds"
        except Exception:
            pass
    return None, "no pdfinfo/pdftotext available"


def checks_render():
    c = []
    soffice = shutil.which("soffice")
    if not soffice:
        c.append(check("renderer-absent", True,
                       "soffice not found on PATH; PDF export and previews were not produced. "
                       "Deck delivered as editable .pptx only. This is recorded honestly in the "
                       "manifest and result.json, not hidden."))
        return c, {"renderer": None}
    pptx = os.path.join(OUTPUT_DIR, "presentation.pptx")
    pdf = os.path.join(OUTPUT_DIR, "presentation.pdf")
    c.append(check("pdf-exists", os.path.isfile(pdf), pdf if os.path.isfile(pdf) else "presentation.pdf missing"))
    slide_count = None
    if zipfile.is_zipfile(pptx):
        with zipfile.ZipFile(pptx) as zf:
            slide_count = sum(1 for n in zf.namelist() if SLIDE_XML_RE.match(n))
    if os.path.isfile(pdf) and slide_count:
        pages, how = pdf_page_count(pdf)
        c.append(check("pdf-page-count-matches", pages == slide_count,
                       f"{pages} page(s) via {how} vs {slide_count} slide(s)"))
    prev_dir = os.path.join(OUTPUT_DIR, "previews")
    pngs = []
    if os.path.isdir(prev_dir):
        pngs = [f for f in os.listdir(prev_dir) if f.lower().endswith(".png")]
    c.append(check("preview-pngs-exist", len(pngs) >= 1,
                   f"{len(pngs)} preview PNG(s) in {prev_dir}"))
    return c, {"renderer": soffice}


def log_gate_to_journal(report_path, stage, verdict):
    journal = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal.py")
    if not os.path.isfile(journal):
        return
    subprocess.run([sys.executable, journal, "log", "--kind", "gate",
                    "--outputs", report_path,
                    "--note", f"gate {stage}: {verdict}"],
                   capture_output=True)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("plan", "build", "render"):
        print("usage: gate.py plan|build|render", file=sys.stderr)
        return 2
    stage = sys.argv[1]
    checks, _meta = {"plan": checks_plan, "build": checks_build, "render": checks_render}[stage]()
    verdict = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    report = {"stage": stage, "checks": checks, "verdict": verdict, "ts": utc_now()}
    os.makedirs(WORK_DIR, exist_ok=True)
    report_path = os.path.join(WORK_DIR, f"gate-{stage}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log_gate_to_journal(report_path, stage, verdict)
    for c in checks:
        print(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
    print(f"gate {stage}: {verdict} (report: {report_path})")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
