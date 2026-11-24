#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 端到端自查（基于合成 fixtures）。

覆盖断言:
    1. status_ok.jsonl 校验通过（退出码 0，无违规）；
    2. status_bad_aggregator.jsonl 触发 S1（退出码 1）；
    3. status_bad_unknown.jsonl 触发 S2 与 S6（退出码 1）；
    4. license classify 产出 绿2/黄2/红1，plan 产出非空降级规则与 checklist；
    5. wording_guard 通过 conclusions_ok.md，拦截 conclusions_bad_wording.md（含行号）；
    6. 冲突用例（两来源结论相左）产出已披露冲突块，登记级来源胜出头条；
    7. scaffold_result 镜像 case_fixture 全部契约字段。

退出码: 0 = 全部断言通过; 1 = 任一断言失败。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIX = ROOT / "examples" / "fixtures"

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))


def run(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *[str(a) for a in args]],
                          capture_output=True, text=True)


def stdout_json(proc):
    return json.loads(proc.stdout)


def main():
    with tempfile.TemporaryDirectory(prefix="governor_selfcheck_") as tmp:
        tmp = Path(tmp)

        # 1. 合法台账通过
        p = run("status_ledger.py", "validate", "--ledger", FIX / "status_ok.jsonl",
                "--sources", FIX / "sources.json")
        ok_report = None
        try:
            ok_report = stdout_json(p)
        except Exception:
            pass
        check("status_ok.jsonl 校验通过（rc=0）", p.returncode == 0, f"rc={p.returncode}")
        check("status_ok.jsonl 无违规", ok_report is not None and ok_report.get("ok") is True
              and ok_report.get("violations") == [])

        # 2. 聚合页当登记依据 → S1
        p = run("status_ledger.py", "validate", "--ledger", FIX / "status_bad_aggregator.jsonl",
                "--sources", FIX / "sources.json")
        rep = None
        try:
            rep = stdout_json(p)
        except Exception:
            pass
        check("status_bad_aggregator.jsonl 失败（rc=1）", p.returncode == 1, f"rc={p.returncode}")
        check("status_bad_aggregator.jsonl 命中 S1",
              rep is not None and any(v.get("rule") == "S1" for v in rep.get("violations", [])))

        # 3. 缺 query_date + 非 ISO 生效日 → S2 + S6
        p = run("status_ledger.py", "validate", "--ledger", FIX / "status_bad_unknown.jsonl",
                "--sources", FIX / "sources.json")
        rep = None
        try:
            rep = stdout_json(p)
        except Exception:
            pass
        rules = {v.get("rule") for v in (rep or {}).get("violations", [])}
        check("status_bad_unknown.jsonl 失败（rc=1）", p.returncode == 1, f"rc={p.returncode}")
        check("status_bad_unknown.jsonl 命中 S2 与 S6", {"S2", "S6"} <= rules, f"rules={sorted(rules)}")

        # 4. license 分级与降级规划
        lic_out = tmp / "license_report.json"
        p = run("license_tiers.py", "classify", "--sources", FIX / "sources.json", "--out", lic_out)
        lic = None
        try:
            lic = json.loads(lic_out.read_text(encoding="utf-8"))
        except Exception:
            pass
        check("license classify 正常完成（rc=0）", p.returncode == 0, f"rc={p.returncode}")
        summ = (lic or {}).get("summary", {})
        check("license 分级为 绿2/黄2/红1",
              summ.get("green") == 2 and summ.get("yellow") == 2 and summ.get("red") == 1,
              f"summary={summ}")

        plan_out = tmp / "degradation_plan.json"
        p = run("license_tiers.py", "plan", "--sources", FIX / "sources.json", "--out", plan_out)
        plan = None
        try:
            plan = json.loads(plan_out.read_text(encoding="utf-8"))
        except Exception:
            pass
        check("license plan 正常完成（rc=0）", p.returncode == 0, f"rc={p.returncode}")
        rules_list = (plan or {}).get("rules", [])
        check("降级规划非空且含红级 do_not_fetch",
              bool(rules_list) and any(r.get("rule") == "do_not_fetch" for r in rules_list))
        check("能力降级 checklist 非空", bool((plan or {}).get("checklist")))

        # 5. 措辞守门
        wg_ok = tmp / "wg_ok.json"
        p = run("wording_guard.py", "--conclusions", FIX / "conclusions_ok.md",
                "--ledger", FIX / "status_ok.jsonl", "--sources", FIX / "sources.json",
                "--out", wg_ok)
        check("conclusions_ok.md 通过措辞守门（rc=0）", p.returncode == 0, f"rc={p.returncode}")

        wg_bad = tmp / "wg_bad.json"
        p = run("wording_guard.py", "--conclusions", FIX / "conclusions_bad_wording.md",
                "--ledger", FIX / "status_ok.jsonl", "--sources", FIX / "sources.json",
                "--out", wg_bad)
        wg = None
        try:
            wg = json.loads(wg_bad.read_text(encoding="utf-8"))
        except Exception:
            pass
        wviol = (wg or {}).get("violations", [])
        check("conclusions_bad_wording.md 被拦截（rc=1）", p.returncode == 1, f"rc={p.returncode}")
        check("拦截报告含行号", bool(wviol) and all(isinstance(v.get("line"), int) and v["line"] >= 1
                                                    for v in wviol))
        check("拦截覆盖确定性措辞与 FTO 两类",
              {v.get("kind") for v in wviol} >= {"definitive_on_unverified", "fto_out_of_scope"},
              f"kinds={sorted({v.get('kind') for v in wviol})}")

        # 6. 冲突用例：登记级 vs 公报级相左 → 披露 + 登记级头条
        conflict_ledger = tmp / "status_conflict.jsonl"
        conflict_ledger.write_text(
            '{"patent_ref": "CN-FICT-900001X", "asserted_status": "granted", '
            '"status_effective_date": "2023-01-01", "source_id": "REG-CNIPA-FICT", '
            '"query_date": "2026-11-20", "note": "合成示例/虚构：冲突用例，登记簿称授权。"}\n'
            '{"patent_ref": "CN-FICT-900001X", "asserted_status": "expired", '
            '"status_effective_date": "2025-01-01", "source_id": "GAZ-CN-FICT", '
            '"query_date": "2026-11-21", "note": "合成示例/虚构：冲突用例，公报称届满。"}\n',
            encoding="utf-8")
        p = run("status_ledger.py", "validate", "--ledger", conflict_ledger,
                "--sources", FIX / "sources.json")
        rep = None
        try:
            rep = stdout_json(p)
        except Exception:
            pass
        conflicts = (rep or {}).get("conflicts", [])
        headline = ((rep or {}).get("headline_statuses") or {}).get("CN-FICT-900001X", {})
        check("冲突用例不产生违规（rc=0）", p.returncode == 0, f"rc={p.returncode}")
        check("冲突块已披露且双方保留",
              len(conflicts) == 1 and conflicts[0].get("conflict_disclosed") is True
              and len(conflicts[0].get("assertions", [])) == 2)
        check("头条状态由登记级来源胜出（granted）",
              headline.get("status") == "granted" and headline.get("tier") == "register",
              f"headline={headline}")

        # 7. scaffold 镜像契约字段
        out_dir = tmp / "out"
        p = run("scaffold_result.py", "--case", FIX / "case_fixture.json", "--out", out_dir)
        result = None
        try:
            result = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        case = json.loads((FIX / "case_fixture.json").read_text(encoding="utf-8"))
        expected = set(case["output_contract"].keys())
        check("scaffold_result 正常完成（rc=0）", p.returncode == 0, f"rc={p.returncode}")
        check("result.json 镜像全部契约字段",
              result is not None and expected <= set(result.keys()),
              f"missing={sorted(expected - set((result or {}).keys()))}")
        check("骨架默认 status=partial 且 case_id 正确",
              result is not None and result.get("status") == "partial"
              and result.get("case_id") == "SYNTH-EXAMPLE-004")

    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n自查合计: {len(RESULTS)} 项，通过 {len(RESULTS) - len(failed)}，失败 {len(failed)}")
    if failed:
        print("失败项: " + "; ".join(failed))
        return 1
    print("全部断言通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
