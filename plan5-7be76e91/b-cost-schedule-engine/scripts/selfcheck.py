#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 端到端自查（确定性，仅标准库）。

对 examples/ 全流程做真实运行校验：
  1. 三份好 plan_record（P1/P2/P3）：cost_ledger + time_model 均 exit 0。
  2. pareto exit 0；P3 被 P1 支配（支配关系精确命中）；推荐与 rule_source 非空。
  3. 三份坏例分别 exit 3 且缺陷精确命中：
     - plan_record_bad_missing_price.json -> cost_ledger 捕获「缺 unit_price」
     - plan_record_bad_overbudget.json    -> time_model 捕获 over_budget 门
     - plan_record_bad_probability.json   -> time_model 捕获「rework_probability 必须在 [0,1]」
  4. Decimal 精确性：P1 台账耗材小计恰为 "0.3"（0.1 + 0.2，无浮点尾差）。
  5. 双跑字节一致：完整流程跑两遍到两个临时目录，逐文件 bytes 比对。

退出码：0=全部通过；2=用法/环境错误；3=任一校验失败（明细写 stdout）。
"""
import argparse
import filecmp
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BUNDLE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = BUNDLE_DIR / "scripts"
EXAMPLES = BUNDLE_DIR / "examples"
CASE = EXAMPLES / "case.example.json"
GOOD_PLANS = ["P1", "P2", "P3"]


def run(cmd):
    return subprocess.run([sys.executable] + [str(c) for c in cmd],
                          capture_output=True, text=True)


def pipeline(out_dir, plan_file, plan_id, case=CASE, ledger_for_time=True):
    """跑 cost_ledger + time_model，返回 (ledger_rc, ledger_out, time_rc, time_out, ledger_path, time_path)。"""
    ledger_path = out_dir / ("ledger_%s.json" % plan_id)
    r1 = run([SCRIPTS / "cost_ledger.py", "--plan", plan_file, "--out-dir", out_dir])
    t_cmd = [SCRIPTS / "time_model.py", "--plan", plan_file, "--out-dir", out_dir]
    if case is not None:
        t_cmd += ["--case", case]
    if ledger_for_time and r1.returncode == 0:
        t_cmd += ["--ledger", ledger_path]
    r2 = run(t_cmd)
    return r1, r2, ledger_path, out_dir / ("time_%s.json" % plan_id)


def full_run(out_dir):
    """完整好例流程 + pareto。返回 dict of results。"""
    res = {}
    for pid in GOOD_PLANS:
        plan_file = EXAMPLES / ("plan_record_%s.json" % pid)
        r1, r2, lp, tp = pipeline(out_dir, plan_file, pid)
        res[pid] = {"ledger_rc": r1.returncode, "ledger_out": r1.stdout,
                    "time_rc": r2.returncode, "time_out": r2.stdout,
                    "ledger": lp, "time": tp}
    plan_args = [arg for pid in GOOD_PLANS
                 for arg in ("--plan", "%s:%s:%s" % (pid, res[pid]["ledger"], res[pid]["time"]))]
    rp = run([SCRIPTS / "pareto.py", "--out-dir", out_dir, "--case", CASE] + plan_args)
    res["pareto"] = {"rc": rp.returncode, "out": rp.stdout,
                     "json": out_dir / "pareto.json"}
    return res


def dirs_identical(d1, d2):
    c1 = sorted(p.relative_to(d1) for p in d1.rglob("*") if p.is_file())
    c2 = sorted(p.relative_to(d2) for p in d2.rglob("*") if p.is_file())
    if c1 != c2:
        return False, "文件列表不同: %s vs %s" % (c1, c2)
    for rel in c1:
        if not filecmp.cmp(d1 / rel, d2 / rel, shallow=False):
            return False, "字节不一致: %s" % rel
    return True, ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="端到端自查：examples 全流程 + 坏例捕获 + 双跑字节一致")
    ap.add_argument("--keep-dir", help="把自查产物保留到指定目录（默认用临时目录）")
    args = ap.parse_args(argv)

    failures = []

    def check(ok, label, detail=""):
        sys.stdout.write("%s %s%s\n" % ("PASS" if ok else "FAIL", label,
                                        (" | " + detail) if detail else ""))
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory(prefix="cse_selfcheck_") as tmp:
        tmp = Path(tmp)
        run_a = Path(args.keep_dir) if args.keep_dir else tmp / "run_a"
        run_b = tmp / "run_b"
        run_a.mkdir(parents=True, exist_ok=True)
        run_b.mkdir(parents=True, exist_ok=True)

        # ---- 1. 好例 exit 0 ----
        res_a = full_run(run_a)
        for pid in GOOD_PLANS:
            r = res_a[pid]
            check(r["ledger_rc"] == 0, "ledger %s exit 0" % pid,
                  "rc=%d %s" % (r["ledger_rc"], r["ledger_out"].strip().splitlines()[-1:]
                                if r["ledger_out"].strip() else ""))
            check(r["time_rc"] == 0, "time %s exit 0" % pid,
                  "rc=%d" % r["time_rc"])

        # ---- 2. pareto 与支配关系 ----
        check(res_a["pareto"]["rc"] == 0, "pareto exit 0",
              "rc=%d" % res_a["pareto"]["rc"])
        pareto = json.loads(res_a["pareto"]["json"].read_text(encoding="utf-8"))
        p3 = next((p for p in pareto["plans"] if p["plan_id"] == "P3"), None)
        check(p3 is not None and p3["dominated"] and "P1" in p3["dominated_by"],
              "P3 被 P1 支配", "dominated_by=%s" % (p3 and p3["dominated_by"]))
        check(bool(pareto["recommendation"]) and bool(pareto["rule_source"]),
              "推荐非空且声明 rule_source",
              "rec=%s rule=%s" % (pareto["recommendation"], pareto["rule_source"]))

        # ---- 3. 坏例精确捕获 ----
        r1, r2, _, _ = pipeline(tmp / "bad_price",
                                EXAMPLES / "plan_record_bad_missing_price.json", "BADPRICE")
        check(r1.returncode == 3 and "缺 unit_price" in r1.stdout,
              "坏例1 缺单价 exit 3 且命中", "rc=%d" % r1.returncode)

        r1, r2, _, _ = pipeline(tmp / "bad_budget",
                                EXAMPLES / "plan_record_bad_overbudget.json", "BADBUDGET")
        check(r1.returncode == 0 and r2.returncode == 3 and "over_budget" in r2.stdout,
              "坏例2 超预算 exit 3 且命中 over_budget",
              "ledger_rc=%d time_rc=%d" % (r1.returncode, r2.returncode))

        r1, r2, _, _ = pipeline(tmp / "bad_prob",
                                EXAMPLES / "plan_record_bad_probability.json", "BADPROB")
        check(r2.returncode == 3 and "rework_probability" in r2.stdout,
              "坏例3 非法概率 exit 3 且命中", "rc=%d" % r2.returncode)

        # ---- 4. Decimal 精确性：0.1 x 7 == 0.7 精确（float 得 0.7000000000000001），
        #         耗材小计 0.7+0.2+480 == 480.9 精确（float 得 480.8999999999999...）----
        ledger_p1 = json.loads(res_a["P1"]["ledger"].read_text(encoding="utf-8"))
        membrane = next((it for it in ledger_p1["items"] if it["name"] == "微量滤膜"), None)
        check(membrane is not None and membrane["line_total"] == "0.7",
              "Decimal 精确: 微量滤膜 0.1x7 == '0.7'（float 会得 0.7000000000000001）",
              "actual=%r" % (membrane and membrane["line_total"]))
        consumable = ledger_p1["subtotals_by_category"].get("耗材")
        check(consumable == "480.9", "Decimal 精确: 耗材小计 == '480.9'（无浮点尾差）",
              "actual=%r" % consumable)

        # ---- 5. 双跑字节一致 ----
        full_run(run_b)
        same, why = dirs_identical(run_a, run_b)
        check(same, "双跑字节一致", why)

    if failures:
        sys.stdout.write("SELFCHECK FAILED: %d 项未过 -> %s\n" % (len(failures), failures))
        return 3
    sys.stdout.write("SELFCHECK OK: 全部校验通过\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
