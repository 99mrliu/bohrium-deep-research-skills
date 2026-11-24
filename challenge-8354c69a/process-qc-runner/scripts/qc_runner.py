#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qc_runner.py — 阶段化过程质量控制运行器：清单化、可断点恢复、失败可定位。

plan.json 格式:
{"stages": [
  {"id": "inventory", "cmd": "python3 scan.py --input /input --out /app/work/inv.json",
   "inputs": ["/input"], "outputs": ["/app/work/inv.json"], "timeout_s": 120,
   "on_fail": "stop" | "continue"},
  ...
]}

每个阶段完成后写 /app/work/qc/manifest.json 条目：
  {id, cmd, exit, started, elapsed_s, stdout_tail, stderr_tail,
   input_hashes, output_hashes}
恢复语义：重跑时，若某阶段已有 manifest 条目 exit=0 且 command 与全部
input_hashes 与当前一致，则跳过（幂等恢复）；任一输入变化 → 该阶段及其
**下游全部阶段**作废重跑。

失败定位：非零退出的阶段记录 stderr_tail 与处置建议（on_fail）；
失败后磁盘状态即现场，修复后同一命令重跑即可续跑。

  python3 qc_runner.py run --plan plan.json --work /app/work
  python3 qc_runner.py status --work /app/work
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time


def hash_path(p):
    if not os.path.exists(p):
        return "MISSING"
    if os.path.isfile(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    h = hashlib.sha256()
    for root, _d, names in os.walk(p):
        for n in sorted(names):
            fp = os.path.join(root, n)
            if os.path.isfile(fp):
                h.update(fp.encode())
                h.update(hash_path(fp).encode())
    return h.hexdigest()


def manifest_path(work):
    return os.path.join(work, "qc", "manifest.json")


def load_manifest(work):
    p = manifest_path(work)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"stages": {}}


def save_manifest(work, m):
    os.makedirs(os.path.join(work, "qc"), exist_ok=True)
    json.dump(m, open(manifest_path(work), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)


def stage_reusable(entry, stage):
    if not entry or entry.get("exit") != 0 or entry.get("cmd") != stage["cmd"]:
        return False
    for path, h in entry.get("input_hashes", {}).items():
        if hash_path(path) != h:
            return False
    return True


def invalidate_downstream(m, from_idx, stages):
    for s in stages[from_idx:]:
        m["stages"].pop(s["id"], None)


def cmd_run(a):
    plan = json.load(open(a.plan, encoding="utf-8"))
    stages = plan["stages"]
    m = load_manifest(a.work)
    for idx, stage in enumerate(stages):
        entry = m["stages"].get(stage["id"])
        if entry and not stage_reusable(entry, stage):
            invalidate_downstream(m, idx, stages)
            entry = None
        if stage_reusable(m["stages"].get(stage["id"]), stage):
            print("[qc] SKIP %s (manifest 一致，幂等恢复)" % stage["id"])
            continue
        print("[qc] RUN  %s" % stage["id"])
        t0 = time.time()
        try:
            proc = subprocess.run(stage["cmd"], shell=True,
                                  capture_output=True, text=True,
                                  timeout=stage.get("timeout_s", 300))
            exit_code, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            exit_code, out, err = 124, "", "TIMEOUT after %ss: %s" % (
                stage.get("timeout_s", 300), (e.stderr or "")[:500])
        rec = {
            "id": stage["id"], "cmd": stage["cmd"], "exit": exit_code,
            "elapsed_s": round(time.time() - t0, 3),
            "stdout_tail": (out or "")[-2000:], "stderr_tail": (err or "")[-2000:],
            "input_hashes": {p: hash_path(p) for p in stage.get("inputs", [])},
            "output_hashes": {p: hash_path(p) for p in stage.get("outputs", [])},
        }
        m["stages"][stage["id"]] = rec
        save_manifest(a.work, m)
        if exit_code != 0:
            print("[qc] FAIL %s exit=%d stderr_tail=%r"
                  % (stage["id"], exit_code, rec["stderr_tail"][-300:]))
            if stage.get("on_fail", "stop") == "stop":
                print("[qc] 停止于阶段 %s；修复后用同一命令重跑即可从断点续跑"
                      % stage["id"])
                sys.exit(2)
        else:
            print("[qc] OK   %s (%.2fs)" % (stage["id"], rec["elapsed_s"]))
    print("[qc] 全部阶段完成 ->", manifest_path(a.work))


def cmd_status(a):
    m = load_manifest(a.work)
    if not m["stages"]:
        print("[qc] 无 manifest 记录")
        return
    for sid, e in m["stages"].items():
        missing_out = [p for p, h in e.get("output_hashes", {}).items()
                       if hash_path(p) != h]
        flag = "OK" if e["exit"] == 0 and not missing_out else \
               ("STALE-OUTPUT" if missing_out else "FAIL(exit=%d)" % e["exit"])
        print("%-20s %-14s %.2fs" % (sid, flag, e.get("elapsed_s", 0)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--plan", required=True)
    p.add_argument("--work", default="/app/work")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("status")
    p.add_argument("--work", default="/app/work")
    p.set_defaults(fn=cmd_status)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
