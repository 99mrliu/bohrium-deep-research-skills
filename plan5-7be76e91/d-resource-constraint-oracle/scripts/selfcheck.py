#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — bundle 自查：examples 全流程正例/负例精确命中 + 双跑字节一致。

检查项（全部通过才 exit 0）：
  1. 正例 facts.example.json：
     - constraints.py  exit 0；P1=feasible_now；P2=feasible_after(2026-01-31)；
       P3=infeasible 且 blocking 违例含 parameter_window_conflict；
     - window_check.py exit 3（P3/temperature_C 空交集精确命中）；
     - timeline.py    exit 0；P1 finish=2026-01-10；P2 start=2026-01-15 /
       first_execution=2026-01-31 / finish=2026-02-06 / past_deadline=False；
       P3=skipped_infeasible。
  2. 负例 facts_all_infeasible.json：
     - constraints.py exit 3（设备档期全占 / 耗材货期超期 / 参数空交集 → 全部 infeasible），
       且 relax_hints 覆盖每个 blocking 违例；
     - timeline.py（带 constraints 报告）exit 3。
  3. 确定性：constraints.py 与 timeline.py 各双跑，产物逐字节一致。

退出码：0 = 全部通过；2 = 用法/输入错误；3 = 存在失败项（缺陷清单写 stdout）。
运行中间产物写入系统临时目录，不污染 examples/outputs/。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

FAILURES = []


def run(script, args, expect_rc, label):
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, script)] + args
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != expect_rc:
        FAILURES.append("%s：期望退出码 %d，实际 %d。stderr: %s"
                        % (label, expect_rc, p.returncode, p.stderr.strip()[:400]))
        return None
    print("PASS rc: %s (exit %d)" % (label, p.returncode))
    return p


def load_json(path, label):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        FAILURES.append("%s：无法读取 %s：%s" % (label, path, e))
        return None


def check(cond, label):
    if cond:
        print("PASS: %s" % label)
    else:
        FAILURES.append("FAIL: %s" % label)
        print("FAIL: %s" % label)


def dir_bytes(d):
    out = {}
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                out[name] = f.read()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="bundle 自查：正例/负例精确命中 + 双跑字节一致。")
    ap.add_argument("--examples-dir",
                    default=os.path.normpath(os.path.join(SCRIPT_DIR, "..", "examples")),
                    help="examples 目录（默认 ../examples）")
    args = ap.parse_args(argv)
    ex = os.path.abspath(args.examples_dir)
    facts_main = os.path.join(ex, "facts.example.json")
    facts_bad = os.path.join(ex, "facts_all_infeasible.json")
    case = os.path.join(ex, "case.example.json")
    for p in (facts_main, facts_bad, case):
        if not os.path.isfile(p):
            print("输入错误：缺少 %s" % p, file=sys.stderr)
            return 2

    tmp = tempfile.mkdtemp(prefix="rco-selfcheck-")
    out_c1 = os.path.join(tmp, "c1")
    out_c2 = os.path.join(tmp, "c2")
    out_w = os.path.join(tmp, "w")
    out_t1 = os.path.join(tmp, "t1")
    out_t2 = os.path.join(tmp, "t2")
    out_cb = os.path.join(tmp, "cb")
    out_tb = os.path.join(tmp, "tb")

    # ---- 1. 正例 ----
    run("constraints.py", ["--facts", facts_main, "--case", case, "--out-dir", out_c1],
        0, "正例 constraints")
    rep = load_json(os.path.join(out_c1, "constraints_report.json"), "正例 constraints 报告")
    if rep:
        by_id = {p["plan_id"]: p for p in rep["plans"]}
        check(by_id.get("P1", {}).get("verdict") == "feasible_now", "P1 verdict == feasible_now")
        check(by_id.get("P2", {}).get("verdict") == "feasible_after"
              and by_id["P2"].get("feasible_after") == "2026-01-31",
              "P2 verdict == feasible_after(2026-01-31)")
        p3 = by_id.get("P3", {})
        check(p3.get("verdict") == "infeasible"
              and any(v["type"] == "parameter_window_conflict" and v["blocking"]
                      for v in p3.get("violations", [])),
              "P3 infeasible 且 blocking 含 parameter_window_conflict")
        check(rep.get("all_infeasible") is False, "正例 all_infeasible == False")

    run("window_check.py", ["--facts", facts_main, "--case", case, "--out-dir", out_w],
        3, "负例命中 window_check（P3 空交集 → exit 3）")
    wrep = load_json(os.path.join(out_w, "window_report.json"), "window 报告")
    if wrep:
        check(wrep.get("empty_intersections") == [{"plan_id": "P3", "parameter": "temperature_C"}],
              "空交集精确为 P3/temperature_C")

    run("timeline.py", ["--facts", facts_main, "--case", case, "--out-dir", out_t1,
                        "--constraints", os.path.join(out_c1, "constraints_report.json")],
        0, "正例 timeline")
    trep = load_json(os.path.join(out_t1, "timeline_report.json"), "timeline 报告")
    if trep:
        by_id = {p["plan_id"]: p for p in trep["plans"]}
        p1, p2, p3 = by_id.get("P1", {}), by_id.get("P2", {}), by_id.get("P3", {})
        check(p1.get("earliest_start") == "2026-01-05"
              and p1.get("earliest_finish") == "2026-01-10"
              and p1.get("past_deadline") is False,
              "P1 时间线 2026-01-05 → 2026-01-10，未超期")
        check(p2.get("earliest_start") == "2026-01-15"
              and p2.get("first_execution_start") == "2026-01-31"
              and p2.get("earliest_finish") == "2026-02-06"
              and p2.get("past_deadline") is False,
              "P2 时间线 start=2026-01-15 / exec=2026-01-31 / finish=2026-02-06，未超期")
        check(any(w.get("kind") == "equipment_booking" and w.get("wait_until") == "2026-01-31"
                  for w in p2.get("critical_waits", [])),
              "P2 关键等待项含 PRESS-01 档期顺延至 2026-01-31")
        check(p3.get("status") == "skipped_infeasible", "P3 skipped_infeasible")

    # ---- 2. 负例：全部不可行 ----
    run("constraints.py", ["--facts", facts_bad, "--case", case, "--out-dir", out_cb],
        3, "负例 constraints（全部 infeasible → exit 3）")
    brep = load_json(os.path.join(out_cb, "constraints_report.json"), "负例 constraints 报告")
    if brep:
        check(brep.get("all_infeasible") is True, "负例 all_infeasible == True")
        hints = brep.get("relax_hints", {})
        ok = True
        for p in brep.get("plans", []):
            n_block = sum(1 for v in p["violations"] if v["blocking"])
            n_hint = len(hints.get(p["plan_id"], []))
            if n_block == 0 or n_hint != n_block:
                ok = False
        check(ok, "relax_hints 覆盖全部 blocking 违例（数量一一对应且非空）")
        vtypes = {v["type"] for p in brep["plans"] for v in p["violations"] if v["blocking"]}
        check({"equipment_booking_conflict", "consumable_lead_time_exceeded",
               "parameter_window_conflict"} <= vtypes,
              "负例覆盖三类 blocking：档期全占 / 货期超期 / 参数空交集")

    run("timeline.py", ["--facts", facts_bad, "--case", case, "--out-dir", out_tb,
                        "--constraints", os.path.join(out_cb, "constraints_report.json")],
        3, "负例 timeline（无可排方案 → exit 3）")

    # ---- 3. 双跑字节一致 ----
    run("constraints.py", ["--facts", facts_main, "--case", case, "--out-dir", out_c2],
        0, "正例 constraints 第二跑")
    run("timeline.py", ["--facts", facts_main, "--case", case, "--out-dir", out_t2,
                        "--constraints", os.path.join(out_c2, "constraints_report.json")],
        0, "正例 timeline 第二跑")
    if os.path.isdir(out_c1) and os.path.isdir(out_c2):
        check(dir_bytes(out_c1) == dir_bytes(out_c2), "constraints.py 双跑字节一致")
    if os.path.isdir(out_t1) and os.path.isdir(out_t2):
        check(dir_bytes(out_t1) == dir_bytes(out_t2), "timeline.py 双跑字节一致")

    print("")
    if FAILURES:
        print("自查失败 %d 项：" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 3
    print("自查全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
