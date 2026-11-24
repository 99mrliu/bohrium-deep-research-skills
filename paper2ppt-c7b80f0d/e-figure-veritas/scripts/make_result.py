#!/usr/bin/env python3
"""make_result.py — 汇总产物并按 case.json 的 output_contract 生成 result.json。

- output_contract 字段名运行时从 case.json 读，不硬编码；缺失字段记入 exceptions。
- 额外字段：uncertainties、change_records（COMMON_SPEC 要求）。
- compliance_checks 的 actual 全部来自真实测量：
    slide_count            python-pptx 实测页数 vs task.md 上限
    export_page_match      渲染 PDF 页数 vs pptx 页数
    placeholder_free       扫描 pptx 全部文本中的占位符/待办提示
    evidence_coverage      内容页含 figure 或 source 的比例
    notes_coverage         含备注页比例（实测 pptx notes）
    figures_in_manifest    binding_report 中 unknown-figure 类 error 数
    redraw_value_drift     redraw_report 的 mismatched_count（容差 0）
    no_schematic_in_results binding_report 中 schematic-in-results 类 error 数
- 渲染：--render 时按 soffice → PDF → pdftoppm → PNG 链真实执行；工具缺失时
  export_artifact.rendered=false 且 exceptions 记 tool_missing，绝不虚报。

退出码：0 正常（即使 status=partial，只要报告如实）；2 输入错误。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

SOFFICE_CANDIDATES = [
    "soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
]
PLACEHOLDER_RE = re.compile(
    r"(?i)(click to add|lorem ipsum|\bTODO\b|\bTBD\b|\{\{[^}]+\}\})")


def find_soffice():
    for cand in SOFFICE_CANDIDATES:
        found = shutil.which(cand) if os.path.basename(cand) == cand else \
            (cand if os.path.isfile(cand) else None)
        if found:
            return found
    return None


def pdf_page_count(pdf_path):
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        n = len(doc)
        doc.close()
        return n
    except ImportError:
        pass
    except Exception:
        return None
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf_path).pages)
    except ImportError:
        return None
    except Exception:
        return None


def render_deck(pptx_path, out_dir, work_key):
    """返回 (pdf_path, previews, exceptions)。"""
    exceptions = []
    soffice = find_soffice()
    if not soffice:
        exceptions.append({"kind": "tool_missing",
                           "detail": "LibreOffice soffice not found; deck not rendered"})
        return None, [], exceptions
    os.makedirs(out_dir, exist_ok=True)
    cmd = [soffice, "--headless", "--norestore",
           f"-env:UserInstallation=file:///tmp/lo-{work_key}",
           "--convert-to", "pdf", "--outdir", out_dir, pptx_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        exceptions.append({"kind": "run_failed",
                           "detail": f"soffice render failed: {exc}"})
        return None, [], exceptions
    pdf_path = os.path.join(out_dir,
                            os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    if proc.returncode != 0 or not os.path.isfile(pdf_path):
        exceptions.append({"kind": "run_failed",
                           "detail": "soffice exited "
                                     f"{proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[:300]}"})
        return None, [], exceptions
    previews = []
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        exceptions.append({"kind": "tool_missing",
                           "detail": "pdftoppm not found; PNG previews not generated"})
    else:
        prefix = os.path.join(out_dir, "preview")
        proc2 = subprocess.run([pdftoppm, "-png", "-r", "100", pdf_path, prefix],
                               capture_output=True, timeout=300)
        if proc2.returncode != 0:
            exceptions.append({"kind": "run_failed",
                               "detail": f"pdftoppm exited {proc2.returncode}"})
        else:
            previews = sorted(glob.glob(prefix + "-*.png"))
    return pdf_path, previews, exceptions


def pptx_measurements(pptx_path):
    """返回 (slide_count, notes_flags, placeholder_hits)；python-pptx 缺失返回 None。"""
    try:
        from pptx import Presentation
    except ImportError:
        return None
    prs = Presentation(pptx_path)
    notes_flags, hits = [], []
    for i, slide in enumerate(prs.slides, start=1):
        try:
            txt = slide.notes_slide.notes_text_frame.text.strip()
        except Exception:
            txt = ""
        notes_flags.append(bool(txt))
        for shape in slide.shapes:
            if shape.has_text_frame:
                for m in PLACEHOLDER_RE.finditer(shape.text_frame.text):
                    hits.append({"slide": i, "hit": m.group(0)})
    return len(prs.slides), notes_flags, hits


def parse_slide_limit(task_md_path):
    if not task_md_path or not os.path.isfile(task_md_path):
        return None
    with open(task_md_path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"(?:≤|<=|at most|no more than)\s*(\d+)\s*slides?", text, re.I)
    return int(m.group(1)) if m else None


def load_json(path, default=None):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def main():
    ap = argparse.ArgumentParser(
        description="Assemble result.json honouring the case.json output_contract.")
    ap.add_argument("--case", required=True, help="case.json")
    ap.add_argument("--task", default=None, help="task.md (slide limit)")
    ap.add_argument("--deck", required=True, help="deck.json")
    ap.add_argument("--pptx", required=True, help="built presentation.pptx")
    ap.add_argument("--binding-report", default=None)
    ap.add_argument("--redraw-report", default=None)
    ap.add_argument("--classify-report", default=None)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--render", action="store_true",
                    help="render pptx -> PDF + PNG previews via soffice/pdftoppm")
    ap.add_argument("--render-dir", default=None, help="where to put PDF/previews")
    ap.add_argument("--work-key", default="b", help="LibreOffice profile suffix")
    ap.add_argument("--out", required=True, help="result.json path")
    args = ap.parse_args()

    case = load_json(args.case)
    deck = load_json(args.deck)
    if case is None or deck is None:
        sys.stderr.write("error: case.json or deck.json unreadable\n")
        return 2
    contract = case.get("output_contract", [])
    exceptions, uncertainties = [], []

    binding = load_json(args.binding_report, {})
    redraw = load_json(args.redraw_report, {})
    classify = load_json(args.classify_report, {})

    # ---- 渲染 ----
    render_dir = args.render_dir or os.path.dirname(os.path.abspath(args.out))
    pdf_path, previews = None, []
    if args.render:
        pdf_path, previews, exc = render_deck(args.pptx, render_dir, args.work_key)
        exceptions.extend(exc)
    else:
        exceptions.append({"kind": "not_requested",
                           "detail": "rendering not requested (--render absent)"})

    # ---- 实测 ----
    meas = pptx_measurements(args.pptx)
    if meas is None:
        exceptions.append({"kind": "tool_missing",
                           "detail": "python-pptx unavailable; pptx-level checks "
                                     "marked unmeasurable"})
        slide_count, notes_flags, ph_hits = None, [], []
    else:
        slide_count, notes_flags, ph_hits = meas

    limit = parse_slide_limit(args.task)
    slides_spec = deck.get("slides", [])
    content_slides = [s for s in slides_spec if s.get("role") not in ("title",)]
    evidence_ok = sum(1 for s in content_slides
                      if s.get("figures") or s.get("sources") or s.get("table"))

    bind_errs = binding.get("errors", [])
    unknown_fig = sum(1 for e in bind_errs if e.get("code") == "unknown-figure")
    schem_err = sum(1 for e in bind_errs if e.get("code") == "schematic-in-results")
    drift = redraw.get("mismatched_count")

    pdf_pages = pdf_page_count(pdf_path) if pdf_path else None

    checks = []
    checks.append({
        "check": "slide_count",
        "expected": f"<= {limit}" if limit else "unknown",
        "actual": slide_count if slide_count is not None else "unmeasurable",
        "pass": (slide_count is not None and limit is not None
                 and slide_count <= limit),
    })
    checks.append({
        "check": "export_page_match",
        "expected": slide_count if slide_count is not None else "unmeasurable",
        "actual": pdf_pages if pdf_pages is not None else "not rendered",
        "pass": (pdf_pages is not None and slide_count is not None
                 and pdf_pages == slide_count),
    })
    checks.append({
        "check": "placeholder_free",
        "expected": 0,
        "actual": len(ph_hits) if meas is not None else "unmeasurable",
        "pass": (meas is not None and not ph_hits),
    })
    checks.append({
        "check": "evidence_coverage",
        "expected": f"{len(content_slides)}/{len(content_slides)} content slides",
        "actual": f"{evidence_ok}/{len(content_slides)}",
        "pass": (len(content_slides) > 0 and evidence_ok == len(content_slides)),
    })
    notes_present = sum(notes_flags)
    checks.append({
        "check": "notes_coverage",
        "expected": f"{len(notes_flags)}/{len(notes_flags)} slides"
                    if notes_flags else "unmeasurable",
        "actual": (f"{notes_present}/{len(notes_flags)}" if notes_flags
                   else "unmeasurable"),
        "pass": (bool(notes_flags) and notes_present == len(notes_flags)),
    })
    checks.append({
        "check": "figures_in_manifest",
        "expected": 0,
        "actual": unknown_fig if binding else "no binding report",
        "pass": (bool(binding) and unknown_fig == 0),
    })
    checks.append({
        "check": "redraw_value_drift",
        "expected": 0,
        "actual": drift if redraw else "no redraw report",
        "pass": (redraw.get("mismatched_count") == 0),
    })
    checks.append({
        "check": "no_schematic_in_results",
        "expected": 0,
        "actual": schem_err if binding else "no binding report",
        "pass": (bool(binding) and schem_err == 0),
    })

    # ---- content_map（quotes 逐字来自 deck.json，由 Agent 从论文文本抄录） ----
    content_map = []
    for i, s in enumerate(slides_spec, start=1):
        content_map.append({
            "slide": i,
            "role": s.get("role"),
            "title": s.get("title"),
            "claims": s.get("claims", []),
            "figures": [f.get("id") for f in s.get("figures", [])],
            "table": s.get("table"),
            "sources": s.get("sources", []),
            "notes_present": (notes_flags[i - 1] if i - 1 < len(notes_flags)
                              else None),
            "notes_time_sec": s.get("notes_time_sec"),
        })

    unknown_kinds = [e["id"] for e in classify.get("entries", [])
                     if e.get("kind") == "unknown"]
    if unknown_kinds:
        uncertainties.append(f"figures with unknown kind pending adjudication: "
                             f"{unknown_kinds}")
    if binding.get("warning_count"):
        uncertainties.append(f"binding lint warnings open: "
                             f"{binding['warning_count']} (see binding_report.json)")

    all_pass = all(c["pass"] for c in checks)
    status = "success" if all_pass else "partial"
    if slide_count is None:
        status = "failed" if not os.path.isfile(args.pptx) else "partial"

    full_result = {
        "case_id": case.get("case_id"),
        "status": status,
        "editable_source": {
            "path": os.path.abspath(args.pptx),
            "format": "pptx",
            "slides": slide_count if slide_count is not None else 0,
            "notes_present": bool(notes_flags) and all(notes_flags),
        },
        "export_artifact": {
            "pdf": os.path.abspath(pdf_path) if pdf_path else None,
            "rendered": pdf_path is not None,
            "previews": [os.path.abspath(p) for p in previews],
            "pages": pdf_pages if pdf_pages is not None else 0,
        },
        "content_map": content_map,
        "compliance_checks": checks,
        "exceptions": exceptions,
        "uncertainties": uncertainties,
        "change_records": deck.get("change_records", []),
        "supporting_reports": {
            "figure_manifest": os.path.abspath(args.manifest) if args.manifest else None,
            "classify_report": os.path.abspath(args.classify_report)
            if args.classify_report else None,
            "redraw_report": os.path.abspath(args.redraw_report)
            if args.redraw_report else None,
            "binding_report": os.path.abspath(args.binding_report)
            if args.binding_report else None,
        },
    }

    # 契约字段核对：运行时从 case.json 读取，不硬编码
    missing = [k for k in contract if k not in full_result]
    if missing:
        full_result["exceptions"].append({
            "kind": "contract_gap",
            "detail": f"output_contract fields missing: {missing}"})
        if full_result["status"] == "success":
            full_result["status"] = "partial"

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(full_result, fh, ensure_ascii=False, indent=2)
    print(f"status={full_result['status']} checks_pass="
          f"{sum(1 for c in checks if c['pass'])}/{len(checks)} "
          f"rendered={full_result['export_artifact']['rendered']} "
          f"contract_missing={missing} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
