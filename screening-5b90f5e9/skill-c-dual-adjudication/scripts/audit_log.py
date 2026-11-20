#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_log.py — 汇总各阶段产物生成审计链 audit.jsonl，并做 PRISMA 式计数闭合校验。

用法:
    python3 audit_log.py [--work /app/work]

输出:
    <work>/audit.jsonl        每行 {stage, input_count, output_count,
      operator_role(system/S1/S2/arbiter), basis_files[], notes}
    <work>/audit_summary.json 各阶段计数 + 闭合校验结果

闭合校验（任一不闭合 exit 3 并打印差额）:
    1. identified = duplicates_removed + screened
    2. screened = S1 标注数 = S2 标注数
    3. screened = included + excluded + needs_human

退出码: 0=成功, 2=用法或IO错误, 3=计数不闭合
"""
import argparse
import json
import sys
import traceback
from pathlib import Path


def eprint(*a):
    print(*a, file=sys.stderr)


def count_jsonl(path):
    if not path.exists():
        return None
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def load_json(path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def main():
    ap = argparse.ArgumentParser(description="生成审计链并做 PRISMA 式计数闭合校验")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    work = Path(args.work)

    summary = load_json(work / "case_summary.json", {})
    dedup = load_json(work / "dedup_summary.json", {})
    agreement = load_json(work / "agreement_report.json", {})
    counts = load_json(work / "final_counts.json", {})
    disagreements = load_json(work / "disagreements.json", [])
    arbitrations = load_json(work / "arbitrations.json", [])

    n_records = count_jsonl(work / "records.jsonl")
    n_dedup = count_jsonl(work / "records_dedup.jsonl")
    n_ledger = count_jsonl(work / "dedup_ledger.jsonl")
    n_s1 = count_jsonl(work / "annotations_s1.jsonl")
    n_s2 = count_jsonl(work / "annotations_s2.jsonl")
    n_final = count_jsonl(work / "final_labels.jsonl")

    identified = dedup.get("identified", n_records)
    removed = dedup.get("duplicates_removed", n_ledger or 0)
    screened = dedup.get("screened", n_dedup)
    mode = summary.get("mode", "dual_model")
    ann_note = ("fixture 外部标注载入（输入 fixture，非金标准）"
                if mode == "dual_fixture" else "模型双视角独立标注（S2 未见 S1 结论）")

    entries = [
        {"stage": "parse_case", "input_count": len(summary.get("materials", [])),
         "output_count": 1, "operator_role": "system",
         "basis_files": ["/input/case.json", "/input/task.md"],
         "notes": f"mode={mode}; fixtures={len(summary.get('fixtures', []))}"},
        {"stage": "load_records", "input_count": len(summary.get("materials", []))
         - len(summary.get("fixtures", [])),
         "output_count": n_records, "operator_role": "system",
         "basis_files": [m.get("name") for m in summary.get("materials", [])],
         "notes": "导入 JSON/JSONL/CSV/RIS 题录"},
        {"stage": "exact_dedup", "input_count": identified, "output_count": screened,
         "operator_role": "system",
         "basis_files": ["records.jsonl", "dedup_ledger.jsonl"],
         "notes": f"保守精确去重 removed={removed}; "
                  f"suspected_pairs={len(dedup.get('suspected_pairs', []))}(仅列出未合并)"},
        {"stage": "annotate_s1", "input_count": screened, "output_count": n_s1,
         "operator_role": "S1",
         "basis_files": ["records_dedup.jsonl", "annotations_s1.jsonl"],
         "notes": ann_note},
        {"stage": "annotate_s2", "input_count": screened, "output_count": n_s2,
         "operator_role": "S2",
         "basis_files": ["records_dedup.jsonl", "annotations_s2.jsonl"],
         "notes": ann_note + "；标注顺序与 S1 互逆"},
        {"stage": "agreement", "input_count": (n_s1 or 0) + (n_s2 or 0),
         "output_count": len(disagreements), "operator_role": "system",
         "basis_files": ["annotations_s1.jsonl", "annotations_s2.jsonl",
                         "agreement_report.json", "disagreements.json"],
         "notes": f"agree={agreement.get('n_agree')}; "
                  f"kappa_3class={agreement.get('three_class', {}).get('kappa')}; "
                  f"kappa_binary={agreement.get('binary_include_vs_rest', {}).get('kappa')}"},
        {"stage": "adjudication", "input_count": len(disagreements),
         "output_count": len(arbitrations), "operator_role": "arbiter",
         "basis_files": ["disagreements.json", "arbitrations.json"],
         "notes": "逐条 D1-D4 分类 + 锚定依据；禁止平均/多数票掩盖实质争议"},
        {"stage": "finalize", "input_count": len(arbitrations),
         "output_count": n_final, "operator_role": "system",
         "basis_files": ["final_labels.jsonl", "final_counts.json"],
         "notes": f"include={counts.get('included')} exclude={counts.get('excluded')} "
                  f"needs_human={counts.get('needs_human')}"},
    ]
    with (work / "audit.jsonl").open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    checks = []
    c1_diff = (identified or 0) - (removed or 0) - (screened or 0)
    checks.append({"rule": "identified = duplicates_removed + screened",
                   "diff": c1_diff, "ok": c1_diff == 0})
    s_diff = None
    if n_s1 is not None and n_s2 is not None and screened is not None:
        s_diff = max(abs(screened - n_s1), abs(screened - n_s2))
    checks.append({"rule": "screened = S1标注数 = S2标注数",
                   "diff": s_diff, "ok": s_diff == 0})
    f_diff = None
    if counts:
        f_diff = (screened or 0) - (counts.get("included", 0)
                                    + counts.get("excluded", 0)
                                    + counts.get("needs_human", 0))
    checks.append({"rule": "screened = included + excluded + needs_human",
                   "diff": f_diff, "ok": f_diff == 0})

    audit_summary = {
        "mode": mode,
        "counts": {"identified": identified, "duplicates_removed": removed,
                   "screened": screened, "s1_annotations": n_s1,
                   "s2_annotations": n_s2,
                   "disagreements": len(disagreements),
                   "arbitrations": len(arbitrations),
                   "final_labels": n_final, **counts},
        "closure_checks": checks,
        "closed": all(c["ok"] for c in checks),
    }
    (work / "audit_summary.json").write_text(
        json.dumps(audit_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for c in checks:
        print(f"[audit_log] {c['rule']}: diff={c['diff']} "
              f"{'OK' if c['ok'] else 'FAIL'}")
    if not audit_summary["closed"]:
        eprint("[audit_log] 计数不闭合（差额见上），请回查各阶段产物")
        return 3
    print(f"[audit_log] 计数闭合；audit.jsonl 共 {len(entries)} 个阶段条目")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[audit_log] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)
