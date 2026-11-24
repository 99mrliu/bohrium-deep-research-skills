#!/usr/bin/env python3
"""make_result.py -- 组装 result.json（output_contract 全字段 + 实测 compliance_checks）。

从 case.json 读取 output_contract 字段清单（不硬编码），逐字段填充真实测量值，
并另加 uncertainties、change_records。compliance_checks 的 actual 全部来自脚本
实测（python-pptx 打开 deck、pypdf/pymupdf 数 PDF 页、quote 逐字子串校验等）。

用法：
    python3 make_result.py --case case.json --task task.md \
        --deck presentation.pptx --pdf presentation.pdf \
        --previews "preview-*.png" --beats beats.json --evidence evidence.json \
        --notes-report notes_report.json --rehearsal rehearsal.json \
        [--change-records change_records.json] [--status auto] --out result.json
"""
import argparse
import glob
import json
import os
import re
import sys

PLACEHOLDER_PATTERNS = ["click to add", "lorem ipsum", "{{", "}}", "TODO", "replace this"]


def load_json(path, required=True):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        if required:
            print(f"ERROR: cannot read {path}: {e}", file=sys.stderr)
            sys.exit(2)
        return None


def count_pdf_pages(pdf_path):
    if not pdf_path or not os.path.exists(pdf_path):
        return None
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf_path).pages)
    except ImportError:
        pass
    except Exception:
        return None
    try:
        import fitz
        doc = fitz.open(pdf_path)
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return None


def parse_max_slides(task_text):
    m = re.search(r"(?:at most|≤|<=|up to)\s*(\d+)\s*(?:页|slides?)?", task_text or "")
    return int(m.group(1)) if m else None


def build_sources(beat, evidence, evidence_fulltext):
    """从 beat 的 evidence_refs 构建 sources；quote 逐字取自 evidence，并实测校验。"""
    figs = {f["ref"]: f for f in evidence.get("figures", [])}
    tabs = {t["ref"]: t for t in evidence.get("tables", [])}
    anchors = {a["id"]: a for a in evidence.get("anchors", [])}
    sources = []
    for ref in beat.get("evidence_refs") or []:
        kind, _, key = str(ref).partition(":")
        entry = None
        if kind == "fig":
            e = figs.get(key)
            if e:
                entry = ("figure", key, e["page"], e["caption"])
        elif kind == "tab":
            e = tabs.get(key)
            if e:
                entry = ("table", key, e["page"], e["caption"])
        elif kind == "anchor" and key.isdigit():
            e = anchors.get(int(key))
            if e:
                entry = ("text", f"{e['value']} {e['unit']}", e["page"], e["context"])
        elif kind == "page" and key.isdigit():
            entry = ("page", f"page {key}", int(key), "")
        if entry is None:
            sources.append({"kind": kind, "ref": key, "locator": "unknown",
                            "quote": "", "quote_verbatim_verified": False})
            continue
        k, r, page, quote = entry
        verified = bool(quote) and quote in evidence_fulltext
        sources.append({
            "kind": k, "ref": r, "locator": f"p.{page}", "quote": quote,
            "quote_verbatim_verified": verified,
        })
    return sources


def main() -> int:
    ap = argparse.ArgumentParser(description="Assemble result.json per case.json output_contract.")
    ap.add_argument("--case", required=True)
    ap.add_argument("--task", help="task.md (for slide-count expectation)")
    ap.add_argument("--deck", required=True)
    ap.add_argument("--pdf", help="rendered PDF (omit if render tool missing)")
    ap.add_argument("--previews", default="", help="glob of preview PNGs")
    ap.add_argument("--beats", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--notes-report", required=True)
    ap.add_argument("--rehearsal", required=True)
    ap.add_argument("--change-records", help="JSON list of change records")
    ap.add_argument("--exceptions", help="JSON list of exceptions")
    ap.add_argument("--status", default="auto", choices=["auto", "success", "partial", "failed"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    case = load_json(args.case)
    beats_data = load_json(args.beats)
    evidence = load_json(args.evidence)
    notes_report = load_json(args.notes_report)
    rehearsal = load_json(args.rehearsal)
    beats = beats_data.get("beats") if isinstance(beats_data, dict) else beats_data

    try:
        from pptx import Presentation
    except ImportError:
        print("ERROR: python-pptx required for make_result.py", file=sys.stderr)
        return 2
    prs = Presentation(args.deck)
    n_slides = len(prs.slides)

    task_text = ""
    if args.task and os.path.exists(args.task):
        with open(args.task, encoding="utf-8") as f:
            task_text = f.read()
    max_slides = parse_max_slides(task_text)

    evidence_fulltext = "\n".join(p["text"] for p in evidence.get("pages", []))
    rehearsal_by_slide = {r["slide"]: r for r in rehearsal.get("per_slide", [])}

    # ---- content_map ----
    content_map = []
    exceptions = []
    if args.exceptions and os.path.exists(args.exceptions):
        exceptions = load_json(args.exceptions) or []
    for i, slide in enumerate(prs.slides, start=1):
        beat = beats[i - 1] if i - 1 < len(beats) else {}
        notes = ""
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        title = ""
        if slide.shapes.title is not None:
            title = slide.shapes.title.text_frame.text
        if not title:  # 兜底：forge_title 文本框（无标题占位符的版式）
            for shape in slide.shapes:
                if shape.name == "forge_title" and shape.has_text_frame:
                    title = shape.text_frame.text
                    break
        sources = build_sources(beat, evidence, evidence_fulltext)
        refs = beat.get("evidence_refs") or []
        content_map.append({
            "slide": i,
            "role": beat.get("role", "unknown"),
            "title": title,
            "claims": [beat.get("claim", "")] if beat.get("claim") else [],
            "figures": [r.split(":", 1)[1] for r in refs if str(r).startswith("fig:")],
            "table": next((r.split(":", 1)[1] for r in refs if str(r).startswith("tab:")), None),
            "sources": sources,
            "notes_present": bool(notes),
            "notes_time_sec": rehearsal_by_slide.get(i, {}).get("spoken_sec", 0.0),
        })

    # ---- compliance_checks（actual 全部实测） ----
    all_text = []
    notes_flags = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                all_text.append(shape.text_frame.text)
        notes_flags.append(
            bool(slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip())
        )
    joined = "\n".join(all_text).lower()
    placeholder_hits = sum(joined.count(p.lower()) for p in PLACEHOLDER_PATTERNS)

    pdf_pages = count_pdf_pages(args.pdf)
    previews = sorted(glob.glob(args.previews)) if args.previews else []
    rendered = pdf_pages is not None and pdf_pages > 0
    if not rendered:
        exceptions.append({
            "kind": "tool_missing",
            "detail": "PDF render unavailable or PDF unreadable; export_artifact.rendered=false",
        })

    total_sources = sum(len(cm["sources"]) for cm in content_map)
    verified_sources = sum(
        1 for cm in content_map for s in cm["sources"] if s["quote_verbatim_verified"]
    )
    # page 型引用无 quote，不计入逐字校验分母
    quoted_sources = sum(
        1 for cm in content_map for s in cm["sources"] if s["quote"]
    )
    evidence_cov = (verified_sources / quoted_sources) if quoted_sources else 0.0

    checks = [
        {
            "check": "slide_count",
            "expected": f"<= {max_slides}" if max_slides else "unspecified",
            "actual": n_slides,
            "pass": (n_slides <= max_slides) if max_slides else True,
        },
        {
            "check": "export_page_match",
            "expected": n_slides,
            "actual": pdf_pages,
            "pass": bool(rendered and pdf_pages == n_slides),
        },
        {
            "check": "placeholder_free",
            "expected": 0,
            "actual": placeholder_hits,
            "pass": placeholder_hits == 0,
        },
        {
            "check": "evidence_coverage",
            "expected": 1.0,
            "actual": round(evidence_cov, 3),
            "pass": quoted_sources > 0 and evidence_cov == 1.0,
        },
        {
            "check": "notes_coverage",
            "expected": n_slides,
            "actual": sum(notes_flags),
            "pass": all(notes_flags) and bool(notes_report.get("pass")),
        },
    ]

    # ---- 契约字段 ----
    result = {
        "case_id": case.get("case_id", "unknown"),
        "status": "success",  # 下方统一重算
        "editable_source": {
            "path": os.path.abspath(args.deck),
            "format": "pptx",
            "slides": n_slides,
            "notes_present": all(notes_flags),
        },
        "export_artifact": {
            "pdf": os.path.abspath(args.pdf) if args.pdf else None,
            "rendered": rendered,
            "previews": [os.path.abspath(p) for p in previews],
            "pages": pdf_pages or 0,
        },
        "content_map": content_map,
        "compliance_checks": checks,
        "exceptions": exceptions,
        "uncertainties": [
            "spoken-time estimates assume 240 CJK chars/min and 150 EN words/min; "
            "real delivery varies by speaker",
            "figure crops come from the caption-upward page region and may include "
            "neighbor text on dense pages",
        ],
        "change_records": [],
    }
    if args.change_records and os.path.exists(args.change_records):
        result["change_records"] = load_json(args.change_records) or []
    else:
        result["change_records"] = [{
            "version": "v1", "slide": "all",
            "change": "initial forge of all beats",
            "reason": "first pass",
            "rollback": "re-run slide_forge.py per beat to restore any slide",
        }]

    # output_contract 覆盖自检（字段名运行时从 case.json 读）
    contract = case.get("output_contract", [])
    missing = [k for k in contract if k not in result]
    if missing:
        exceptions.append({"kind": "contract_gap", "detail": f"missing fields: {missing}"})
        result["exceptions"] = exceptions

    if args.status == "auto":
        if missing:
            result["status"] = "failed"
        elif all(c["pass"] for c in checks) and not exceptions:
            result["status"] = "success"
        else:
            result["status"] = "partial"
    else:
        result["status"] = args.status

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    npass = sum(1 for c in checks if c["pass"])
    print(
        f"make_result: status={result['status']} checks={npass}/{len(checks)} pass "
        f"sources_verified={verified_sources}/{quoted_sources} "
        f"contract_fields={len(contract) - len(missing)}/{len(contract)} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
