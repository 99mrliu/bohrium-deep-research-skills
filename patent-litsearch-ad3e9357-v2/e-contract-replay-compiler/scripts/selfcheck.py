#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — result-contract-replay-compiler 端到端自检（全部基于合成 fixtures）

流程（在临时目录中进行，不改动仓库内 fixtures）：
  1. scaffold：从 case_fixture.json 生成脚手架，断言契约镜像与 case_id；
  2. fill：合并 fill.json，断言字段被填充、uncertainty 收缩、change_records 追加；
  3. validate：好结果 → 通过；result_bad_missing_field.json → V2 fail；
     result_bad_overclaim.json → V3 fail（status=ok 但契约字段为 null）；
  4. replay：log 两步 → pack manifest → verify 全 fresh；改动一个输入后再 verify，
     断言该步骤 stale、其余 fresh；
  5. render：渲染 review.md 并断言六个章节齐全。

退出码：0 全部断言通过；1 存在失败断言；2 用法/输入错误。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
FIXTURES = os.path.join(ROOT, "examples", "fixtures")

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def run(script, *args, cwd=None):
    cmd = [sys.executable, os.path.join(SCRIPTS, script)] + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout + p.stderr


def jload(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    tmp = tempfile.mkdtemp(prefix="rcrc-selfcheck-")
    print(f"[信息] 自检工作目录: {tmp}")
    try:
        # 准备 fixtures 副本
        for fn in ("case_fixture.json", "fill.json", "result_bad_missing_field.json",
                   "result_bad_overclaim.json"):
            shutil.copy(os.path.join(FIXTURES, fn), os.path.join(tmp, fn))
        case = os.path.join(tmp, "case_fixture.json")
        outdir = os.path.join(tmp, "output")

        # ---------- 1. scaffold ----------
        rc, log = run("scaffold_result.py", "--case", case, "--out", outdir,
                      "--note", "自检：初始脚手架")
        check("scaffold 退出码为 0", rc == 0, log.strip().splitlines()[-1] if log else "")
        res = jload(os.path.join(outdir, "result.json"))
        check("scaffold case_id 正确", res.get("case_id") == "SYNTH-EXAMPLE-005")
        check("scaffold 契约字段镜像为 null",
              all(res.get(f) is None for f in
                  ("candidates", "evidence_records", "legal_status", "omissions_note")))
        check("scaffold 初始 status=partial", res.get("status") == "partial")
        check("scaffold uncertainty 覆盖全部 null 契约字段",
              all(any(str(u).startswith(f + ":") for u in res.get("uncertainty", []))
                  for f in ("candidates", "evidence_records", "legal_status",
                            "omissions_note")))
        check("scaffold change_records 有 1 条", len(res.get("change_records", [])) == 1)

        # ---------- 2. fill ----------
        rc, log = run("scaffold_result.py", "--case", case, "--out", outdir,
                      "--fill", os.path.join(tmp, "fill.json"),
                      "--note", "自检：合并 fill.json")
        check("fill 退出码为 0", rc == 0)
        res = jload(os.path.join(outdir, "result.json"))
        check("fill 后 candidates 有 1 条候选",
              isinstance(res.get("candidates"), list) and len(res["candidates"]) == 1)
        check("fill 后 sources 有 1 条来源",
              isinstance(res.get("sources"), list) and len(res["sources"]) == 1)
        check("fill 后 uncertainty 不再含 candidates",
              not any("candidates" in str(u) for u in res.get("uncertainty", [])))
        check("fill 后 uncertainty 仍含未填字段 legal_status",
              any("legal_status" in str(u) for u in res.get("uncertainty", [])))
        check("fill 后 change_records 有 2 条", len(res.get("change_records", [])) == 2)
        check("fill 不会覆盖 case_id", res.get("case_id") == "SYNTH-EXAMPLE-005")

        # ---------- 3. validate ----------
        rep_good = os.path.join(tmp, "validate_good.json")
        rc, log = run("contract_validate.py", "--case", case,
                      "--result", os.path.join(outdir, "result.json"),
                      "--out", rep_good)
        check("好结果 validate 通过（exit 0）", rc == 0, log.strip())
        check("好结果报告 overall=pass", jload(rep_good).get("overall") == "pass")

        rep_miss = os.path.join(tmp, "validate_missing.json")
        rc, log = run("contract_validate.py", "--case", case,
                      "--result", os.path.join(tmp, "result_bad_missing_field.json"),
                      "--out", rep_miss)
        rep = jload(rep_miss)
        v2 = next((r for r in rep["rules"] if r["id"] == "V2"), {})
        check("缺字段反例 validate 失败（exit 1）", rc == 1)
        check("缺字段反例触发 V2 fail", v2.get("status") == "fail",
              "; ".join(v2.get("messages", [])))

        rep_over = os.path.join(tmp, "validate_overclaim.json")
        rc, log = run("contract_validate.py", "--case", case,
                      "--result", os.path.join(tmp, "result_bad_overclaim.json"),
                      "--out", rep_over)
        rep = jload(rep_over)
        v3 = next((r for r in rep["rules"] if r["id"] == "V3"), {})
        check("过度声明反例 validate 失败（exit 1）", rc == 1)
        check("过度声明反例触发 V3 fail", v3.get("status") == "fail",
              "; ".join(v3.get("messages", [])))

        # ---------- 4. replay ----------
        runlog = os.path.join(tmp, "run_log.jsonl")
        manifest = os.path.join(tmp, "replay_manifest.json")
        rc, log = run("replay_pack.py", "log", "--runlog", runlog,
                      "--cmd", "scaffold_result.py --case case_fixture.json --fill fill.json",
                      "--inputs", case, os.path.join(tmp, "fill.json"),
                      "--outputs", os.path.join(outdir, "result.json"),
                      "--workdir", tmp)
        check("replay log 步骤 1 成功", rc == 0)
        rc, log = run("replay_pack.py", "log", "--runlog", runlog,
                      "--cmd", "contract_validate.py --case case_fixture.json --result result.json",
                      "--inputs", os.path.join(outdir, "result.json"),
                      "--outputs", rep_good,
                      "--workdir", tmp)
        check("replay log 步骤 2 成功", rc == 0)

        rc, log = run("replay_pack.py", "pack", "--runlog", runlog, "--out", manifest)
        check("replay pack 成功", rc == 0)
        man = jload(manifest)
        check("manifest 含 2 个有序步骤",
              [s.get("step") for s in man.get("steps", [])] == [1, 2])
        check("manifest 含环境说明", "python" in man.get("environment", {}))

        rc, log = run("replay_pack.py", "verify", "--manifest", manifest)
        check("verify 全部 fresh（exit 0）", rc == 0, log.strip().splitlines()[-1])
        check("verify 报告 2 步 fresh", "fresh=2" in log and "stale=0" in log)

        # 改动一个输入文件 → 对应步骤应变 stale
        with open(os.path.join(tmp, "fill.json"), "a", encoding="utf-8") as f:
            f.write("\n")
        rc, log = run("replay_pack.py", "verify", "--manifest", manifest)
        check("输入被改动后 verify 仍 exit 0（如实报告）", rc == 0)
        check("步骤 1 报告 stale", "步骤 1: stale" in log)
        check("步骤 2 仍 fresh", "步骤 2: fresh" in log)

        # ---------- 5. render ----------
        review = os.path.join(tmp, "review.md")
        rc, log = run("report_render.py", "--result", os.path.join(outdir, "result.json"),
                      "--manifest", manifest, "--out", review)
        check("render 退出码为 0", rc == 0)
        with open(review, "r", encoding="utf-8") as f:
            text = f.read()
        for sec in ("案例标识与状态", "主结果表", "来源清单",
                    "不确定性与未完成项", "变更记录", "可复跑性"):
            check(f"review.md 含章节「{sec}」", sec in text)
        check("review.md 标注 stale 状态", "stale" in text)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"[信息] 已清理临时目录: {tmp}")

    n_pass = sum(1 for _, ok in CHECKS if ok)
    print(f"\n[汇总] {n_pass}/{len(CHECKS)} 项断言通过")
    if n_pass != len(CHECKS):
        print("[结论] 自检未通过", file=sys.stderr)
        return 1
    print("[结论] 自检全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
