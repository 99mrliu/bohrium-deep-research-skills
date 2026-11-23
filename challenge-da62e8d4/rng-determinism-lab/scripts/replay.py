#!/usr/bin/env python3
"""replay.py — 受控重放：同一命令在固定 PYTHONHASHSEED=0 下跑 N 次，机械判定执行确定性。

只使用标准库。

用法:
    python3 replay.py --name NAME --runs N --out DIR [--artifact RELPATH ...]
                      [--timeout SECONDS] -- CMD [ARG ...]

每次运行：
  - 独立子目录 DIR/run_<i>/，命令以该目录为 cwd 执行；
  - 环境在继承当前环境的基础上强制 PYTHONHASHSEED=0；
  - stdout/stderr 分别写入 run_<i>/stdout.txt、run_<i>/stderr.txt；
  - run_<i>/meta.json 记录退出码、墙钟秒数、timeout 标记与 PYTHONHASHSEED；
  - 超时（--timeout，默认 60 秒）时杀掉整个进程组并记 timeout=true。

判定逻辑（仅机械比较，不做统计推断）：
  - 各次 stdout 逐字节一致                       -> identical
  - stdout 文本不同，但抽取的数值序列完全一致      -> numerically_stable
    （数值用正则抽取，含科学计数法；例如只有耗时数字不同）
  - 数值序列不一致                                -> unstable，
    报告首次分叉的数值索引与两值（以 run_1 为基准）。
  - 命令不存在/无法启动                           -> spawn_error（不中断，仍出报告）。

--artifact 可重复声明产物文件的相对路径（相对 run_<i>/），逐次计算 sha256 对比。

输出：
  DIR/determinism_report.json   结构化报告
  DIR/report.md                 人读摘要

退出码：0 报告已生成（无论判定结果如何）；2 参数错误。
"""
import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time

NUM_RE = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def extract_numbers(text):
    """从文本抽取全部数值（含科学计数），返回 float 列表与原始 token 列表。"""
    tokens = NUM_RE.findall(text)
    values = []
    for t in tokens:
        try:
            values.append(float(t))
        except ValueError:
            values.append(None)
    return tokens, values


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_one(cmd, rundir, timeout):
    """执行一次，返回 meta 字典。stdout/stderr 落盘到 rundir。"""
    os.makedirs(rundir, exist_ok=True)
    stdout_path = os.path.join(rundir, "stdout.txt")
    stderr_path = os.path.join(rundir, "stderr.txt")
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    meta = {
        "command": cmd,
        "cwd": rundir,
        "env_overrides": {"PYTHONHASHSEED": "0"},
        "exit_code": None,
        "wall_time_seconds": None,
        "timeout": False,
        "spawn_error": None,
    }
    t0 = time.monotonic()
    try:
        out_f = open(stdout_path, "wb")
        err_f = open(stderr_path, "wb")
    except OSError as e:
        meta["spawn_error"] = "无法打开 stdout/stderr 文件: %s" % e
        return meta
    try:
        try:
            proc = subprocess.Popen(
                cmd, cwd=rundir, env=env,
                stdout=out_f, stderr=err_f,
                start_new_session=True,  # 独立进程组，便于超时整组击杀
            )
        except (FileNotFoundError, PermissionError, OSError) as e:
            meta["spawn_error"] = "%s: %s" % (type(e).__name__, e)
            return meta
        try:
            proc.wait(timeout=timeout)
            meta["exit_code"] = proc.returncode
        except subprocess.TimeoutExpired:
            meta["timeout"] = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            proc.wait()
            meta["exit_code"] = proc.returncode
    finally:
        out_f.close()
        err_f.close()
        meta["wall_time_seconds"] = round(time.monotonic() - t0, 6)
    return meta


def compare_sequences(seqs):
    """比较各次数值序列。返回 (all_equal, first_divergence or None)。"""
    base = seqs[0]
    for i, seq in enumerate(seqs[1:], start=2):
        if len(seq) != len(base):
            idx = min(len(seq), len(base))
            return False, {
                "run": i, "numeric_index": idx,
                "reason": "序列长度不同: run_1=%d, run_%d=%d" % (len(base), i, len(seq)),
                "value_run_1": base[idx] if idx < len(base) else None,
                "value_run_%d" % i: seq[idx] if idx < len(seq) else None,
            }
        for j, (a, b) in enumerate(zip(base, seq)):
            if a != b:
                return False, {
                    "run": i, "numeric_index": j,
                    "value_run_1": a, "value_run_%d" % i: b,
                }
    return True, None


def main(argv):
    # `--` 之后全部是被测命令
    if "--" in argv:
        idx = argv.index("--")
        opt_args, cmd = argv[:idx], argv[idx + 1:]
    else:
        opt_args, cmd = argv, []
    parser = argparse.ArgumentParser(description="受控重放与执行确定性判定")
    parser.add_argument("--name", required=True, help="本次重放的名称")
    parser.add_argument("--runs", type=int, required=True, help="重放次数 N")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--artifact", action="append", default=[],
                        help="产物文件相对路径（相对 run_<i>/），可重复")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="单次运行超时秒数，默认 60")
    args = parser.parse_args(opt_args)
    if not cmd:
        parser.error("`--` 之后必须给出待跑命令")
    if args.runs < 1:
        parser.error("--runs 必须 >= 1")

    os.makedirs(args.out, exist_ok=True)
    runs_detail = []
    stdouts = []
    num_seqs = []
    for i in range(1, args.runs + 1):
        rundir = os.path.join(args.out, "run_%d" % i)
        meta = run_one(cmd, rundir, args.timeout)
        meta["run"] = i
        # meta.json 落盘
        with open(os.path.join(rundir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        # 读回 stdout 做比较
        stdout_text = ""
        stdout_path = os.path.join(rundir, "stdout.txt")
        if os.path.isfile(stdout_path):
            with open(stdout_path, "r", encoding="utf-8", errors="replace") as f:
                stdout_text = f.read()
        tokens, values = extract_numbers(stdout_text)
        meta["stdout_num_count"] = len(values)
        runs_detail.append(meta)
        stdouts.append(stdout_text)
        num_seqs.append(values)

    # ---- 判定 ---------------------------------------------------------------
    spawn_errors = [r for r in runs_detail if r["spawn_error"]]
    timeout_runs = [r for r in runs_detail if r["timeout"]]
    exit_codes = [r["exit_code"] for r in runs_detail]
    first_divergence = None
    if spawn_errors:
        verdict = "spawn_error"
    elif len(set(stdouts)) == 1:
        verdict = "identical"
    else:
        all_equal, first_divergence = compare_sequences(num_seqs)
        verdict = "numerically_stable" if all_equal else "unstable"

    # ---- 产物哈希对比 --------------------------------------------------------
    artifact_report = {}
    for rel in args.artifact:
        per_run = {}
        hashes = []
        for i in range(1, args.runs + 1):
            p = os.path.join(args.out, "run_%d" % i, rel)
            if os.path.isfile(p):
                digest = sha256_file(p)
                per_run["run_%d" % i] = digest
                hashes.append(digest)
            else:
                per_run["run_%d" % i] = None
        artifact_report[rel] = {
            "per_run_sha256": per_run,
            "identical": (len(hashes) == args.runs
                          and len(set(hashes)) == 1),
            "missing_runs": [i for i in range(1, args.runs + 1)
                             if per_run["run_%d" % i] is None],
        }

    report = {
        "name": args.name,
        "runs": args.runs,
        "timeout_seconds": args.timeout,
        "command": cmd,
        "env_overrides": {"PYTHONHASHSEED": "0"},
        "verdict": verdict,
        "exit_codes": exit_codes,
        "exit_codes_uniform": len(set(map(str, exit_codes))) == 1,
        "spawn_errors": [r["spawn_error"] for r in spawn_errors],
        "timeout_runs": [r["run"] for r in timeout_runs],
        "runs_detail": runs_detail,
        "stdout_comparison": {
            "byte_identical": len(set(stdouts)) == 1,
            "numeric_sequences_identical": verdict in ("identical",
                                                       "numerically_stable"),
            "first_divergence": first_divergence,
        },
        "artifacts": artifact_report,
        "notes": [
            "判定为机械比较（字节级/数值序列级），不构成与论文数值的任何比较结论。",
            "unstable 表示同机重跑已不可复现；在与论文或跨机比较之前必须先固定随机性来源。",
        ],
    }
    report_path = os.path.join(args.out, "determinism_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # ---- report.md -----------------------------------------------------------
    lines = []
    lines.append("# 受控重放确定性报告: %s" % args.name)
    lines.append("")
    lines.append("- 命令: `%s`" % " ".join(cmd))
    lines.append("- 重放次数: %d；超时上限: %s 秒；环境覆盖: `PYTHONHASHSEED=0`"
                 % (args.runs, args.timeout))
    lines.append("- **判定 verdict: `%s`**" % verdict)
    lines.append("")
    lines.append("| run | exit_code | wall_time(s) | timeout | stdout 数值个数 |")
    lines.append("|-----|-----------|--------------|---------|-----------------|")
    for r in runs_detail:
        lines.append("| %d | %s | %s | %s | %s |" % (
            r["run"], r["exit_code"], r["wall_time_seconds"],
            r["timeout"], r.get("stdout_num_count")))
    lines.append("")
    if spawn_errors:
        lines.append("## spawn_error")
        lines.append("")
        for r in spawn_errors:
            lines.append("- run_%d: %s" % (r["run"], r["spawn_error"]))
        lines.append("")
    if first_divergence:
        lines.append("## 首次数值分叉")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(first_divergence, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    if artifact_report:
        lines.append("## 产物文件 sha256 对比")
        lines.append("")
        for rel, info in artifact_report.items():
            lines.append("### `%s` — 各次一致: %s" % (rel, info["identical"]))
            lines.append("")
            for rk, hv in info["per_run_sha256"].items():
                lines.append("- %s: `%s`" % (rk, hv if hv else "(缺失)"))
            lines.append("")
    lines.append("## 说明")
    lines.append("")
    for n in report["notes"]:
        lines.append("- " + n)
    lines.append("")
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("verdict=%s 报告: %s" % (verdict, report_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
