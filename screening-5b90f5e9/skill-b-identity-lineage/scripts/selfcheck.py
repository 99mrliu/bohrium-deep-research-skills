#!/usr/bin/env python3
"""selfcheck.py - 交付前终检。

检查项:
  1. result.json 存在且可解析，含 case_id；
  2. output_contract 全部字段存在且非空（合同字段齐）；
  3. 关键产物路径存在（records/pair_decisions/clusters.final/canonical/
     final_decisions/audit_summary）；
  4. 每个多副本簇合并依据非空；
  5. audit_summary.all_ok 为真（计数闭合）。

退出码: 0=通过; 2=输入不足（缺 case_summary 等）; 3=校验失败。
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="交付前终检")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()
    work, out_dir = Path(args.work), Path(args.output_dir)
    failures = []

    result_path = out_dir / "result.json"
    if not result_path.exists():
        failures.append("result.json 不存在")
        result = {}
    else:
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            failures.append(f"result.json 解析失败: {e}")
            result = {}
    if result and not result.get("case_id"):
        failures.append("result.json 缺少 case_id")

    summary_path = work / "case_summary.json"
    contract = []
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        contract = summary.get("output_contract") or []
    else:
        print("警告: case_summary.json 缺失，跳过合同字段比对", file=sys.stderr)
    for f in contract:
        if f not in result:
            failures.append(f"合同字段缺失: {f}")
        elif result[f] in (None, "", [], {}):
            failures.append(f"合同字段为空: {f}")

    for name in ("records.jsonl", "pair_decisions.jsonl", "canonical_records.json",
                 "final_decisions.jsonl", "audit_summary.json"):
        if not (work / name).exists():
            failures.append(f"产物缺失: {name}")
    if not (work / "clusters.final.json").exists() and not (work / "clusters.json").exists():
        failures.append("产物缺失: clusters.final.json")

    clus_path = work / "clusters.final.json"
    if not clus_path.exists():
        clus_path = work / "clusters.json"
    if clus_path.exists():
        clusters = json.loads(clus_path.read_text(encoding="utf-8"))["clusters"]
        bad = [c["cluster_id"] for c in clusters
               if len(c["members"]) > 1 and not c.get("merge_evidence")]
        if bad:
            failures.append(f"多副本簇缺合并依据: {bad}")

    audit_path = work / "audit_summary.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if not audit.get("all_ok"):
            failed = [c["name"] for c in audit.get("checks", []) if not c["ok"]]
            failures.append(f"计数闭合审计未通过: {failed}")

    if failures:
        print(json.dumps({"ok": False, "exit": 3, "failures": failures},
                         ensure_ascii=False))
        return 3
    if not summary_path.exists():
        print(json.dumps({"ok": True, "exit": 2,
                          "note": "case_summary 缺失，其余检查通过"}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "exit": 0, "checks": "all passed"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
