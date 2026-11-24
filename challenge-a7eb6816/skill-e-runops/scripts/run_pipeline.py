#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_pipeline.py — 通用分阶段运行器（仅 Python 3 标准库）。

读取 pipeline_plan.json：
  {
    "case": "case.json",               # 相对 root，供保底 init 使用
    "workdir": "work",                 # checkpoint 与日志目录，相对 root
    "outdir": "output",                # result.json 所在目录，相对 root
    "warn_threshold": {"stage_seconds": 30, "total_seconds": 120},
    "stages": [
      {"name": "...", "command": "...", "outputs": ["相对 root 的产物路径"]}
    ]
  }

行为契约：
  * 第一步永远调用 result_guard init 落保底 result.json（已存在则跳过）；
    此后任何时刻 /app/output/result.json 都是诚实 partial（或更终态）。
  * 逐阶段用 subprocess 真实执行 command（sh -c，cwd=root）。
  * 每阶段完成后写 workdir/checkpoint.json：阶段名、完成时间戳、
    各产物 sha256、状态（success/failed）。
  * --resume：跳过「已成功且全部产物 hash 未变」的阶段；产物缺失或
    hash 变化的阶段自动重跑。
  * 任一阶段失败：保留 checkpoint，记录 failed 状态与 stderr 摘要，
    并调用 result_guard finalize --fail-stage 落 failed 状态，退出码 8。
  * 内置 budget_ledger：记录阶段数与耗时；超过 plan 的 warn_threshold
    时在 checkpoint.warnings 与 stdout 同时告警。

退出码：
  0  全部阶段成功
  8  某阶段失败（checkpoint 已记录 failed）
  1  运行错误（plan 缺失/非法等）
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_guard.py")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_ckpt(ckpt, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, ensure_ascii=False, indent=2)
        f.write("\n")


def run_guard(args_list):
    return subprocess.run([sys.executable, GUARD] + args_list,
                          capture_output=True, text=True)


def main():
    p = argparse.ArgumentParser(description="分阶段运行器（检查点续跑 + 预算台账）")
    p.add_argument("--plan", required=True, help="pipeline_plan.json 路径")
    p.add_argument("--root", default=None,
                   help="相对路径解析与阶段执行的工作目录，默认 plan 所在目录")
    p.add_argument("--resume", action="store_true", help="跳过已成功且产物未变的阶段")
    a = p.parse_args()
    if not os.path.isfile(a.plan):
        print(f"[pipeline] plan 不存在: {a.plan}", file=sys.stderr)
        return 1
    try:
        plan = load_json(a.plan)
    except json.JSONDecodeError as e:
        print(f"[pipeline] plan JSON 非法: {e}", file=sys.stderr)
        return 1
    root = os.path.abspath(a.root or os.path.dirname(os.path.abspath(a.plan)))
    workdir = os.path.join(root, plan.get("workdir", "work"))
    outdir = os.path.join(root, plan.get("outdir", "output"))
    logdir = os.path.join(workdir, "logs")
    for d in (workdir, outdir, logdir):
        os.makedirs(d, exist_ok=True)
    thresholds = plan.get("warn_threshold", {}) or {}
    stage_limit = thresholds.get("stage_seconds")
    total_limit = thresholds.get("total_seconds")

    ckpt_path = os.path.join(workdir, "checkpoint.json")
    if os.path.isfile(ckpt_path):
        ckpt = load_json(ckpt_path)
    else:
        ckpt = {"plan": os.path.abspath(a.plan), "root": root,
                "started_at": now_iso(), "stages": {},
                "ledger": {"stages_run": 0, "stages_skipped": 0,
                           "total_seconds": 0.0},
                "warnings": []}
    ledger = ckpt["ledger"]

    # ---- 第 0 步：保底 result.json（任何时刻存在诚实 partial） ----
    result_path = os.path.join(outdir, "result.json")
    if not os.path.isfile(result_path):
        case_rel = plan.get("case", "case.json")
        case_path = os.path.join(root, case_rel)
        r = run_guard(["init", "--case", case_path, "--out", outdir])
        print(r.stdout.strip())
        if r.returncode != 0:
            print(f"[pipeline] 保底 init 失败: {r.stderr.strip()}", file=sys.stderr)
            return 1
    else:
        print("[pipeline] 保底 result.json 已存在，跳过 init")

    # ---- 逐阶段执行 ----
    for i, st in enumerate(plan.get("stages", []), 1):
        name = st.get("name", f"stage{i}")
        command = st.get("command", "")
        rel_outputs = st.get("outputs", [])
        abs_outputs = [os.path.join(root, o) for o in rel_outputs]
        entry = ckpt["stages"].get(name)

        if a.resume and entry and entry.get("status") == "success":
            prev = entry.get("outputs", {})
            intact = all(os.path.isfile(pth) and sha256(pth) == prev.get(rel)
                         for rel, pth in zip(rel_outputs, abs_outputs))
            if intact:
                print(f"[pipeline] [{i}] {name}: SKIP（产物 hash 未变）")
                ledger["stages_skipped"] += 1
                save_ckpt(ckpt, ckpt_path)
                continue
            print(f"[pipeline] [{i}] {name}: 产物缺失或 hash 变化，重跑")

        print(f"[pipeline] [{i}] {name}: RUN  {command}")
        t0 = datetime.now(timezone.utc)
        proc = subprocess.run(command, shell=True, cwd=root,
                              capture_output=True, text=True)
        t1 = datetime.now(timezone.utc)
        dur = round((t1 - t0).total_seconds(), 3)
        ledger["total_seconds"] = round(ledger["total_seconds"] + dur, 3)

        with open(os.path.join(logdir, f"{i:02d}_{name}.log"), "w",
                  encoding="utf-8") as f:
            f.write(f"command: {command}\nreturncode: {proc.returncode}\n"
                    f"duration_s: {dur}\n--- stdout ---\n{proc.stdout}\n"
                    f"--- stderr ---\n{proc.stderr}\n")

        if stage_limit is not None and dur > stage_limit:
            msg = (f"budget_ledger 告警: 阶段 '{name}' 耗时 {dur}s "
                   f"> 阈值 {stage_limit}s")
            ckpt["warnings"].append(msg)
            print(f"[pipeline] WARNING {msg}")
        if total_limit is not None and ledger["total_seconds"] > total_limit:
            msg = (f"budget_ledger 告警: 累计耗时 {ledger['total_seconds']}s "
                   f"> 阈值 {total_limit}s")
            if msg not in ckpt["warnings"]:
                ckpt["warnings"].append(msg)
                print(f"[pipeline] WARNING {msg}")

        missing = [o for o in abs_outputs if not os.path.isfile(o)]
        if proc.returncode != 0 or missing:
            reason = (f"returncode={proc.returncode}" if proc.returncode != 0
                      else "声明产物未生成: " + ", ".join(missing))
            ckpt["stages"][name] = {
                "status": "failed", "finished_at": now_iso(),
                "duration_s": dur, "returncode": proc.returncode,
                "stderr_tail": (proc.stderr or "")[-800:],
                "reason": reason,
            }
            save_ckpt(ckpt, ckpt_path)
            r = run_guard(["finalize", "--result", result_path,
                           "--outdir", outdir,
                           "--fail-stage", name, "--fail-reason", reason])
            print(r.stdout.strip())
            print(f"[pipeline] [{i}] {name}: FAILED（{reason}），"
                  f"checkpoint 已保留，退出码 8", file=sys.stderr)
            return 8

        ledger["stages_run"] += 1
        ckpt["stages"][name] = {
            "status": "success", "finished_at": now_iso(),
            "duration_s": dur,
            "outputs": {rel: sha256(pth)
                        for rel, pth in zip(rel_outputs, abs_outputs)},
        }
        save_ckpt(ckpt, ckpt_path)
        print(f"[pipeline] [{i}] {name}: OK ({dur}s)")

    ckpt["finished_at"] = now_iso()
    save_ckpt(ckpt, ckpt_path)
    print(f"[pipeline] 完成: run={ledger['stages_run']} "
          f"skip={ledger['stages_skipped']} "
          f"total={ledger['total_seconds']}s warnings={len(ckpt['warnings'])}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as e:
        print(f"[pipeline] IO 错误: {e}", file=sys.stderr)
        sys.exit(1)
