#!/usr/bin/env python3
"""run_minimal_example.py — 合成示例三阶段端到端演示（离线，仅标准库）。

在 bundle 根目录运行：
    python3 scripts/run_minimal_example.py

三阶段（产物写入 examples/minimal/output/）：
  第 1 次运行：源 eupmc_b 的材料是截断 JSON（parse_error）-> 3 次尝试记入
               retry_journal、断点保存、eupmc_b 降级、result_run1 partial；
  第 2 次运行：源 eupmc_b 已修复 -> 从 checkpoint 续跑，crossref_a 与
               publisher_c 直接跳过，只补 eupmc_b，result_run2 status=ok；
  第 3 次运行：什么都不变 -> 全部源命中 checkpoint，零新 journal 事件、
               零新投递（幂等校验），另做一次「重复投递抑制」自检。

每次执行都会先重置 output/ 并把 materials/source_b.json 还原为损坏版，
因此本脚本可反复执行，结果一致。
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assemble_result
import delivery_dedup as dd
import retry_engine

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(BUNDLE_ROOT, "examples", "minimal")
CASE = os.path.join(EX, "case.json")
MAT_B = os.path.join(EX, "materials", "source_b.json")
MAT_B_BROKEN = os.path.join(EX, "materials", "source_b_broken.json")
MAT_B_FIXED = os.path.join(EX, "materials", "source_b_fixed.json")
OUT = os.path.join(EX, "output")
WORK = os.path.join(OUT, "work")


def line_count(path):
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check(cond, msg):
    print(("  [PASS] " if cond else "  [FAIL] ") + msg)
    return cond


def main():
    print("== 阶段 0：重置示例环境 ==")
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(WORK)
    shutil.copyfile(MAT_B_BROKEN, MAT_B)
    print("  output/ 已重置；materials/source_b.json <- 损坏版")

    journal = os.path.join(WORK, "retry_journal.jsonl")
    dlog = os.path.join(WORK, "delivery_log.jsonl")
    ok_all = True

    print("\n== 第 1 次运行：源 eupmc_b 截断（parse_error） ==")
    retry_engine.run_case(CASE, WORK)
    r1 = assemble_result.assemble(CASE, WORK,
                                  os.path.join(OUT, "result_run1.json"))
    ok_all &= check(r1["status"] == "partial",
                    "run1 status=partial（实际 %s）" % r1["status"])
    ok_all &= check(any(d["source"] == "eupmc_b"
                        and d["failure_class"] == "parse_error"
                        for d in r1["degraded_sources"]),
                    "run1 degraded_sources 含 eupmc_b/parse_error")
    j1 = line_count(journal)
    d1 = line_count(dlog)
    ok_all &= check(j1 == 5,
                    "run1 journal 共 5 条尝试（a:1 + b:3 + c:1，实际 %d）" % j1)
    ok_all &= check(line_count(os.path.join(WORK, "runs.jsonl")) == 1,
                    "run1 runs.jsonl 1 条")
    print("  run1: journal=%d 条, deliveries=%d 条" % (j1, d1))

    print("\n== 第 2 次运行：源 eupmc_b 已修复，从 checkpoint 续跑 ==")
    shutil.copyfile(MAT_B_FIXED, MAT_B)
    print("  materials/source_b.json <- 修复版")
    retry_engine.run_case(CASE, WORK)
    r2 = assemble_result.assemble(CASE, WORK,
                                  os.path.join(OUT, "result_run2.json"))
    ok_all &= check(r2["status"] == "ok",
                    "run2 status=ok（实际 %s）" % r2["status"])
    ok_all &= check(not r2["degraded_sources"], "run2 degraded_sources 为空")
    j2, d2 = line_count(journal), line_count(dlog)
    ok_all &= check(j2 - j1 == 1,
                    "run2 仅新增 1 条 journal（只补 eupmc_b，实际 +%d）"
                    % (j2 - j1))
    ok_all &= check(d2 - d1 == 1,
                    "run2 仅新增 1 条投递（eupmc_b 修复版中 1 条完整记录，"
                    "实际 +%d）" % (d2 - d1))
    cp2 = load_json(os.path.join(WORK, "checkpoint.json"))
    ok_all &= check(len(cp2["completed"]) == 3 and not cp2["degraded"],
                    "run2 checkpoint 三个源全部 completed、无 degraded")

    print("\n== 第 3 次运行：幂等重跑 ==")
    retry_engine.run_case(CASE, WORK)
    r3 = assemble_result.assemble(CASE, WORK,
                                  os.path.join(OUT, "result_run3.json"))
    j3, d3 = line_count(journal), line_count(dlog)
    ok_all &= check(j3 == j2, "run3 零新 journal 事件（%d -> %d）" % (j2, j3))
    ok_all &= check(d3 == d2, "run3 零新投递（%d -> %d）" % (d2, d3))
    ok_all &= check(r3["status"] == "ok", "run3 status 保持 ok")

    # 重复投递抑制自检：模拟「已投递未写 checkpoint 即崩溃」后的重投递
    sample = dd.read_all(dlog)[0]
    dup = dict(sample)
    suppressed = not dd.append_if_new(dlog, dup)
    ok_all &= check(suppressed and line_count(dlog) == d3,
                    "重复投递键 %s 被抑制，账本行数不变" % sample["delivery_key"])

    report = {
        "phases": {
            "run1": {"status": r1["status"], "journal_entries": j1,
                     "deliveries": d1,
                     "degraded": [d["source"] for d in r1["degraded_sources"]]},
            "run2": {"status": r2["status"],
                     "new_journal_entries": j2 - j1,
                     "new_deliveries": d2 - d1},
            "run3": {"status": r3["status"],
                     "new_journal_entries": j3 - j2,
                     "new_deliveries": d3 - d2},
        },
        "duplicate_delivery_suppressed": suppressed,
        "verdict": "idempotent" if (j3 == j2 and d3 == d2 and suppressed)
                   else "NOT idempotent",
        "all_checks_passed": bool(ok_all),
    }
    with open(os.path.join(OUT, "idempotency_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    # 最终交付：第 3 次运行的结果即 result.json
    shutil.copyfile(os.path.join(OUT, "result_run3.json"),
                    os.path.join(OUT, "result.json"))

    print("\n== 幂等校验结论: %s；全部自检 %s ==" %
          (report["verdict"], "通过" if ok_all else "存在失败"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
