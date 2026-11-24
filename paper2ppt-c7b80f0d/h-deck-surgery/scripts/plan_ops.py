#!/usr/bin/env python3
"""plan_ops.py — 汇总 probe + task + evidence，产出结构化手术建议骨架 ops_suggested.json。

用法:
    python3 plan_ops.py --probe probe_report.json --task task.md \
        --evidence evidence.json --suggest ops_suggested.json

本脚本不做决策：它只给出诊断（疑似占位标题、与证据不符的数值、缺备注页、
未被引用的 Figure/Table、页数预算）和候选动作清单；Agent 据此手工填写
ops_journal.json（schema 见 references/ops-schema.md）。
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_common as dc
from evidence_scan import UNIT_RE, N_COUNT_RE

PLACEHOLDER_TITLE_RE = re.compile(
    r"^\s*(TODO|TBD|SECTION[_ ]?HEADER|COLUMN[_ ]?NAME|TITLE[_ ]?PLACEHOLDER|"
    r"UNTITLED|CLICK TO ADD|LOREM|XXX+)\s*$",
    re.IGNORECASE,
)


def parse_max_slides(task_text: str) -> int | None:
    m = re.search(r"[≤<=]{1,2}\s*(\d+)\s*(?:页|pages?|slides?)", task_text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:页|slides?)\s*(?:上限|以内|max)", task_text)
    if m:
        return int(m.group(1))
    m = re.search(r"max(?:imum)?\s*(?:of)?\s*(\d+)\s*slides?", task_text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成手术建议骨架 ops_suggested.json（空 ops 模板 + 诊断）")
    ap.add_argument("--probe", required=True, help="deck_probe.py 产物")
    ap.add_argument("--task", required=True, help="task.md 路径")
    ap.add_argument("--evidence", required=True, help="evidence_scan.py 产物")
    ap.add_argument("--suggest", required=True, help="输出 ops_suggested.json 路径")
    args = ap.parse_args(argv)

    for p in (args.probe, args.task, args.evidence):
        if not os.path.exists(p):
            print(f"error: input not found: {p}", file=sys.stderr)
            return 2
    probe = dc.load_json(args.probe)
    evidence = dc.load_json(args.evidence)
    with open(args.task, "r", encoding="utf-8") as f:
        task_text = f.read()

    max_slides = parse_max_slides(task_text)
    ev_values = {(n["value"], n["unit"]) for n in evidence.get("numbers", [])}

    diagnostics, candidates = [], []
    for s in probe.get("slides", []):
        idx = s["index"]
        title = s.get("title") or ""
        body = s.get("body_preview") or ""
        if PLACEHOLDER_TITLE_RE.match(title):
            diagnostics.append(
                {"slide": idx, "kind": "placeholder_title",
                 "detail": f"title {title!r} looks like a placeholder/column name"}
            )
            candidates.append({"slide": idx, "op": "set_title",
                               "why": "replace placeholder title with a real section title"})
        # 页内数值与证据比对：页面上出现但证据中不存在的带单位数值 → 疑似错数值
        slide_values = [(m.group(1), m.group(2)) for m in UNIT_RE.finditer(body)]
        slide_values += [(m.group(1), "count(n)") for m in N_COUNT_RE.finditer(body)]
        for pair in slide_values:
            if pair not in ev_values:
                diagnostics.append(
                    {"slide": idx, "kind": "value_mismatch",
                     "detail": f"value {pair[0]} {pair[1]} not found in evidence numbers"}
                )
                candidates.append({"slide": idx, "op": "replace_text",
                                   "why": f"verify {pair[0]} {pair[1]} against paper; "
                                          f"replace with the evidenced value if wrong"})
        if not s.get("notes_present"):
            candidates.append({"slide": idx, "op": "set_notes",
                               "why": "slide has no speaker notes"})

    slide_titles_blob = " ".join(
        (s.get("title") or "") + " " + (s.get("body_preview") or "")
        for s in probe.get("slides", [])
    )
    for cap in evidence.get("captions", []):
        if cap["label"] not in slide_titles_blob:
            diagnostics.append(
                {"slide": None, "kind": "caption_unreferenced",
                 "detail": f"{cap['label']} (page {cap['page']}) not referenced on any slide"}
            )
            candidates.append({"slide": None, "op": "insert_slide/add_figure",
                               "why": f"consider covering {cap['label']} within page budget"})

    n = probe.get("slide_count", 0)
    if max_slides is not None:
        diagnostics.append(
            {"slide": None, "kind": "page_budget",
             "detail": f"current {n} slides, task limit <= {max_slides}; "
                       f"insertions allowed up to {max_slides - n} if all current slides stay"}
        )

    suggested = {
        "mode": "edit",
        "base_deck": probe.get("deck"),
        "max_slides": max_slides,
        "slide_count": n,
        "diagnostics": diagnostics,
        "candidates": candidates,
        "op_template": {
            "op_id": "op-NNN (unique, stable across reruns)",
            "op": "set_title|replace_text|set_bullets|insert_slide|delete_slide|move_slide|set_notes|add_figure",
            "slide": "1-based slide number in the deck state WHEN THE OP IS APPLIED",
            "params": "see references/ops-schema.md",
            "reason": "mandatory: why this change, citing evidence/task",
        },
        "ops": [],
        "note": "Agent fills ops[] into ops_journal.json; this file is advice only.",
    }
    dc.dump_json(suggested, args.suggest)
    print(
        f"plan ok: diagnostics={len(diagnostics)} candidates={len(candidates)} "
        f"max_slides={max_slides} -> {args.suggest}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
