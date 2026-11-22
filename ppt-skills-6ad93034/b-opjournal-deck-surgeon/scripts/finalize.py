#!/usr/bin/env python3
"""finalize.py — opjournal-deck-surgeon step 6: assemble result.json.

Collects only measured facts: intake report, journal stats, verify.json,
export_status.json. Root contract fields:
case_id / status / editable_source / export_artifact / content_map /
compliance_checks / exceptions. Change records are first-class: journal
digest + snapshot list + change_journal.md path.
"""
import json, os

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")
OUT = os.environ.get("CASE_OUTPUT_DIR", "/app/output")


def jl(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def main():
    intake = jl(os.path.join(WORK, "intake_report.json"), {}) or {}
    verify = jl(os.path.join(WORK, "verify.json"), {}) or {}
    export = jl(os.path.join(WORK, "export_status.json"), {}) or {}
    journal = []
    jp = os.path.join(WORK, "journal.jsonl")
    if os.path.exists(jp):
        journal = [json.loads(l) for l in open(jp, encoding="utf-8") if l.strip()]

    checks = {}
    for k, v in (verify.get("checks") or {}).items():
        checks[f"V-{k}"] = v
    checks.setdefault("V-deck-exists", {"status": "pass" if os.path.exists(
        os.path.join(OUT, "presentation.pptx")) else "fail", "evidence": ""})
    checks["V-export"] = {"status": "pass" if export.get("pdf") else "fail",
                          "evidence": export.get("pdf") or "; ".join(export.get("errors", []))}
    checks["V-journal-integrity"] = {
        "status": "pass" if journal and journal[0].get("op") == "init" else "fail",
        "evidence": f"{len(journal)} 条操作记录"}

    content_map = []
    per_slide = {}
    for op in journal:
        n = op.get("slide")
        if not n:
            continue
        e = per_slide.setdefault(n, {"slide": n, "ops": [], "anchors": set(),
                                     "figures": [], "has_notes": False})
        e["ops"].append(op["op"])
        for it in op.get("items", []) or []:
            if it.get("anchor"):
                e["anchors"].add(it["anchor"])
        if op.get("fig"):
            e["figures"].append(op["fig"])
        if op["op"] == "set_notes":
            e["has_notes"] = True
    for n in sorted(per_slide):
        e = per_slide[n]
        content_map.append({"slide": n, "ops": e["ops"],
                            "anchors": sorted(e["anchors"]),
                            "figures": e["figures"], "has_notes": e["has_notes"]})

    exceptions = list(intake.get("problems", [])) + list(export.get("errors", []))
    for f in verify.get("findings", []):
        if f.get("level") == "hard":
            exceptions.append(f["msg"])

    fails = [k for k, v in checks.items() if v.get("status") == "fail"]
    deck_ok = checks["V-deck-exists"]["status"] == "pass"
    status = "failed" if not deck_ok else ("partial" if fails else "completed")

    snaps = sorted(f for f in os.listdir(os.path.join(WORK, "versions"))
                   if f.endswith(".pptx")) if os.path.isdir(os.path.join(WORK, "versions")) else []
    result = {
        "case_id": intake.get("case_id", "UNKNOWN-CASE"),
        "status": status,
        "editable_source": {
            "path": "presentation.pptx" if deck_ok else None,
            "type": "pptx",
            "mode": intake.get("mode"),
            "base": intake.get("base_used"),
            "built_by": f"op-journal replay ({len(journal) - 1} ops onto v000)",
        },
        "export_artifact": {
            "pdf": export.get("pdf"),
            "previews_dir": "previews" if export.get("preview_pages") else None,
            "preview_pages": export.get("preview_pages", 0),
        },
        "content_map": content_map,
        "compliance_checks": checks,
        "exceptions": exceptions,
        "sources": {"paper": None, "base_deck": intake.get("base_used")},
        "uncertainty": ["图裁剪为版式启发式，个别图可能含邻近文字"]
        if intake.get("figures_ok") else ["无可用图裁剪或无论文 PDF"],
        "change_records": {
            "journal_ops": len(journal) - 1,
            "change_journal_md": "change_journal.md",
            "snapshots": snaps,
            "rollback": "python3 op.py rollback N && python3 apply.py",
        },
    }
    # paper source name if discoverable
    try:
        import glob
        pdfs = glob.glob(os.path.join(os.environ.get("CASE_INPUT_DIR", "/input"), "**", "*.pdf"),
                         recursive=True)
        if pdfs:
            result["sources"]["paper"] = os.path.basename(pdfs[0])
    except Exception:
        pass
    with open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": status, "fails": fails}, ensure_ascii=False))


if __name__ == "__main__":
    main()
