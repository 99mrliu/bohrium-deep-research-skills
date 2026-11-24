#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 技能包端到端程序化自测。

使用 examples/fixtures 中的合成样例：
  1. 用 source_register.py 登记夹具源文件（对虚构专利源预声明 OCR 容差）；
  2. 审计 result_ok.json                     —— 必须通过（exit 0）；
  3. 审计 result_bad_forged.json             —— 必须失败（exit 1，quote 不在源中）；
  4. 审计 result_bad_tolerant_undeclared.json —— 必须失败（exit 1，存在 OCR 噪声
     近似匹配但缺少声明：锚点无 tolerance_used:true）；
  5. 用 scaffold_result.py 从 case_fixture.json 生成骨架，校验 case_id 与
     output_contract 字段镜像。

逐条打印断言结果，全部通过才 exit 0，否则 exit 1；脚本/夹具缺失 exit 2。
"""
import json
import os
import subprocess
import sys
import tempfile

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(SKILL_DIR, "scripts")
FIXTURES = os.path.join(SKILL_DIR, "examples", "fixtures")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         (" — " + detail) if detail else ""))


def run(script, *args):
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script), *args],
        capture_output=True, text=True)


def main():
    for f in ("source_register.py", "quote_audit.py", "scaffold_result.py"):
        if not os.path.exists(os.path.join(SCRIPTS, f)):
            print("错误：缺少脚本 %s" % f, file=sys.stderr)
            return 2
    for f in ("case_fixture.json", "src_patent_EX1001.txt",
              "src_paper_EX2001.txt", "result_ok.json",
              "result_bad_forged.json", "result_bad_tolerant_undeclared.json"):
        if not os.path.exists(os.path.join(FIXTURES, f)):
            print("错误：缺少夹具 %s" % f, file=sys.stderr)
            return 2

    tmp = tempfile.mkdtemp(prefix="vaeg_selfcheck_")
    registry = os.path.join(tmp, "registry.json")

    # 1) 登记（含对专利源的 OCR 容差预声明）
    r = run("source_register.py", "--roots", FIXTURES, "--out", registry,
            "--tolerance-ocr", os.path.join(FIXTURES, "src_patent_EX1001.txt"))
    check("source_register 登记夹具源文件", r.returncode == 0,
          (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else "")

    # 2) result_ok 必须通过
    r = run("quote_audit.py", "--result", os.path.join(FIXTURES, "result_ok.json"),
            "--registry", registry)
    check("quote_audit(result_ok) 通过 (exit 0)", r.returncode == 0,
          (r.stdout or "").strip().splitlines()[-1] if r.stdout else r.stderr.strip())

    # 3) result_bad_forged 必须失败（quote 不在源中）
    r = run("quote_audit.py", "--result",
            os.path.join(FIXTURES, "result_bad_forged.json"),
            "--registry", registry)
    out = (r.stdout or "") + (r.stderr or "")
    check("quote_audit(result_bad_forged) 失败 (exit 1)",
          r.returncode == 1 and "quote not found" in out,
          out.strip().splitlines()[0] if out.strip() else "")

    # 4) result_bad_tolerant_undeclared 必须失败（近似匹配但未声明容差）
    r = run("quote_audit.py", "--result",
            os.path.join(FIXTURES, "result_bad_tolerant_undeclared.json"),
            "--registry", registry)
    out = (r.stdout or "") + (r.stderr or "")
    check("quote_audit(result_bad_tolerant_undeclared) 失败 (exit 1)",
          r.returncode == 1 and "undeclared tolerance" in out,
          out.strip().splitlines()[0] if out.strip() else "")

    # 5) 骨架生成与契约镜像校验
    outdir = os.path.join(tmp, "out")
    r = run("scaffold_result.py", "--case", os.path.join(FIXTURES, "case_fixture.json"),
            "--out", outdir, "--status", "partial")
    ok = r.returncode == 0
    detail = (r.stdout or r.stderr).strip()
    if ok:
        with open(os.path.join(outdir, "result.json"), "r", encoding="utf-8") as f:
            skel = json.load(f)
        with open(os.path.join(FIXTURES, "case_fixture.json"), "r",
                  encoding="utf-8") as f:
            case = json.load(f)
        expect = set(case["output_contract"].keys())
        mirrored = expect.issubset(skel.keys()) and all(
            skel[k] is None for k in expect
            if k not in ("status", "sources", "uncertainty"))
        ok = (skel.get("case_id") == "SYNTH-EXAMPLE-001"
              and skel.get("status") == "partial"
              and mirrored
              and isinstance(skel.get("sources"), list)
              and isinstance(skel.get("uncertainty"), list)
              and isinstance(skel.get("change_records"), list))
        detail = "case_id=%s, 契约字段镜像=%s" % (
            skel.get("case_id"), sorted(expect))
    check("scaffold_result(case_fixture) case_id 与契约镜像正确", ok, detail)

    print("-" * 60)
    if all(RESULTS):
        print("自查通过：%d/%d 断言全部 PASS。" % (len(RESULTS), len(RESULTS)))
        return 0
    print("自查失败：%d/%d 断言通过。" % (sum(RESULTS), len(RESULTS)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
