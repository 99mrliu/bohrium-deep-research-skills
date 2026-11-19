#!/usr/bin/env python3
"""lib_finalize.py — assemble final result.json for the cartography workflow.

Reads:
  --case  /input/case.json
  --work  work dir containing answers_draft.json:
      {"answers": [{"question_id": "...", "question": "...", "answer": "...",
                    "evidence": [{"entry_id": "E01", "locator": "L12-L14",
                                  "quote": "逐字引文"}]}]}
  --out   output dir containing artifacts/catalog.json, repair_log.md

Deterministic enforcement:
  * every evidence entry must point to an existing catalog entry that is
    readable AND current_version; historical-version citations are moved to
    `version_caveats`; unknown entry_ids are dropped with a note;
  * status = "completed" iff every question answered with evidence or an
    explicit no-evidence statement and no unresolved evidence problems,
    else "partial";
  * the catalog summary (six dimensions) is embedded so result.json stands
    alone for review.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone


def norm(s):
    return re.sub(r"\s+", "", s or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()

    case = json.load(open(a.case, encoding="utf-8")) if os.path.exists(a.case) else {}
    contract = case.get("output_contract") or {}

    draft_path = os.path.join(a.work, "answers_draft.json")
    draft = {"answers": []}
    if os.path.exists(draft_path):
        draft = json.load(open(draft_path, encoding="utf-8"))

    cat_path = os.path.join(a.out, "artifacts", "catalog.json")
    catalog = {"entries": [], "dimensions": {}, "conflicts": []}
    if os.path.exists(cat_path):
        catalog = json.load(open(cat_path, encoding="utf-8"))
    by_id = {e["entry_id"]: e for e in catalog.get("entries", [])}

    # line-verify quotes against extracted texts when available
    texts = {}
    for e in catalog.get("entries", []):
        xp = e.get("extract_path") or os.path.join(
            a.work, "extracted", e["entry_id"] + ".txt")
        if e.get("extract_status") == "ok" and os.path.exists(xp):
            texts[e["entry_id"]] = open(xp, encoding="utf-8", errors="replace").read()

    answers, dropped, caveats = [], [], []
    for ans in draft.get("answers", []):
        kept = []
        for ev in ans.get("evidence", []):
            eid = ev.get("entry_id")
            ent = by_id.get(eid)
            if ent is None:
                dropped.append({"question_id": ans.get("question_id"),
                                "entry_id": eid, "reason": "not_in_catalog"})
                continue
            ok, why = True, None
            if not ent.get("readable"):
                ok, why = False, "not_readable"
            elif not ent.get("current_version", True):
                ok, why = False, "historical_version"
            elif ent.get("extract_status") != "ok":
                ok, why = False, "text_unavailable"
            else:
                q = norm(ev.get("quote"))
                if q and q not in norm(texts.get(eid, "")):
                    ok, why = False, "quote_not_found"
            if ok:
                ev2 = dict(ev)
                ev2["path"] = ent["path"]
                ev2["sha8"] = ent.get("sha8")
                ev2["role"] = ent.get("role")
                kept.append(ev2)
            elif why == "historical_version":
                caveats.append({"question_id": ans.get("question_id"),
                                "entry_id": eid, "path": ent["path"],
                                "role": ent.get("role"),
                                "note": "引用来自历史版本；已移入 version_caveats"})
            else:
                dropped.append({"question_id": ans.get("question_id"),
                                "entry_id": eid, "reason": why})
        answers.append({
            "question_id": ans.get("question_id"),
            "question": ans.get("question"),
            "answer": ans.get("answer"),
            "evidence": kept,
            "no_evidence": bool(ans.get("no_evidence")),
            "missing": ans.get("missing"),
        })

    dims = catalog.get("dimensions", {})
    result = {
        "case_id": case.get("case_id"),
        "status": None,
        "catalog_summary": {
            "file_types": dims.get("file_types", {}),
            "metadata_sources": (dims.get("metadata_fields", {}) or {}).get("sources", []),
            "directories": sorted((dims.get("directory_tree", {}) or {}).keys()),
            "duplicate_groups": len(dims.get("duplicates", [])),
            "version_chains": len(dims.get("version_diffs", [])),
            "unreadable_skipped": (dims.get("permissions_sources", {}) or {}).get(
                "skipped", []),
        },
        "answers": answers,
        "version_caveats": caveats,
        "sources": [{"entry_id": ev["entry_id"], "path": ev.get("path"),
                     "sha8": ev.get("sha8"), "locator": ev.get("locator")}
                    for ans in answers for ev in ans["evidence"]],
        "uncertainty": [],
        "change_log": [
            "lib_finalize: answers=%d kept_evidence=%d dropped=%d caveats=%d"
            % (len(answers),
               sum(len(x["evidence"]) for x in answers), len(dropped), len(caveats)),
        ],
        "skipped_files": (dims.get("permissions_sources", {}) or {}).get("skipped", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(contract, dict):
        for k in contract:
            result.setdefault(k, answers if "answer" in k else [])

    if dropped:
        result["uncertainty"].append(
            "有 %d 条证据未通过编目校验（不可读/历史版本/文本不可用/引文不符），"
            "明细见 dropped_evidence。" % len(dropped))
        result["dropped_evidence"] = dropped
    if catalog.get("conflicts"):
        result["uncertainty"].append(
            "编目存在 %d 个版本冲突（见 artifacts/catalog.json conflicts 与 "
            "repair_log.md 第 4 节），答案未擅自取舍。" % len(catalog["conflicts"]))
    for ans in answers:
        if ans.get("no_evidence"):
            result["uncertainty"].append(
                "问题 %s：库中无依据。缺失：%s"
                % (ans.get("question_id"), ans.get("missing") or "未说明"))

    complete = (not dropped) and all(
        ans.get("evidence") or ans.get("no_evidence") for ans in answers)
    result["status"] = "completed" if complete else "partial"
    if not complete:
        result["uncertainty"].append("存在被丢弃证据或空答案问题，按 partial 交付。")

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("finalized status=%s answers=%d evidence=%d dropped=%d caveats=%d"
          % (result["status"], len(answers),
             sum(len(x["evidence"]) for x in answers), len(dropped), len(caveats)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
