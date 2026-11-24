#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — decision-forge-qc 全流程自查。

对 examples/ 合成示例执行全流程并断言预期结果：
  1. quality_gate 正例 exit 0；
  2. quality_gate 负例 exit 3，且 4 个 booby-trap 缺陷代码精确命中
     （FIELD_GROUP_EMPTY / ELIMINATION_EVIDENCE_MISSING /
      SELECTION_CITES_PENDING / CONTRACT_KEY_MISSING）；
  3. sensitivity 对正例 exit 0，verdict=sensitive，触发扰动与解析翻转阈值
     同手算值一致（reliability 下调 4/13→P_C；cost 上调 1/3→P_B；
     duration/safety 上调 3/7→P_C；等权重档翻转→P_C）；
  4. report_render exit 0，report.html/report.md 生成且含关键内容
     （case_id、合成示例横幅、页脚、选定方案、翻转表）；
  5. 确定性：全流程双跑，全部产物逐字节一致；
  6. 输入错误路径：quality_gate 作用于不存在的文件时 exit 2。

退出码：0=全部断言通过；2=自查脚本自身输入/用法错误；3=存在失败断言。
仅标准库；自身不写任何带时间戳的产物。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
EXAMPLES = ROOT / "examples"

EXPECTED_BAD_CODES = [
    "FIELD_GROUP_EMPTY",
    "ELIMINATION_EVIDENCE_MISSING",
    "SELECTION_CITES_PENDING",
    "CONTRACT_KEY_MISSING",
]
# 手算期望值（见 examples/README.md 验算过程）
EXPECTED_THRESHOLDS = {
    "reliability": {"down": (4.0 / 13.0, "P_C"), "up": None},
    "cost": {"down": None, "up": (1.0 / 3.0, "P_B")},
    "duration": {"down": None, "up": (3.0 / 7.0, "P_C")},
    "safety": {"down": None, "up": (3.0 / 7.0, "P_C")},
}
EXPECTED_TRIGGER_SCENARIOS = {"reliability_down", "equal_weights"}
TOL = 1e-9


class SelfcheckInputError(Exception):
    pass


def run(script, *script_args):
    cmd = [sys.executable, str(SCRIPTS / script)] + [str(a) for a in script_args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def pipeline(outdir):
    """对正例跑完整流程（gate → sensitivity → render），返回各步 CompletedProcess。"""
    out = Path(outdir)
    g = run("quality_gate.py", "--package", EXAMPLES / "package_good.json",
            "--case", EXAMPLES / "case.example.json", "--outdir", out)
    s = run("sensitivity.py", "--package", EXAMPLES / "package_good.json",
            "--outdir", out)
    r = run("report_render.py", "--package", EXAMPLES / "package_good.json",
            "--sensitivity", out / "sensitivity.json", "--outdir", out)
    return g, s, r


def file_bytes(outdir):
    out = Path(outdir)
    return {p.name: p.read_bytes() for p in sorted(out.iterdir()) if p.is_file()}


USAGE = ("用法: python3 selfcheck.py\n"
         "对 examples/ 合成示例跑全流程自查（质量门正/负例、敏感性手算对账、\n"
         "渲染产物检查、双跑字节一致、错误路径 exit 2）。无参数。\n"
         "退出码: 0=全部断言通过 / 2=自身用法错误 / 3=存在失败断言。")


def main(argv=None):
    argv = argv or []
    if argv in (["--help"], ["-h"]):
        print(USAGE)
        return 0
    if argv:
        raise SelfcheckInputError(f"selfcheck.py 不接受参数: {' '.join(argv)}")
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    try:
        with tempfile.TemporaryDirectory(prefix="dfqc_selfcheck_") as tmp:
            d1 = Path(tmp) / "run1"
            d2 = Path(tmp) / "run2"

            # 1. 正例 gate
            g1, s1, r1 = pipeline(d1)
            check("正例 quality_gate exit 0", g1.returncode == 0,
                  f"rc={g1.returncode} stderr={g1.stderr.strip()}")

            # 2. 负例 gate：exit 3 + 缺陷代码精确命中
            gb = run("quality_gate.py", "--package", EXAMPLES / "package_bad.json",
                     "--case", EXAMPLES / "case.example.json",
                     "--outdir", Path(tmp) / "bad")
            check("负例 quality_gate exit 3", gb.returncode == 3,
                  f"rc={gb.returncode}")
            codes = []
            try:
                with open(Path(tmp) / "bad" / "gate_report.json",
                          encoding="utf-8") as f:
                    codes = [d["code"] for d in json.load(f)["defects"]]
            except (OSError, json.JSONDecodeError, KeyError) as e:
                check("负例缺陷代码精确命中", False, f"无法读取 gate_report.json: {e}")
            else:
                check("负例缺陷代码精确命中",
                      sorted(codes) == sorted(EXPECTED_BAD_CODES),
                      f"实际={sorted(codes)} 预期={sorted(EXPECTED_BAD_CODES)}")

            # 3. sensitivity：verdict / 触发扰动 / 解析阈值与手算一致
            check("sensitivity exit 0", s1.returncode == 0,
                  f"rc={s1.returncode} stderr={s1.stderr.strip()}")
            try:
                with open(d1 / "sensitivity.json", encoding="utf-8") as f:
                    sens = json.load(f)
                ok = sens["verdict"]["status"] == "sensitive"
                check("sensitivity verdict=sensitive", ok,
                      f"实际={sens['verdict']['status']}")
                triggers = {t["scenario"] for t in sens["verdict"]["triggers"]}
                check("触发扰动集合与手算一致", triggers == EXPECTED_TRIGGER_SCENARIOS,
                      f"实际={sorted(triggers)}")
                th = {t["dimension"]: t for t in sens["thresholds"]}
                details = []
                all_ok = True
                for dim, exp in EXPECTED_THRESHOLDS.items():
                    for direction in ("down", "up"):
                        got = th[dim][f"{direction}_flip"]
                        want = exp[direction]
                        if want is None:
                            good = got is None
                        else:
                            good = (got is not None
                                    and abs(got["threshold"] - want[0]) < TOL
                                    and got["new_top"] == want[1])
                        all_ok = all_ok and good
                        details.append(f"{dim}.{direction}:{'OK' if good else 'MISMATCH'}")
                check("翻转阈值与手算一致（4/13、1/3、3/7）", all_ok, " ".join(details))
            except (OSError, json.JSONDecodeError, KeyError) as e:
                check("sensitivity 结果可解析", False, str(e))

            # 4. render：exit 0 + 关键内容
            check("report_render exit 0", r1.returncode == 0,
                  f"rc={r1.returncode} stderr={r1.stderr.strip()}")
            try:
                html_text = (d1 / "report.html").read_text(encoding="utf-8")
                md_text = (d1 / "report.md").read_text(encoding="utf-8")
            except OSError as e:
                check("report.html/report.md 生成", False, str(e))
            else:
                needles = ["SYNTH-EXP-2026-001", "SYNTHETIC EXAMPLE",
                           "report_render.py", "P_A", "hard_threshold_timeline",
                           "CONF-SAF-01", "reliability_down", "0.307692",
                           "sensitive", "<footer>"]
                missing = [n for n in needles if n not in html_text]
                check("report.html 关键内容完整", not missing,
                      f"缺失={missing}" if missing else f"含全部 {len(needles)} 个标记")
                md_needles = ["SYNTH-EXP-2026-001", "SYNTHETIC EXAMPLE",
                              "P_A", "决策日志", "翻转阈值", "sensitive"]
                missing_md = [n for n in md_needles if n not in md_text]
                check("report.md 关键内容完整", not missing_md,
                      f"缺失={missing_md}" if missing_md else "ok")

            # 5. 确定性：双跑逐字节一致
            g2, s2, r2 = pipeline(d2)
            b1, b2 = file_bytes(d1), file_bytes(d2)
            same = b1 == b2 and len(b1) >= 5
            check("双跑产物逐字节一致", same,
                  f"run1 文件={sorted(b1)} 字节一致={b1 == b2}")

            # 6. 输入错误路径 exit 2
            gbad = run("quality_gate.py", "--package",
                       EXAMPLES / "no_such_file.json", "--outdir", Path(tmp) / "x")
            check("缺失输入文件 exit 2", gbad.returncode == 2,
                  f"rc={gbad.returncode}")
    except OSError as e:
        print(f"自查脚本自身输入错误: {e}", file=sys.stderr)
        return 2

    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(f"selfcheck 汇总: {len(checks) - len(failed)}/{len(checks)} 通过")
    if failed:
        print("存在失败断言，退出码 3")
        return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SelfcheckInputError as e:
        print(f"用法错误: {e}（本脚本无需参数，直接 python3 selfcheck.py 运行）",
              file=sys.stderr)
        sys.exit(2)
