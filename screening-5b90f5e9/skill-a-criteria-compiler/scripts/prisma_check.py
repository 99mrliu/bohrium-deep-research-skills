#!/usr/bin/env python3
"""prisma_check.py — 计数闭合校验 + PRISMA 风格流量与逐步审计（步骤 9，脚本环节）。

闭合等式（任一不闭合 → exit 3 并打印差额）：
  identified = duplicates_removed + screened
  screened   = included + excluded + needs_human

输出 audit_summary.json：逐步 {stage, input_count, output_count, operator
（system/model）, basis_files}，可被第三人独立复跑核对。

退出码：0=闭合；2=输入不足；3=不闭合。幂等。
"""
import argparse
import json
import sys
from pathlib import Path


def load(work, name, required=True):
    p = Path(work) / name
    if not p.exists():
        if required:
            print(f"[prisma_check] 缺少 {p}，输入不足。", file=sys.stderr)
            sys.exit(2)
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[prisma_check] {p} 解析失败: {e}", file=sys.stderr)
        sys.exit(2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="计数闭合校验与审计输出")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    args = ap.parse_args(argv)
    work = Path(args.work)

    case_summary = load(work, "case_summary.json", required=False) or {}
    norm = load(work, "normalize_summary.json")
    dedup = load(work, "dedup_summary.json")
    screen = load(work, "screening_summary.json")

    identified = dedup.get("identified", norm.get("identified"))
    duplicates_removed = dedup.get("duplicates_removed")
    screened = screen.get("screened")
    included = screen.get("included")
    excluded = screen.get("excluded")
    needs_human = screen.get("needs_human")

    checks = []
    ok = True

    eq1_lhs, eq1_rhs = identified, (duplicates_removed or 0) + (screened or 0)
    c1 = {"name": "identified = duplicates_removed + screened",
          "lhs": eq1_lhs, "rhs": eq1_rhs, "pass": eq1_lhs == eq1_rhs}
    checks.append(c1)
    if not c1["pass"]:
        ok = False
        print(f"[prisma_check] 不闭合: identified({eq1_lhs}) != "
              f"duplicates_removed+screened({eq1_rhs})，差额={eq1_lhs - eq1_rhs}",
              file=sys.stderr)

    eq2_lhs, eq2_rhs = screened, (included or 0) + (excluded or 0) + (needs_human or 0)
    c2 = {"name": "screened = included + excluded + needs_human",
          "lhs": eq2_lhs, "rhs": eq2_rhs, "pass": eq2_lhs == eq2_rhs}
    checks.append(c2)
    if not c2["pass"]:
        ok = False
        print(f"[prisma_check] 不闭合: screened({eq2_lhs}) != "
              f"included+excluded+needs_human({eq2_rhs})，差额={eq2_lhs - eq2_rhs}",
              file=sys.stderr)

    criteria_version = screen.get("criteria_version")
    n_criteria = None
    ct_path = work / "criteria_table.json"
    if ct_path.exists():
        try:
            n_criteria = len(json.loads(ct_path.read_text(encoding="utf-8")).get("criteria") or [])
        except Exception:
            n_criteria = None

    audit = {
        "case_id": case_summary.get("case_id"),
        "prisma_flow": {
            "identified": identified,
            "duplicates_removed": duplicates_removed,
            "screened": screened,
            "included": included,
            "excluded": excluded,
            "needs_human": needs_human,
        },
        "closure_checks": checks,
        "stages": [
            {"stage": "intake", "input_count": case_summary.get("materials_count"),
             "output_count": len(case_summary.get("records_files") or []),
             "operator": "system",
             "basis_files": ["/input/case.json", "/input/task.md",
                             str(work / "case_summary.json")]},
            {"stage": "normalize", "input_count": len(norm.get("per_file") or []),
             "output_count": norm.get("identified"), "operator": "system",
             "basis_files": [str(work / "normalized.jsonl"),
                             str(work / "normalize_summary.json")]},
            {"stage": "dedup", "input_count": identified, "output_count": dedup.get("groups"),
             "operator": "system",
             "basis_files": [str(work / "dedup_ledger.jsonl"),
                             str(work / "dedup_summary.json")]},
            {"stage": "model_judgment",
             "input_count": (screened or 0) * (n_criteria or 0) if n_criteria is not None else None,
             "output_count": screen.get("judgments_total"), "operator": "model",
             "basis_files": [str(work / "criteria_table.json"),
                             str(work / "judgments.jsonl")]},
            {"stage": "screening_synthesis", "input_count": screened,
             "output_count": screened, "operator": "system",
             "basis_files": [str(work / "decisions.jsonl"),
                             str(work / "screening_summary.json")]},
        ],
        "criteria_version": criteria_version,
        "generated_by": "prisma_check.py",
        "stage": "audit",
    }
    out = work / "audit_summary.json"
    out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    status = "CLOSED" if ok else "NOT_CLOSED"
    print(f"[prisma_check] {status}: identified={identified} dup_removed={duplicates_removed} "
          f"screened={screened} inc={included} exc={excluded} nh={needs_human} -> {out}")
    return 0 if ok else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[prisma_check] 未预期错误（诚实降级）: {e}", file=sys.stderr)
        sys.exit(2)
