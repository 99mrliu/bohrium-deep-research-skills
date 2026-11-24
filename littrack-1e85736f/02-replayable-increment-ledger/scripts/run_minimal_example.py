#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_minimal_example.py — 一键端到端运行 examples/minimal 合成示例（仅标准库）。

在 bundle 根目录执行：
    python3 scripts/run_minimal_example.py

流程（全部产物写入 examples/minimal/output/）：
  0. 复制 materials/previous_journal.jsonl 与 previous_snapshot.json 作为初始状态；
  1. 第 1 轮 record_run（建立本轮 journal 记录）；
  2. 第 2 轮 record_run（含新增 + 跨源重复 + 标题差异重复 + 预印本→正式版版本链）；
  3. replayer 回放第 1、2 轮 -> replay_diff_round{1,2}.json；
  4. idempotency_check 校验第 2 轮 -> idempotency_report.json；
  5. assemble_result -> result.json；
  6. 打印 PASS/FAIL 摘要；任一环节失败以非零码退出。
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EX = os.path.join(ROOT, "examples", "minimal")
MAT = os.path.join(EX, "materials")
OUT = os.path.join(EX, "output")


def rel(p):
    return os.path.relpath(p, ROOT)


def run(cmd, label):
    print("== [%s] %s" % (label, " ".join(rel(c) if c.startswith(ROOT) else c for c in cmd)))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.stdout.strip():
        print("   stdout: %s" % proc.stdout.strip())
    if proc.returncode != 0:
        print("   stderr: %s" % proc.stderr.strip()[-2000:])
        raise SystemExit("步骤失败: %s (exit %d)" % (label, proc.returncode))
    return proc


def main():
    os.makedirs(OUT, exist_ok=True)
    # 清理上一轮产物（仅清理本脚本自己生成的文件）
    for name in os.listdir(OUT):
        os.remove(os.path.join(OUT, name))

    journal = os.path.join(OUT, "increment_journal.jsonl")
    snap_prev = os.path.join(OUT, "snapshot_prev.json")
    snap_r1 = os.path.join(OUT, "snapshot_round1.json")
    snap_r2 = os.path.join(OUT, "snapshot_round2.json")
    shutil.copyfile(os.path.join(MAT, "previous_journal.jsonl"), journal)
    shutil.copyfile(os.path.join(MAT, "previous_snapshot.json"), snap_prev)

    case = rel(os.path.join(EX, "case.json"))
    with open(os.path.join(EX, "case.json"), "r", encoding="utf-8") as f:
        case_doc = json.load(f)
    w1 = case_doc["windows"]["round1"]
    w2 = case_doc["windows"]["round2"]

    py = sys.executable
    record = os.path.join(HERE, "record_run.py")
    replay = os.path.join(HERE, "replayer.py")
    idem = os.path.join(HERE, "idempotency_check.py")
    assemble = os.path.join(HERE, "assemble_result.py")

    sum1 = os.path.join(OUT, "run_round1_summary.json")
    sum2 = os.path.join(OUT, "run_round2_summary.json")

    # ---- 第 1 轮：建立 journal ----
    run([py, record, "--case", case,
         "--window-start", w1["start_utc"], "--window-end", w1["end_utc"],
         "--source", "crossref=" + rel(os.path.join(MAT, "round1_crossref.json")),
         "--source", "arxiv=" + rel(os.path.join(MAT, "round1_arxiv.json")),
         "--journal", rel(journal),
         "--snapshot-in", rel(snap_prev), "--snapshot-out", rel(snap_r1),
         "--run-summary", rel(sum1)], "round1 record")

    # ---- 第 2 轮：新增 + 重复 + 版本更新 ----
    run([py, record, "--case", case,
         "--window-start", w2["start_utc"], "--window-end", w2["end_utc"],
         "--source", "crossref=" + rel(os.path.join(MAT, "round2_crossref.json")),
         "--source", "arxiv=" + rel(os.path.join(MAT, "round2_arxiv.json")),
         "--journal", rel(journal),
         "--snapshot-in", rel(snap_r1), "--snapshot-out", rel(snap_r2),
         "--run-summary", rel(sum2)], "round2 record")

    with open(sum1, "r", encoding="utf-8") as f:
        run1_id = json.load(f)["run_id"]
    with open(sum2, "r", encoding="utf-8") as f:
        run2_id = json.load(f)["run_id"]

    # ---- 回放两轮 ----
    rd1 = os.path.join(OUT, "replay_diff_round1.json")
    rd2 = os.path.join(OUT, "replay_diff_round2.json")
    run([py, replay, "--journal", rel(journal), "--run-id", run1_id,
         "--snapshot", rel(snap_prev),
         "--source", "crossref=" + rel(os.path.join(MAT, "round1_crossref.json")),
         "--source", "arxiv=" + rel(os.path.join(MAT, "round1_arxiv.json")),
         "--case", case, "--out", rel(rd1)], "replay round1")
    run([py, replay, "--journal", rel(journal), "--run-id", run2_id,
         "--snapshot", rel(snap_r1),
         "--source", "crossref=" + rel(os.path.join(MAT, "round2_crossref.json")),
         "--source", "arxiv=" + rel(os.path.join(MAT, "round2_arxiv.json")),
         "--case", case, "--out", rel(rd2)], "replay round2")

    # ---- 幂等校验第 2 轮 ----
    idem_path = os.path.join(OUT, "idempotency_report.json")
    run([py, idem, "--case", case,
         "--window-start", w2["start_utc"], "--window-end", w2["end_utc"],
         "--source", "crossref=" + rel(os.path.join(MAT, "round2_crossref.json")),
         "--source", "arxiv=" + rel(os.path.join(MAT, "round2_arxiv.json")),
         "--journal", rel(journal), "--snapshot-in", rel(snap_r1),
         "--out", rel(idem_path)], "idempotency round2")

    # ---- 组装 result.json ----
    result_path = os.path.join(OUT, "result.json")
    run([py, assemble, "--case", case, "--journal", rel(journal),
         "--run-summary", rel(sum1), "--run-summary", rel(sum2),
         "--replay-diff", rel(rd1), "--replay-diff", rel(rd2),
         "--idempotency", rel(idem_path),
         "--snapshot-prev", rel(snap_r1), "--snapshot-new", rel(snap_r2),
         "--out", rel(result_path)], "assemble result.json")

    # ---- 摘要 ----
    def status_of(path, key="status"):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get(key)

    print("\n================ 合成示例运行摘要 ================")
    print("round1 run_id: %s" % run1_id)
    print("round2 run_id: %s" % run2_id)
    print("replay round1: %s" % status_of(rd1))
    print("replay round2: %s" % status_of(rd2))
    print("idempotency  : %s" % status_of(idem_path))
    print("result.json  : status=%s" % status_of(result_path))
    ok = (status_of(rd1) == "consistent" and status_of(rd2) == "consistent"
          and status_of(idem_path) == "pass" and status_of(result_path) == "complete")
    print("OVERALL: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
