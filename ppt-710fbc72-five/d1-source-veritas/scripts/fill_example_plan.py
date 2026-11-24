"""fill_example_plan.py — auto-complete slide_plan.json for the SYNTHETIC case.

Non-interactive example filler: every bullet/number/figure/quote is pulled
from the corpus ledger built by `prepare`, so the fidelity gate passes by
construction. In a real run the Agent performs this creative step instead.

Usage:
  python3 fill_example_plan.py --work /app/work
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _find(entries: list[dict], *keywords: str) -> tuple[dict | None, str | None]:
    """First corpus sentence containing ALL keywords (case-insensitive)."""
    for e in entries:
        if e.get("kind") != "text":
            continue
        for s in _sentences(e["text"]):
            low = s.lower()
            if all(k.lower() in low for k in keywords):
                return e, s
    return None, None


def fill(work: str) -> str:
    plan_path = os.path.join(work, "slide_plan.json")
    plan = common.load_json(plan_path)
    corpus_dir = plan.get("corpus_dir") or os.path.join(work, "corpus")
    entries = common.read_corpus(os.path.join(corpus_dir, "corpus.jsonl"))
    figures = [e for e in entries if e.get("kind") == "figure"]

    def fig(label_n: int) -> dict | None:
        for f in figures:
            if f.get("label") and re.search(rf"\b{label_n}\b", f["label"]):
                return {"ref": f["label"],
                        "path": os.path.join(corpus_dir, f["file"]),
                        "caption": f"{f['label']} (from corpus ledger, page {f['page']})"}
        return None

    # --- pull verbatim sentences from the corpus ----------------------------
    e_prob, s_prob = _find(entries, "diverge", "24")
    e_contrib, s_contrib = _find(entries, "corpus ledger", "fidelity gate")
    e_m1, s_m1 = _find(entries, "sha256", "bounding box")
    e_m2, s_m2 = _find(entries, "n = 128")
    e_m3, s_m3 = _find(entries, "3.6 seconds")
    e_r1, s_r1 = _find(entries, "92.4%", "87.1%")
    e_lim1, s_lim1 = _find(entries, "unit conversion", "4%")
    e_lim2, s_lim2 = _find(entries, "page break")
    e_concl, s_concl = _find(entries, "keeps slide numbers", "verbatim")
    title_entry = next((e for e in entries
                        if e.get("kind") == "text" and e["page"] == 1
                        and "VeritasNet" in e["text"]), None)

    def ev(entry, sentence, etype="page"):
        return {"type": etype, "ref": f"p.{entry['page']}",
                "quote": sentence[:400]} if entry and sentence else None

    f1, f2 = fig(1), fig(2)

    slides = [
        {"kind": "title",
         "title": (title_entry["text"].split("Authors")[0].strip()
                   if title_entry else "Synthetic Paper Talk"),
         "claim": "数字逐字、来源可查的学术汇报（合成示例）",
         "bullets": ["Synthetic demo for source-veritas-deck (合成示例)",
                     "Audience: lab meeting; 10 minutes"],
         "figures": [], "evidence": [], "notes":
             "开场：本报告由 source-veritas-deck 生成，所有数字均可回溯到语料台账。",
         "layout_hint": "Title Slide"},

        {"kind": "background",
         "title": "Background: numbers drift from sources",
         "claim": "Slide numbers frequently diverge from the source paper.",
         "bullets": [s_prob or "", s_contrib or ""],
         "figures": [],
         "evidence": [x for x in (ev(e_prob, s_prob), ev(e_contrib, s_contrib)) if x],
         "notes": "问题动机：试点审计 24 份合成 deck，7 份存在原文之外的数字。",
         "layout_hint": "Title and Content"},

        {"kind": "method",
         "title": "Method: corpus ledger + fidelity gate",
         "claim": "Every block and figure is hashed; every number is checked.",
         "bullets": [s_m1 or "", s_m2 or "", s_m3 or ""],
         "figures": [],
         "evidence": [x for x in (ev(e_m1, s_m1), ev(e_m2, s_m2),
                                  ev(e_m3, s_m3)) if x],
         "notes": "方法：sha256 台账 + 逐条核验；评估用 n = 128 页，抽取 3.6 秒/篇。",
         "layout_hint": "Title and Content"},

        {"kind": "results",
         "title": "Results: 92.4% detection accuracy",
         "claim": "The gate detects unfaithful numbers at 92.4% accuracy.",
         "bullets": [s_r1 or ""],
         "figures": [f for f in (f1, f2) if f],
         "evidence": [x for x in (ev(e_r1, s_r1),
                                  {"type": "figure", "ref": "Figure 1",
                                   "quote": ""},
                                  {"type": "figure", "ref": "Figure 2",
                                   "quote": ""}) if x],
         "notes": "结果：92.4% 对 87.1% 基线，提升 5.3 个点，p < 0.05，n = 128。",
         "layout_hint": "Title and Content"},

        {"kind": "discussion",
         "title": "Limitations",
         "claim": "Unit conversions and page-break quotes remain hard.",
         "bullets": [s_lim1 or "", s_lim2 or ""],
         "figures": [],
         "evidence": [x for x in (ev(e_lim1, s_lim1), ev(e_lim2, s_lim2)) if x],
         "notes": "局限：约 4% 需要单位换算的无法核验；跨页引文可能失败。",
         "layout_hint": "Title and Content"},

        {"kind": "conclusion",
         "title": "Conclusion",
         "claim": "Ledger + gate keeps slide numbers verbatim.",
         "bullets": [s_concl or ""],
         "figures": [],
         "evidence": [x for x in (ev(e_concl, s_concl),) if x],
         "notes": "结论：语料台账 + 逐条门禁，宁可少写，不可无据。",
         "layout_hint": "Title and Content"},
    ]

    for s in slides:
        s["bullets"] = [b for b in s["bullets"] if b and b.strip()]

    plan["mainline"] = {
        "problem": "slide numbers diverge from source papers",
        "method": "sha256 corpus ledger + per-claim fidelity gate",
        "results": "92.4% vs 87.1% baseline (p < 0.05, n = 128)",
        "limitations": "unit conversion (~4%) and page-break quotes"}
    plan["audience"] = "lab meeting (academic peers)"
    plan["duration_min"] = 10
    plan["slides"] = slides
    plan["filled_by"] = "fill_example_plan.py (synthetic, non-interactive)"
    common.dump_json(plan, plan_path)
    print(f"[fill_example_plan] filled {len(slides)} slides -> {plan_path}")
    return plan_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    fill(os.path.abspath(args.work))
    return 0


if __name__ == "__main__":
    sys.exit(main())
