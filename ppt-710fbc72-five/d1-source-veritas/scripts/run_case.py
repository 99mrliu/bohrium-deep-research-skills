"""run_case.py — single entry point for source-veritas-deck.

Two phases (DESIGN.md unified calling pattern):

  python3 run_case.py prepare --input /input --work /app/work --output /app/output
      bootstrap deps -> read case.json/task.md/materials -> build the SOURCE
      CORPUS LEDGER (extract_source) -> write partial-first result.json (all
      output_contract fields) -> prefill slide_plan.json with candidate
      evidence anchors -> print NEXT ACTION.

  python3 run_case.py finish --input /input --work /app/work --output /app/output
      FIDELITY GATE (verify_fidelity) -> build deck.pptx -> export PDF/PNG ->
      QA -> finalize result.json.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DEFAULT_CONTRACT_FIELDS = ["case_id", "status", "summary", "artifacts",
                           "evidence_map", "sources", "uncertainty",
                           "change_log"]


# ---------------------------------------------------------------------------
# input discovery
# ---------------------------------------------------------------------------

def _read_input(input_dir: str, change_log: list) -> dict:
    case = common.load_json(os.path.join(input_dir, "case.json"), {}) or {}
    task_path = os.path.join(input_dir, "task.md")
    task = ""
    if os.path.exists(task_path):
        with open(task_path, "r", encoding="utf-8") as f:
            task = f.read()
    else:
        change_log.append({"action": "input-missing", "detail": "task.md not found"})

    materials = case.get("materials") or {}
    paper_pdf, template_pptx = None, None
    if isinstance(materials, dict):
        for key in ("paper", "paper_pdf", "pdf", "source"):
            p = materials.get(key)
            if p:
                cand = p if os.path.isabs(p) else os.path.join(input_dir, p)
                if os.path.exists(cand):
                    paper_pdf = cand
        for key in ("template", "template_pptx", "pptx", "deck"):
            p = materials.get(key)
            if p:
                cand = p if os.path.isabs(p) else os.path.join(input_dir, p)
                if os.path.exists(cand):
                    template_pptx = cand
    if not paper_pdf:
        pdfs = sorted(glob.glob(os.path.join(input_dir, "**", "*.pdf"),
                                recursive=True))
        paper_pdf = pdfs[0] if pdfs else None
    if not template_pptx:
        pptxs = sorted(glob.glob(os.path.join(input_dir, "**", "*.pptx"),
                                 recursive=True))
        templ = [p for p in pptxs if "template" in os.path.basename(p).lower()]
        template_pptx = (templ or pptxs or [None])[0]

    fields = ((case.get("output_contract") or {}).get("fields")
              or DEFAULT_CONTRACT_FIELDS)
    return {"case": case, "task": task, "paper_pdf": paper_pdf,
            "template_pptx": template_pptx, "contract_fields": fields}


def _partial_result(case: dict, fields: list, sources: list,
                    change_log: list) -> dict:
    """Partial-first skeleton covering EVERY contract field."""
    res = {
        "case_id": case.get("case_id", "unknown"),
        "status": "partial",
        "summary": "prepare phase done: corpus ledger built; "
                   "slide_plan.json awaiting agent completion",
        "artifacts": [],
        "evidence_map": [],
        "sources": sources,
        "uncertainty": ["slide plan not yet completed; deck not built"],
        "change_log": change_log,
    }
    for f in fields:  # superset-cover anything else the contract declares
        if f not in res:
            res[f] = None
    return res


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def cmd_prepare(args) -> int:
    t0 = time.time()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)
    change_log = common.load_json(os.path.join(args.work, "change_log.json"), [])

    deps = common.ensure_deps(change_log)
    missing = [k for k, v in deps.items() if v.startswith("missing")]
    if missing:
        print(f"[prepare] DEGRADED: missing deps {missing}")

    info = _read_input(args.input, change_log)
    case, fields = info["case"], info["contract_fields"]
    sources = []
    for label, p in (("case.json", os.path.join(args.input, "case.json")),
                     ("task.md", os.path.join(args.input, "task.md")),
                     ("paper", info["paper_pdf"]), ("template", info["template_pptx"])):
        if p and os.path.exists(p):
            sources.append({"role": label, "path": os.path.abspath(p),
                            "sha256": common.sha256_file(p)})
        else:
            change_log.append({"action": "input-missing",
                               "detail": f"{label} not found"})

    # --- build the corpus ledger ------------------------------------------
    corpus_dir = os.path.join(args.work, "corpus")
    stats = None
    if info["paper_pdf"] and not missing:
        import extract_source
        stats = extract_source.extract(info["paper_pdf"], corpus_dir)
        change_log.append({"action": "extract-corpus",
                           "detail": f"{stats['text_blocks']} text blocks, "
                                     f"{len(stats['figures'])} figures, "
                                     f"{len(stats['sections'])} sections"})
    else:
        change_log.append({"action": "extract-skipped",
                           "reason": "no paper pdf or missing deps"})

    # --- partial-first result.json -----------------------------------------
    res = _partial_result(case, fields, sources, change_log)
    res["degraded"] = [f"missing deps: {missing}"] if missing else []
    common.dump_json(res, os.path.join(args.output, "result.json"))
    common.dump_json(change_log, os.path.join(args.work, "change_log.json"))

    # --- prefill slide_plan.json with candidate evidence anchors -----------
    plan_path = os.path.join(args.work, "slide_plan.json")
    if not os.path.exists(plan_path):
        candidates = {"sections": stats["sections"] if stats else [],
                      "figures": stats["figures"] if stats else [],
                      "number_samples": []}
        if stats:
            entries = common.read_corpus(stats["corpus"])
            for e in entries:
                if e.get("kind") == "text" and e.get("numbers"):
                    candidates["number_samples"].append(
                        {"page": e["page"], "id": e["id"],
                         "numbers": [n["raw"] for n in e["numbers"]][:6]})
                if len(candidates["number_samples"]) >= 12:
                    break
        plan = {
            "mainline": {"problem": "", "method": "", "results": "",
                         "limitations": ""},
            "audience": "",
            "duration_min": 12,
            "corpus_dir": os.path.abspath(corpus_dir),
            "template": os.path.abspath(info["template_pptx"]) if info["template_pptx"] else None,
            "candidate_evidence": candidates,
            "slides": [
                {"kind": k, "title": "", "claim": "", "bullets": [],
                 "figures": [], "evidence": [], "notes": "",
                 "layout_hint": h}
                for k, h in [("title", "Title Slide"),
                             ("background", "Title and Content"),
                             ("method", "Title and Content"),
                             ("results", "Title and Content"),
                             ("discussion", "Title and Content"),
                             ("conclusion", "Title and Content")]],
        }
        common.dump_json(plan, plan_path)

    print(f"[prepare] corpus={stats['corpus'] if stats else 'NONE'}")
    print(f"[prepare] result.json (partial) -> {args.output}/result.json")
    print(f"[prepare] slide_plan.json -> {plan_path}")
    print("NEXT ACTION: edit slide_plan.json — fill titles/claims/bullets/"
          "figures/evidence using ONLY corpus-anchored content "
          "(numbers verbatim, figures from corpus/figs, quotes exact), then run:")
    print(f"  python3 {os.path.abspath(__file__)} finish --input {args.input} "
          f"--work {args.work} --output {args.output}")
    print(f"[prepare] elapsed {time.time()-t0:.1f}s")
    return 0


# ---------------------------------------------------------------------------
# finish
# ---------------------------------------------------------------------------

def cmd_finish(args) -> int:
    t0 = time.time()
    work, out = args.work, args.output
    os.makedirs(out, exist_ok=True)
    change_log = common.load_json(os.path.join(work, "change_log.json"), [])
    plan_path = os.path.join(work, "slide_plan.json")
    plan = common.load_json(plan_path)
    res_path = os.path.join(out, "result.json")
    res = common.load_json(res_path, {}) or {}
    case = common.load_json(os.path.join(args.input, "case.json"), {}) or {}
    fields = ((case.get("output_contract") or {}).get("fields")
              or DEFAULT_CONTRACT_FIELDS)

    uncertainty = list(res.get("uncertainty") or [])
    degraded = list(res.get("degraded") or [])
    artifacts, evidence_map = [], []

    if plan is None:
        res.update({"case_id": case.get("case_id", res.get("case_id", "unknown")),
                    "status": "failed",
                    "summary": "slide_plan.json missing; run prepare first",
                    "change_log": change_log})
        for f in fields:
            res.setdefault(f, None)
        common.dump_json(res, res_path)
        print("[finish] FAILED: no slide_plan.json")
        return 1

    corpus_dir = plan.get("corpus_dir") or os.path.join(work, "corpus")
    template = plan.get("template")
    if not template or not os.path.exists(template):
        info = _read_input(args.input, change_log)
        template = info["template_pptx"]

    # --- 1) FIDELITY GATE ---------------------------------------------------
    import verify_fidelity
    report = verify_fidelity.verify_plan(plan, corpus_dir, change_log)
    clean_plan = plan
    if report["summary"]["unverified"]:
        clean_plan = verify_fidelity.drop_unverified(plan, report, change_log)
        report["gate"] = "pass-with-drops"
    clean_path = os.path.join(work, "slide_plan.verified.json")
    common.dump_json(clean_plan, clean_path)
    report["cleaned_plan"] = os.path.abspath(clean_path)
    report_path = os.path.join(out, "fidelity_report.json")
    common.dump_json(report, report_path)
    artifacts.append({"kind": "fidelity_report", "path": os.path.abspath(report_path),
                      "sha256": common.sha256_file(report_path)})

    # --- 2) build deck ------------------------------------------------------
    deck_path = os.path.join(out, "deck.pptx")
    build_log_path = os.path.join(work, "build_log.json")
    build_log = None
    if template and os.path.exists(template):
        import build_deck
        build_log = build_deck.build(clean_plan, template, deck_path)
        common.dump_json(build_log, build_log_path)
        artifacts.append({"kind": "deck", "path": os.path.abspath(deck_path),
                          "sha256": common.sha256_file(deck_path)})
    else:
        degraded.append("template pptx missing: deck not built")
        uncertainty.append("no template; deck.pptx absent")

    # --- 3) export + QA ------------------------------------------------------
    qa = None
    if build_log:
        import export_render
        qa = export_render.export(deck_path, out)
        qa_path = os.path.join(out, "qa_report.json")
        common.dump_json(qa, qa_path)
        artifacts.append({"kind": "qa_report", "path": os.path.abspath(qa_path),
                          "sha256": common.sha256_file(qa_path)})
        if qa.get("pdf"):
            artifacts.append({"kind": "pdf", "path": qa["pdf"],
                              "sha256": qa["pdf_sha256"]})
        for p in qa.get("previews", []):
            artifacts.append({"kind": "preview_png", "path": p["file"],
                              "sha256": p["sha256"]})
        degraded.extend(qa.get("degraded", []))
        if qa.get("counts_match") is False:
            uncertainty.append("pdf page count != pptx slide count")

    # --- 4) evidence map ------------------------------------------------------
    for sidx, slide in enumerate(clean_plan.get("slides", [])):
        evidence_map.append({
            "slide": sidx, "title": slide.get("title", ""),
            "anchors": [{"type": e.get("type"), "ref": e.get("ref")}
                        for e in slide.get("evidence", []) or []],
            "figures": [f.get("ref") for f in slide.get("figures", []) or []],
            "verdict": (report["slides"][sidx]["verdict"]
                        if sidx < len(report["slides"]) else None),
        })

    # --- 5) finalize result.json ---------------------------------------------
    summary = report["summary"]
    status = "success"
    problems = []
    if not build_log:
        status, problems = "failed", ["deck not built"]
    elif degraded or summary["unverified"]:
        status = "partial"
        if summary["unverified"]:
            problems.append(f"{summary['unverified']} unverified item(s) dropped by gate")
        if degraded:
            problems.append(f"degraded: {'; '.join(degraded)}")

    res.update({
        "case_id": case.get("case_id", res.get("case_id", "unknown")),
        "status": status,
        "summary": (f"deck built from corpus-ledger plan; fidelity gate "
                    f"{report['gate']} (verified={summary['verified']} "
                    f"loose={summary['loose']} unverified={summary['unverified']} "
                    f"dropped={summary['dropped']})"
                    + ("; " + "; ".join(problems) if problems else "")),
        "artifacts": artifacts,
        "evidence_map": evidence_map,
        "sources": res.get("sources", []),
        "uncertainty": uncertainty,
        "change_log": change_log,
        "degraded": degraded,
    })
    for f in fields:
        res.setdefault(f, None)
    common.dump_json(res, res_path)
    common.dump_json(change_log, os.path.join(work, "change_log.json"))

    print(f"[finish] status={status} gate={report['gate']}")
    print(f"[finish] fidelity_report -> {report_path}")
    if build_log:
        print("[finish] per-slide checklist:")
        for s in build_log["slides"]:
            print(f"  slide {s['slide']}: layout={s['layout_used']} "
                  f"title_via={s.get('title_via')} body_via={s.get('body_via')} "
                  f"figs={len(s.get('figures_embedded', []))} "
                  f"fallbacks={s.get('fallbacks', [])}")
    print(f"[finish] result.json -> {res_path}")
    print(f"[finish] elapsed {time.time()-t0:.1f}s")
    return 0 if status in ("success", "partial") else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "finish"):
        p = sub.add_parser(name)
        p.add_argument("--input", required=True)
        p.add_argument("--work", required=True)
        p.add_argument("--output", required=True)
    args = ap.parse_args()
    return cmd_prepare(args) if args.cmd == "prepare" else cmd_finish(args)


if __name__ == "__main__":
    sys.exit(main())
