#!/usr/bin/env python3
"""selfcheck.py — 交付前终检（最后一步，脚本环节）。

检查：
  1) result.json 存在且可解析，且含 output_contract 全部字段（从 case_summary 读）；
  2) 关键产物文件存在；result.json 中引用的绝对路径产物都存在；
  3) decisions.jsonl 每条都带非空 primary_reason_code；
  4) 计数闭合（复算 prisma 两条等式）。
打印逐项 PASS/FAIL 摘要；全过 exit 0，任一失败 exit 3。
"""
import argparse
import json
import sys
from pathlib import Path

REQUIRED_ARTIFACTS = ["criteria_table.json", "decisions.jsonl",
                      "screening_summary.json", "audit_summary.json",
                      "dedup_ledger.jsonl", "normalized.jsonl"]


def iter_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_strings(v)


def main(argv=None):
    ap = argparse.ArgumentParser(description="交付前终检")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--output-dir", default="/app/output", help="输出目录（默认 /app/output）")
    args = ap.parse_args(argv)
    work = Path(args.work)
    out_dir = Path(args.output_dir)

    results = []

    def check(name, ok, detail=""):
        results.append({"check": name, "pass": bool(ok), "detail": detail})
        return ok

    # 1) result.json 与合同字段
    result_path = out_dir / "result.json"
    result = None
    if not result_path.exists():
        check("result.json 存在", False, f"{result_path} 不存在")
    else:
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            check("result.json 存在且可解析", True)
        except Exception as e:
            check("result.json 存在且可解析", False, str(e))
    missing_fields = []
    summary_path = work / "case_summary.json"
    if result is not None and summary_path.exists():
        fields = json.loads(summary_path.read_text(encoding="utf-8")).get(
            "output_contract_fields") or []
        missing_fields = [f for f in fields if f not in result]
        check("output_contract 字段齐备", not missing_fields,
              f"缺字段: {missing_fields}" if missing_fields else f"{len(fields)} 个字段齐")
    elif result is not None:
        check("output_contract 字段齐备", False, "case_summary.json 缺失，无法核对合同")

    # 2) 产物文件与路径引用
    missing_artifacts = [a for a in REQUIRED_ARTIFACTS if not (work / a).exists()]
    check("关键产物齐备", not missing_artifacts,
          f"缺: {missing_artifacts}" if missing_artifacts else "全部存在")
    bad_refs = []
    if result is not None:
        for s in iter_strings(result):
            if s.startswith("/") and ("." in Path(s).name):
                if not Path(s).exists():
                    bad_refs.append(s)
    check("result.json 引用的绝对路径存在", not bad_refs,
          f"失效引用: {bad_refs[:5]}" if bad_refs else "无失效引用")

    # 3) decisions 全部带理由码
    no_code = 0
    dec_path = work / "decisions.jsonl"
    n_dec = 0
    if dec_path.exists():
        for line in dec_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            n_dec += 1
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                no_code += 1
                continue
            if not d.get("primary_reason_code"):
                no_code += 1
    check("decisions 全部带理由码", dec_path.exists() and no_code == 0,
          f"{n_dec} 条中 {no_code} 条缺码" if no_code else f"{n_dec} 条均带码")

    # 4) 计数闭合
    try:
        dedup = json.loads((work / "dedup_summary.json").read_text(encoding="utf-8"))
        screen = json.loads((work / "screening_summary.json").read_text(encoding="utf-8"))
        eq1 = dedup["identified"] == dedup["duplicates_removed"] + screen["screened"]
        eq2 = screen["screened"] == screen["included"] + screen["excluded"] + screen["needs_human"]
        check("计数闭合", eq1 and eq2,
              f"eq1={eq1} eq2={eq2}")
    except Exception as e:
        check("计数闭合", False, f"汇总文件读取失败: {e}")

    n_pass = sum(1 for r in results if r["pass"])
    all_ok = n_pass == len(results)
    print("=" * 60)
    for r in results:
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['check']}"
              + (f" — {r['detail']}" if r["detail"] else ""))
    print(f"[selfcheck] {'PASS' if all_ok else 'FAIL'} ({n_pass}/{len(results)})")
    print("=" * 60)
    return 0 if all_ok else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[selfcheck] 未预期错误: {e}", file=sys.stderr)
        sys.exit(3)
