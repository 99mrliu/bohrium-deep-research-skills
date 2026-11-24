#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_minimal_example.py — 最小合成示例的端到端一键运行。

在 bundle 根目录执行：
    python3 scripts/run_minimal_example.py

流程：
1. 对 examples/minimal/candidate_result.json（故意埋 3 处错误）依次运行
   contract_validate → evidence_spotcheck → freshness_check → metrics → qa_report，
   产物写入 examples/minimal/output/candidate/；
2. 自检期望：locator 不可解析 / 窗口外日期 / 旧文重报 3 处错误全部被对应门禁检出，
   qa_report overall=fail 且阻断项 ≥3；
3. 对 examples/minimal/fixed_result.json 重跑全部门禁，
   产物写入 examples/minimal/output/fixed/，期望 overall=pass；
4. 汇总 output/run_summary.json 并打印人类可读结论。

退出码：0 = 全部期望满足；1 = 期望未满足（示例本身出现问题）。仅标准库。
"""
import json
import subprocess
import sys
from pathlib import Path

BUNDLE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = BUNDLE_ROOT / "scripts"
EXAMPLE = BUNDLE_ROOT / "examples" / "minimal"
OUT = EXAMPLE / "output"

CASE = EXAMPLE / "case.json"

PLANTED = {
    "locator_unresolvable": "10.7554/elife.90001",
    "date_out_of_window": "10.1016/j.cell.2026.08.015",
    "already_in_snapshot": "10.1038/s41586-026-00001-x",
}


def run_gate(script, gate_args, out_path):
    cmd = [sys.executable, str(SCRIPTS / script)] + gate_args
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(BUNDLE_ROOT))
    for line in proc.stdout.splitlines():
        print(f"    {line}")
    if proc.returncode not in (0, 2):  # 0=pass 2=warn 属预期；1=fail 由调用方按场景判断
        if proc.returncode != 1:
            print(f"    !! {script} 退出码异常: {proc.returncode}")
            print(proc.stderr[-2000:] if proc.stderr else "    (no stderr)")
    if not out_path.is_file():
        raise RuntimeError(f"{script} 未生成报告文件: {out_path}")
    return json.loads(out_path.read_text(encoding="utf-8")), proc.returncode


def run_pipeline(result_path, out_dir):
    """对一份 result 跑全部门禁，返回 (qa_report_dict, sub_reports)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  [1/5] contract_validate")
    contract, _ = run_gate(
        "contract_validate.py",
        ["--case", str(CASE), "--result", str(result_path),
         "--out", str(out_dir / "contract_validate.json")],
        out_dir / "contract_validate.json")
    print(f"  [2/5] evidence_spotcheck")
    spot, _ = run_gate(
        "evidence_spotcheck.py",
        ["--result", str(result_path), "--base", str(EXAMPLE),
         "--out", str(out_dir / "evidence_spotcheck.json")],
        out_dir / "evidence_spotcheck.json")
    print(f"  [3/5] freshness_check")
    fresh, _ = run_gate(
        "freshness_check.py",
        ["--case", str(CASE), "--result", str(result_path),
         "--out", str(out_dir / "freshness_check.json")],
        out_dir / "freshness_check.json")
    print(f"  [4/5] metrics")
    metrics, _ = run_gate(
        "metrics.py",
        ["--case", str(CASE), "--result", str(result_path),
         "--spotcheck", str(out_dir / "evidence_spotcheck.json"),
         "--freshness", str(out_dir / "freshness_check.json"),
         "--out", str(out_dir / "metrics.json")],
        out_dir / "metrics.json")
    print(f"  [5/5] qa_report")
    qa, _ = run_gate(
        "qa_report.py",
        ["--case", str(CASE), "--result", str(result_path),
         "--reports", str(out_dir / "contract_validate.json"),
         str(out_dir / "evidence_spotcheck.json"),
         str(out_dir / "freshness_check.json"),
         str(out_dir / "metrics.json"),
         "--out-json", str(out_dir / "qa_report.json"),
         "--out-md", str(out_dir / "qa_report.md")],
        out_dir / "qa_report.json")
    return qa, {"contract": contract, "spotcheck": spot,
                "freshness": fresh, "metrics": metrics}


def _fails_contain(report, needle):
    return any(c.get("status") == "fail" and needle in c.get("message", "")
               for c in report.get("checks", []))


def verify_candidate(qa, subs):
    """校验 3 处埋错是否全部被检出。返回 (ok, findings)。"""
    findings = []
    ok = True

    f1 = _fails_contain(subs["spotcheck"], PLANTED["locator_unresolvable"]) or \
        any(c.get("status") == "fail" and c.get("id") == "item[2].locator"
            for c in subs["spotcheck"]["checks"])
    findings.append(("埋错1 locator 指向不存在的记录 (10.7554/elife.90001 → "
                     "#/resultList/result/7)", "evidence_spotcheck", f1))

    f2 = _fails_contain(subs["freshness"], PLANTED["date_out_of_window"])
    findings.append(("埋错2 日期落在窗口外 (10.1016/j.cell.2026.08.015 → 2026-08-20)",
                     "freshness_check", f2))

    f3 = _fails_contain(subs["freshness"], PLANTED["already_in_snapshot"]) and \
        any("previous_snapshot" in c.get("message", "")
            for c in subs["freshness"]["checks"]
            if c.get("status") == "fail"
            and PLANTED["already_in_snapshot"] in c.get("message", ""))
    findings.append(("埋错3 已在 previous_snapshot 中 (10.1038/s41586-026-00001-x)",
                     "freshness_check", f3))

    qa_fail = qa.get("overall_status") == "fail"
    findings.append(("qa_report overall_status = fail", "qa_report", qa_fail))
    enough_blockers = len(qa.get("blocking_items", [])) >= 3
    findings.append((f"qa_report 阻断项 ≥3（实际 {len(qa.get('blocking_items', []))}）",
                     "qa_report", enough_blockers))

    for _, _, passed in findings:
        ok = ok and passed
    return ok, findings


def main():
    print("=" * 72)
    print("tracking-qa-harness 最小合成示例（synthetic demo）端到端运行")
    print(f"bundle 根目录: {BUNDLE_ROOT}")
    print("=" * 72)

    summary = {"bundle_root": str(BUNDLE_ROOT), "synthetic": True, "runs": {}}
    all_ok = True

    # ---- 第 1 轮：candidate（应检出 3 处埋错） ----
    print("\n>>> 第 1 轮：candidate_result.json（故意埋 3 处错误）")
    qa_c, subs_c = run_pipeline(EXAMPLE / "candidate_result.json", OUT / "candidate")
    ok_c, findings = verify_candidate(qa_c, subs_c)
    print("  --- 埋错检出自检 ---")
    for desc, gate, passed in findings:
        print(f"  [{'OK' if passed else 'MISS'}] {desc}（检出门禁: {gate}）")
    summary["runs"]["candidate"] = {
        "result_file": "examples/minimal/candidate_result.json",
        "overall_status": qa_c.get("overall_status"),
        "blocking_items": len(qa_c.get("blocking_items", [])),
        "metrics": qa_c.get("metrics"),
        "planted_errors_detected": [
            {"error": d, "gate": g, "detected": p} for d, g, p in findings],
        "expectations_met": ok_c,
    }
    all_ok = all_ok and ok_c

    # ---- 第 2 轮：fixed（应全部通过） ----
    print("\n>>> 第 2 轮：fixed_result.json（修复后，应全部通过）")
    qa_f, _ = run_pipeline(EXAMPLE / "fixed_result.json", OUT / "fixed")
    ok_f = qa_f.get("overall_status") == "pass"
    print(f"  --- 修复版自检: overall_status={qa_f.get('overall_status')} "
          f"({'OK' if ok_f else 'NOT PASS'}) ---")
    summary["runs"]["fixed"] = {
        "result_file": "examples/minimal/fixed_result.json",
        "overall_status": qa_f.get("overall_status"),
        "blocking_items": len(qa_f.get("blocking_items", [])),
        "metrics": qa_f.get("metrics"),
        "expectations_met": ok_f,
    }
    all_ok = all_ok and ok_f

    summary["all_expectations_met"] = all_ok
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n" + "=" * 72)
    print(f"端到端自检结论: {'全部期望满足 ✅' if all_ok else '存在未满足的期望 ❌'}")
    print(f"产物目录: {OUT}")
    print("=" * 72)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
