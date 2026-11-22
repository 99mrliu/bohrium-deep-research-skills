#!/usr/bin/env python3
"""result.py — Step 9 of contract-gate-slides.

Assemble output/result.json strictly from measured artifacts and gate
outputs — never from intentions. Root fields required by the case contract:
case_id, status, editable_source, export_artifact, content_map,
compliance_checks, exceptions. Extra fields (sources, uncertainty,
change_log) keep the run auditable.
"""
import json, os

IN = os.environ.get("CASE_INPUT_DIR", "/input")
WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def jload(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def main():
    brief = jload(os.path.join(WORK, "case_brief.json"), {}) or {}
    reqs = jload(os.path.join(WORK, "requirements.json"), []) or []
    plan = jload(os.path.join(WORK, "plan.json"), {}) or {}
    gp = jload(os.path.join(WORK, "gate_plan.json"), {}) or {}
    gd = jload(os.path.join(WORK, "gate_deck.json"), {}) or {}
    rs = jload(os.path.join(WORK, "render_status.json"), {}) or {}
    mw = jload(os.path.join(WORK, "mining_warnings.json"), []) or []

    checks = {}
    for r in reqs:
        checks[r["id"]] = {"status": "skip", "evidence": "未执行", "desc": r["desc"]}
    for src in (gp.get("checks"), gd.get("checks")):
        for k, v in (src or {}).items():
            if k in checks:
                checks[k] = {**v, "desc": checks[k]["desc"]}
            else:
                checks[k] = v
    pptx_ok = os.path.exists(os.path.join(OUT, "presentation.pptx"))
    pdf_ok = bool(rs.get("pdf"))
    checks.setdefault("G09-export-pdf", {"status": "pass" if pdf_ok else "fail",
                                         "evidence": rs.get("pdf") or "; ".join(rs.get("errors", []))})
    checks["G10-content-map"] = {"status": "pass" if plan.get("slides") else "fail",
                                 "evidence": f"{len(plan.get('slides', []))} 页映射"}
    checks["G11-result-fields"] = {"status": "pass", "evidence": "由 result.py 机械组装"}

    exceptions = list(brief.get("assumptions", [])) + list(mw) + list(rs.get("errors", []))
    for g in (gp, gd):
        for p in g.get("problems", []):
            if p.get("level") == "hard":
                exceptions.append(f"[{p['where']}] {p['msg']}")

    fails = [k for k, v in checks.items() if v.get("status") == "fail"]
    if not pptx_ok:
        status = "failed"
    elif fails or not pdf_ok:
        status = "partial"
    else:
        status = "completed"

    content_map = []
    for s in plan.get("slides", []):
        content_map.append({
            "slide": s.get("slide"),
            "role": s.get("role"),
            "title": s.get("title"),
            "anchors": sorted({b.get("anchor") for b in s.get("bullets", []) if b.get("anchor")}),
            "figure": s.get("figure"),
            "notes_chars": len(s.get("notes", "")),
        })

    result = {
        "case_id": brief.get("case_id", "UNKNOWN-CASE"),
        "status": status,
        "editable_source": {
            "path": "presentation.pptx" if pptx_ok else None,
            "type": "pptx",
            "slides": len(plan.get("slides", [])),
            "mode": brief.get("mode"),
            "template": os.path.basename(brief["template_pptx"]) if brief.get("template_pptx") else None,
        },
        "export_artifact": {
            "pdf": rs.get("pdf"),
            "previews_dir": "previews" if rs.get("previews") else None,
            "preview_pages": rs.get("previews", 0),
            "converter": rs.get("converter"),
        },
        "content_map": content_map,
        "compliance_checks": checks,
        "exceptions": exceptions,
        "sources": {
            "paper": os.path.basename(brief["paper_pdf"]) if brief.get("paper_pdf") else None,
            "template": os.path.basename(brief["template_pptx"]) if brief.get("template_pptx") else None,
            "starting_deck": os.path.basename(brief["starting_deck_pptx"]) if brief.get("starting_deck_pptx") else None,
        },
        "uncertainty": [w for w in mw if "扫描" in w or "OCR" in w] or
                       (["图裁剪依赖版式启发式，个别图可能含邻近文字"] if any(
                           f.get("crop_status") != "ok" for f in jload(os.path.join(WORK, "paper_figs.json"), []) or []) else []),
        "change_log": [
            {"step": "survey", "artifact": "case_brief.json + requirements.json"},
            {"step": "mine_paper", "artifact": "paper_pages/sections/figs + digest + 图裁剪"},
            {"step": "plan", "artifact": "plan.json（模型撰写，gate plan 校验）"},
            {"step": "build_deck", "artifact": "presentation.pptx"},
            {"step": "render", "artifact": rs.get("pdf") or "未导出"},
            {"step": "gate deck", "artifact": "gate_deck.json"},
        ],
    }
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": status, "fails": fails, "exceptions": len(exceptions)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
