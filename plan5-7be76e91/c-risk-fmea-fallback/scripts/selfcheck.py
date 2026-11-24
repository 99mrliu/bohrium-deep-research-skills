#!/usr/bin/env python3
"""selfcheck.py — examples 全流程自查（确定性，纯 stdlib）。

校验内容：
  1. 正例：P1/P2 三脚本（fmea -> expected_cost -> fallback_graph）均 exit 0；
     P3 的 fmea/expected_cost exit 0，fallback_graph 精确 exit 3（critical 无回退）。
  2. 负例精确命中：NEG-EMPTY-TRIGGER 的 fmea exit 3（空触发条件）；
     NEG-CYCLE 的 fallback_graph exit 3（回退链成环）。
  3. 双跑字节一致：全流程在两个独立临时目录各跑一遍，逐文件字节比较。
  4. --help 可用：四个脚本 --help 均 exit 0。

退出码：0 全部通过 / 2 用法错误 / 3 自查失败（失败清单写 stdout）。
"""
import argparse
import filecmp
import subprocess
import sys
import tempfile
from pathlib import Path

EXIT_OK, EXIT_USAGE, EXIT_GATE = 0, 2, 3
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
EXAMPLES = ROOT / "examples"

failures = []


def run(script, argv, expect_code, label, check=True):
    cmd = [sys.executable, str(SCRIPTS / script)] + argv
    p = subprocess.run(cmd, capture_output=True, text=True)
    status = "OK" if p.returncode == expect_code else "FAIL"
    print(f"[{status}] {label}: exit={p.returncode} (expect {expect_code})")
    if check and p.returncode != expect_code:
        failures.append(f"{label}: exit={p.returncode}, expect={expect_code}\n"
                        f"  stdout: {p.stdout.strip()[:400]}\n  stderr: {p.stderr.strip()[:400]}")
    return p.returncode


def suite(outroot):
    """完整跑一遍 examples 流程，返回 (产物目录列表)。"""
    outroot = Path(outroot)
    base = EXAMPLES / "base_inputs.json"
    dirs = []
    for plan in ("P1", "P2", "P3"):
        reg = EXAMPLES / f"risk_register_{plan}.json"
        od = outroot / plan
        dirs.append(od)
        exp_fb = EXIT_GATE if plan == "P3" else EXIT_OK
        run("fmea.py", ["--register", str(reg), "--outdir", str(od)], EXIT_OK, f"{plan}/fmea")
        run("expected_cost.py", ["--register", str(reg), "--base", str(base), "--outdir", str(od)],
            EXIT_OK, f"{plan}/expected_cost")
        run("fallback_graph.py", ["--register", str(reg), "--fmea", str(od / "fmea.json"),
                                  "--outdir", str(od)], exp_fb, f"{plan}/fallback_graph")
    # 多方案对比
    run("expected_cost.py",
        ["--register", str(EXAMPLES / "risk_register_P1.json"),
         "--register", str(EXAMPLES / "risk_register_P2.json"),
         "--register", str(EXAMPLES / "risk_register_P3.json"),
         "--base", str(base), "--outdir", str(outroot / "compare")],
        EXIT_OK, "compare/expected_cost")
    dirs.append(outroot / "compare")
    # 负例 1：空触发条件 -> fmea exit 3
    run("fmea.py", ["--register", str(EXAMPLES / "risk_register_neg_empty_trigger.json"),
                    "--outdir", str(outroot / "neg_empty")], EXIT_GATE, "neg_empty_trigger/fmea")
    dirs.append(outroot / "neg_empty")
    # 负例 2：回退成环 -> fallback_graph exit 3（fmea 本身应通过）
    neg_od = outroot / "neg_cycle"
    run("fmea.py", ["--register", str(EXAMPLES / "risk_register_neg_cycle.json"),
                    "--outdir", str(neg_od)], EXIT_OK, "neg_cycle/fmea")
    run("fallback_graph.py",
        ["--register", str(EXAMPLES / "risk_register_neg_cycle.json"),
         "--fmea", str(neg_od / "fmea.json"), "--outdir", str(neg_od)],
        EXIT_GATE, "neg_cycle/fallback_graph")
    dirs.append(neg_od)
    return dirs


def compare_trees(da, db):
    files_a = sorted(p.relative_to(da) for p in da.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(db) for p in db.rglob("*") if p.is_file())
    if files_a != files_b:
        failures.append(f"双跑文件清单不一致: {files_a} vs {files_b}")
        return
    for rel in files_a:
        if not filecmp.cmp(da / rel, db / rel, shallow=False):
            failures.append(f"双跑字节不一致: {rel}")


def main():
    ap = argparse.ArgumentParser(description="examples 全流程自查：正负例退出码 + 双跑字节一致。"
                                             "退出码 0 通过 / 2 用法 / 3 失败。")
    ap.parse_args()

    for s in ("fmea.py", "expected_cost.py", "fallback_graph.py", "selfcheck.py"):
        p = subprocess.run([sys.executable, str(SCRIPTS / s), "--help"],
                           capture_output=True, text=True)
        print(f"[{'OK' if p.returncode == 0 else 'FAIL'}] --help {s}: exit={p.returncode}")
        if p.returncode != 0:
            failures.append(f"{s} --help exit={p.returncode}")

    with tempfile.TemporaryDirectory(prefix="selfcheck_a_") as ta, \
         tempfile.TemporaryDirectory(prefix="selfcheck_b_") as tb:
        print(f"--- 第一跑: {ta}")
        suite(ta)
        print(f"--- 第二跑: {tb}")
        suite(tb)
        compare_trees(Path(ta), Path(tb))
        print("双跑字节比较完成")

    if failures:
        print("\nSELF-CHECK FAILED (exit 3):")
        for f in failures:
            print("  " + f.replace("\n", "\n  "))
        sys.exit(EXIT_GATE)
    print("\nSELF-CHECK PASS: 正例 exit 0、负例 exit 3 精确命中、双跑字节一致。")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
