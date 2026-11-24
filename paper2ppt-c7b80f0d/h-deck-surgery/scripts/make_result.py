#!/usr/bin/env python3
"""make_result.py — 汇总全部手术产物，按 case.json 的 output_contract 生成 result.json。

用法:
    python3 make_result.py --case case.json --task task.md --deck final.pptx \
        --evidence evidence.json --ops-log ops_log.json --diff deck_diff.json \
        --render render_report.json --out result.json

纪律：
  * output_contract 字段名运行时从 case.json 读取，不硬编码；
  * compliance_checks 的 actual 一律来自脚本真实测量（deck 解析 / render 报告 / evidence 比对）；
  * content_map.sources[].quote 是 evidence.json 中的逐字 quote，只在数值/caption/limitation
    真实匹配时挂载；挂不上就留空并在 uncertainties 说明。
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_common as dc
from evidence_scan import UNIT_RE, N_COUNT_RE
from plan_ops import PLACEHOLDER_TITLE_RE, parse_max_slides

WORDS_PER_SEC = 2.5  # 约 150 词/分钟语速，用于 notes_time_sec 估计


def role_of(index: int, title: str) -> str:
    t = (title or "").lower()
    if index == 1:
        return "title"
    for key, role in (("limitation", "limitations"), ("conclusion", "conclusion"),
                      ("method", "methods"), ("result", "results"),
                      ("background", "background"), ("table", "results")):
        if key in t:
            return role
    return "content"


def slide_sources(slide_text: str, evidence: dict) -> list[dict]:
    """把页面文本中的数值/caption/limitation 与 evidence 逐字 quote 对上。"""
    sources = []
    seen = set()
    numbers = evidence.get("numbers", [])
    values = [(m.group(1), m.group(2)) for m in UNIT_RE.finditer(slide_text)]
    values += [(m.group(1), "count(n)") for m in N_COUNT_RE.finditer(slide_text)]
    for val, unit in values:
        for n in numbers:
            if n["value"] == val and n["unit"] == unit:
                key = ("number", val, unit, n["page"])
                if key not in seen:
                    seen.add(key)
                    sources.append({"kind": "paper_pdf",
                                    "ref": os.path.basename(evidence.get("source", "paper.pdf")),
                                    "locator": f"page {n['page']}",
                                    "quote": n["quote"]})
                break
    for cap in evidence.get("captions", []):
        if cap["label"] in slide_text:
            key = ("caption", cap["label"])
            if key not in seen:
                seen.add(key)
                sources.append({"kind": "paper_pdf",
                                "ref": os.path.basename(evidence.get("source", "paper.pdf")),
                                "locator": f"page {cap['page']}",
                                "quote": cap["quote"]})
    if re.search(r"limitation", slide_text, re.IGNORECASE):
        for lim in evidence.get("limitations", []):
            key = ("limitation", lim["page"])
            if key not in seen:
                seen.add(key)
                sources.append({"kind": "paper_pdf",
                                "ref": os.path.basename(evidence.get("source", "paper.pdf")),
                                "locator": f"page {lim['page']}",
                                "quote": lim["quote"]})
    return sources


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按 output_contract 汇总 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--deck", required=True, help="最终 pptx")
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--ops-log", required=True)
    ap.add_argument("--diff", required=True)
    ap.add_argument("--render", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    for p in (args.case, args.task, args.deck, args.evidence, args.ops_log,
              args.diff, args.render):
        if not os.path.exists(p):
            print(f"error: input not found: {p}", file=sys.stderr)
            return 2

    case = dc.load_json(args.case)
    contract = case.get("output_contract", [])
    with open(args.task, "r", encoding="utf-8") as f:
        task_text = f.read()
    evidence = dc.load_json(args.evidence)
    ops_log = dc.load_json(args.ops_log)
    diff = dc.load_json(args.diff)
    render = dc.load_json(args.render)
    deck = dc.load_deck(args.deck)

    exceptions, uncertainties = [], []

    # ---- content_map ----
    content_map = []
    for s in deck["slides"]:
        body_lines = []
        for bt in s["body_texts"]:
            body_lines += [ln.strip() for ln in bt.splitlines() if ln.strip()]
        slide_text = (s["title"] or "") + "\n" + "\n".join(body_lines)
        notes = s["notes"] or ""
        n_words = len(notes.split())
        figures = sorted(set(re.findall(r"Figure\s+\d+", slide_text)))
        if s["n_pictures"] and not figures:
            figures = [f"{s['n_pictures']} embedded image(s)"]
        content_map.append({
            "slide": s["index"],
            "role": role_of(s["index"], s["title"]),
            "title": s["title"],
            "claims": body_lines,
            "figures": figures,
            "table": bool(re.search(r"Table\s+\d+", slide_text)),
            "sources": slide_sources(slide_text, evidence),
            "notes_present": bool(notes.strip()),
            "notes_time_sec": round(n_words / WORDS_PER_SEC, 1) if n_words else 0,
        })

    # ---- compliance_checks（全部实测）----
    n_slides = deck["slide_count"]
    max_slides = parse_max_slides(task_text)
    checks = []
    if max_slides is not None:
        checks.append({"check": "slide_count", "expected": f"<= {max_slides}",
                       "actual": n_slides, "pass": n_slides <= max_slides})
    else:
        checks.append({"check": "slide_count", "expected": "unknown (task.md unparseable)",
                       "actual": n_slides, "pass": True})
        uncertainties.append("could not parse slide limit from task.md")

    render_pages = render.get("pages")
    rendered = bool(render.get("rendered"))
    if rendered:
        checks.append({"check": "export_page_match", "expected": n_slides,
                       "actual": render_pages, "pass": render_pages == n_slides})
    else:
        checks.append({"check": "export_page_match", "expected": n_slides,
                       "actual": None, "pass": False})
        exceptions.append({"kind": "tool_missing",
                           "detail": f"render failed/skipped: "
                                     f"{render.get('tool_missing') or render.get('error')}"})

    placeholder_hits = [
        s["index"] for s in deck["slides"]
        if PLACEHOLDER_TITLE_RE.match(s["title"] or "") or not (s["title"] or "").strip()
    ]
    checks.append({"check": "placeholder_free", "expected": 0,
                   "actual": len(placeholder_hits), "pass": not placeholder_hits})

    content_slides = [c for c in content_map if c["claims"]]
    with_src = [c for c in content_slides if c["sources"]]
    ev_cov = round(len(with_src) / len(content_slides), 3) if content_slides else 1.0
    checks.append({"check": "evidence_coverage",
                   "expected": 1.0, "actual": ev_cov, "pass": ev_cov >= 1.0})
    if ev_cov < 1.0:
        missing = [c["slide"] for c in content_slides if not c["sources"]]
        uncertainties.append(f"slides without evidence-backed quote: {missing}")

    with_notes = [c for c in content_map if c["notes_present"]]
    notes_cov = round(len(with_notes) / len(content_map), 3) if content_map else 0.0
    checks.append({"check": "notes_coverage", "expected": 1.0,
                   "actual": notes_cov, "pass": notes_cov >= 1.0})

    # ---- change_records（对接 ops_log）----
    change_records = []
    for o in ops_log.get("ops", []):
        if o["status"] != "applied":
            continue
        change_records.append({
            "version": o.get("version_after"),
            "slide": o.get("slide"),
            "change": f"{o['op']}: {o.get('detail')}",
            "reason": o.get("reason", ""),
            "rollback": o.get("rollback"),
        })

    all_pass = all(c["pass"] for c in checks) and not exceptions
    status = "success" if all_pass else ("partial" if rendered else "failed")

    fields = {
        "case_id": case.get("case_id"),
        "status": status,
        "editable_source": {
            "path": os.path.abspath(args.deck),
            "format": "pptx",
            "slides": n_slides,
            "notes_present": any(c["notes_present"] for c in content_map),
        },
        "export_artifact": {
            "pdf": render.get("pdf"),
            "rendered": rendered,
            "previews": render.get("previews", []),
            "pages": render_pages,
        },
        "content_map": content_map,
        "compliance_checks": checks,
        "exceptions": exceptions,
    }
    result = {}
    for name in contract:  # 契约字段按 case.json 原顺序、原字段名输出
        if name in fields:
            result[name] = fields[name]
        else:
            result[name] = None
            exceptions.append({"kind": "contract_field_unfilled",
                               "detail": f"output_contract field {name!r} not produced"})
            result["status"] = "partial" if status == "success" else status
    result["uncertainties"] = uncertainties
    result["change_records"] = change_records
    result["provenance"] = {
        "mode": "edit",
        "ops_log": os.path.abspath(args.ops_log),
        "deck_diff_summary": diff.get("summary"),
        "render_engine": render.get("engine"),
    }

    dc.dump_json(result, args.out)
    print(f"result ok: status={result['status']} case_id={result.get('case_id')} "
          f"checks={len(checks)} all_pass={all_pass} "
          f"change_records={len(change_records)} -> {args.out}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
