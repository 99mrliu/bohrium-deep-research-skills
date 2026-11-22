#!/usr/bin/env python3
"""plan_scaffold.py — Step 3 of contract-gate-slides.

Allocate narrative roles across the requested slide count and emit a
plan.json skeleton. The agent then edits plan.json in place (titles,
bullets with anchors, figure picks, speaker notes) reading ONLY
paper_digest.md — not the full paper.

Output: $WORK/plan.json
"""
import json, os

WORK = os.environ.get("CASE_WORK_DIR", "/app/work")


def allocate_roles(n, required):
    """Return a list of n roles covering all required roles."""
    req = [r for r in required if r not in ("title",)]
    roles = ["title"]
    body = n - 1
    # guarantee required roles first (keep order background..conclusion)
    order = ["background", "method", "result", "comparison", "limitation", "conclusion"]
    core = [r for r in order if r in req]
    for r in core:
        if body > 0:
            roles.append(r)
            body -= 1
    # distribute the remaining slots by narrative weight
    weights = [("background", 0.15), ("method", 0.30), ("result", 0.40),
               ("limitation", 0.05), ("conclusion", 0.10)]
    extra = []
    for r, w in weights:
        extra += [r] * max(0, round(body * w) - (1 if r == "background" else 0))
    while len(roles) - 1 + len(extra) < n - 1:
        extra.append("result")
    # interleave extras after their first occurrence
    for r in extra:
        idx = max((i for i, x in enumerate(roles) if x == r), default=0)
        roles.insert(idx + 1, r)
    roles = roles[:n]
    while len(roles) < n:
        roles.insert(-1, "result")
    return roles


def main():
    brief = json.load(open(os.path.join(WORK, "case_brief.json"), encoding="utf-8"))
    figs = json.load(open(os.path.join(WORK, "paper_figs.json"), encoding="utf-8"))
    n = brief["slide_count"]
    roles = allocate_roles(n, brief.get("required_roles") or [])
    ok_figs = [f["id"] for f in figs if f.get("crop_status") == "ok"]
    plan = {
        "_schema": {
            "slide": "页码 1..N（勿改）",
            "role": "title/background/method/result/comparison/limitation/conclusion（勿改）",
            "title": "页标题，≤20 字，概括本页主张而非泛词",
            "bullets": [{"text": "≤60 中文字符；数字必须与论文一致", "anchor": "p<页码> 或 <figN>/<tabN>"}],
            "figure": f"可选，只能取已裁剪: {ok_figs}；否则 null",
            "notes": "演讲备注 1-3 句（讲稿交付物），不写套话",
        },
        "case_id": brief["case_id"],
        "audience": brief["audience"],
        "time_minutes": brief["time_minutes"],
        "slides": [
            {"slide": i + 1, "role": roles[i], "title": "",
             "bullets": [{"text": "", "anchor": ""}],
             "figure": None, "notes": ""}
            for i in range(n)
        ],
    }
    with open(os.path.join(WORK, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(json.dumps({"slides": n, "roles": roles, "figures_available": ok_figs},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
