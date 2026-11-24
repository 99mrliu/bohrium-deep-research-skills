#!/usr/bin/env python3
"""run_minimal_example.py — 一键端到端运行合成示例。

在 bundle 根目录执行：
    python3 scripts/run_minimal_example.py

读取 examples/minimal/（case.json + materials/ + previous_snapshot.json，
全部为合成数据），依次运行 window_planner -> seam_proof -> date_normalize ->
assign_windows -> backfill -> assemble_result，产物写入 examples/minimal/output/，
并在结尾打印窗口链、backfill 事件与边界判定摘要；seam_proof 未全部通过时
以非零码退出。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
CASE_DIR = os.path.join(ROOT, "examples", "minimal")
OUT_DIR = os.path.join(CASE_DIR, "output")

import assemble_result  # noqa: E402
import assign_windows  # noqa: E402
import backfill  # noqa: E402
import date_normalize  # noqa: E402
import seam_proof  # noqa: E402
import window_planner  # noqa: E402
from window_common import load_json  # noqa: E402


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    p = lambda name: os.path.join(OUT_DIR, name)  # noqa: E731

    window_planner.main(["--case-dir", CASE_DIR, "--out", p("window_plan.json")])
    rc = seam_proof.main(["--plan", p("window_plan.json"), "--out", p("seam_proof.json")])
    date_normalize.main(["--case-dir", CASE_DIR, "--out", p("normalized_items.json")])
    assign_windows.main(["--case-dir", CASE_DIR, "--work-dir", OUT_DIR,
                         "--out", p("assigned_items.json")])
    backfill.main(["--work-dir", OUT_DIR, "--out", p("backfill_events.json")])
    assemble_result.main(["--case-dir", CASE_DIR, "--work-dir", OUT_DIR,
                          "--out", p("result.json")])

    plan = load_json(p("window_plan.json"))
    proof = load_json(p("seam_proof.json"))
    assigned = load_json(p("assigned_items.json"))
    bf = load_json(p("backfill_events.json"))

    print("\n==== 合成示例运行摘要 ====")
    print("窗口链（[start, end)，左闭右开）：")
    for w in plan["chain"]:
        print("  %-14s %s -> %s  [%s]" % (w["id"], w["start"], w["end"], w["status"]))
    print("接缝证明：overall_pass=%s" % proof["overall_pass"])
    for s in proof["seams"]:
        print("  %s  gap=%ss overlap=%ss pass=%s"
              % (s["seam"], s.get("gap_seconds"), s.get("overlap_seconds"), s.get("pass")))
    print("边界判定：")
    for r in assigned["items"]:
        if r.get("flags"):
            print("  %-28s -> %-18s flags=%s"
                  % (r.get("doi"), r.get("classification"), ",".join(r["flags"])))
    print("backfill 事件：%d 条" % bf["backfill_count"])
    for e in bf["events"]:
        print("  %s 原窗口=%s 延迟=%s天 原因=%s"
              % (e["doi"], e["original_window"], e["delay_days"], e["reason"]))
    print("产物目录：%s" % OUT_DIR)
    return 0 if proof["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
