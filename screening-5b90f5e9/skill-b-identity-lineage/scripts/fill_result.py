#!/usr/bin/env python3
"""fill_result.py - 把流水线产物增量填充进 /app/output/result.json。

已知合同字段的填充来源（映射表见 SKILL.md 第 4 节）:
  case_id / skill_name / status / product / evidence_matrix /
  sources / uncertainty / change_records / counts / checks
合同额外字段：保留原值；若为 null 则在 uncertainty.pending_fields 登记，
由运行时模型按语义补充（本脚本不臆造内容）。

幂等：重复运行覆盖由本脚本负责的字段，不动其它字段。

退出码: 0=成功; 2=输入不足（骨架或产物缺失，能填多少填多少）; 3=失败。
"""
import argparse
import json
import sys
from pathlib import Path

SKILL_NAME = "identitylineage-dedup-first"
KNOWN_FIELDS = ["case_id", "skill_name", "status", "product", "evidence_matrix",
                "sources", "uncertainty", "change_records", "counts", "checks"]


def load_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def main() -> int:
    ap = argparse.ArgumentParser(description="增量填充 result.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()
    work, out_dir = Path(args.work), Path(args.output_dir)
    result_path = out_dir / "result.json"
    code = 0

    if result_path.exists():
        result = load_json(result_path, {})
    else:
        code = 2
        result = {}
        out_dir.mkdir(parents=True, exist_ok=True)

    summary = load_json(work / "case_summary.json", {}) or {}
    audit = load_json(work / "audit_summary.json")
    counts = load_json(work / "screening_counts.json")
    canonical = load_json(work / "canonical_records.json", {}) or {}

    decisions = []
    dec_path = work / "final_decisions.jsonl"
    if dec_path.exists():
        decisions = [json.loads(l) for l in dec_path.read_text(encoding="utf-8").splitlines()
                     if l.strip()]
    conflicts = []
    conf_path = work / "conflict_log.jsonl"
    if conf_path.exists():
        conflicts = [json.loads(l) for l in conf_path.read_text(encoding="utf-8").splitlines()
                     if l.strip()]

    if audit is None or counts is None or not decisions:
        code = 2

    result["case_id"] = summary.get("case_id") or result.get("case_id") or "UNKNOWN"
    result["skill_name"] = SKILL_NAME
    result["status"] = "completed" if (audit or {}).get("all_ok") else "degraded"
    result["product"] = {
        "final_decisions": str(dec_path) if dec_path.exists() else None,
        "canonical_records": str(work / "canonical_records.json"),
        "clusters_final": str(work / "clusters.final.json"),
        "pair_decisions": str(work / "pair_decisions.jsonl"),
        "audit_summary": str(work / "audit_summary.json"),
        "note": "快照式筛选：仅覆盖本案例输入材料，非实时数据库检索，不声称全局召回",
    }
    result["evidence_matrix"] = [
        {"canonical_id": d["canonical_id"], "decision": d["decision"],
         "reason_code": d["reason_code"], "evidence_quote": d.get("evidence_quote"),
         "members": d["members"]}
        for d in decisions
    ]
    result["sources"] = [
        {"file": m.get("name"), "format": m.get("sniffed_format"),
         "size_bytes": m.get("size_bytes")}
        for m in summary.get("material_files", [])
    ]
    result["uncertainty"] = {
        "conflicts": conflicts,
        "needs_human": [d["canonical_id"] for d in decisions
                        if d["decision"] == "needs_human"],
        "warnings": (summary.get("warnings") or []),
        "snapshot_only": True,
        "no_live_search": True,
        "human_review_fabricated": False,
    }
    result["change_records"] = [
        {"step": "scaffold", "detail": "result.json 骨架按 output_contract 生成"},
        {"step": "import", "detail": "多格式导入嗅探 → records.jsonl（field_status 三级语义）"},
        {"step": "identity_resolve", "detail": "三层匹配 → pair_decisions/clusters/review_queue"},
        {"step": "arbitration", "detail": "Tier3 候选对经模型批量仲裁（rationale 必填）"},
        {"step": "canonical", "detail": "字段级确定性合并 + 版本谱系链"},
        {"step": "screening", "detail": "canonical 级判定，evidence_quote 子串锚定校验"},
        {"step": "audit", "detail": "计数闭合审计"},
    ]
    result["counts"] = {
        "identified": (audit or {}).get("identified"),
        "canonical": (audit or {}).get("canonical"),
        "merged_copies": (audit or {}).get("merged_copies"),
        "screened": (counts or {}).get("screened"),
        "included": (counts or {}).get("included"),
        "excluded": (counts or {}).get("excluded"),
        "needs_human": (counts or {}).get("needs_human"),
        "propagated_records": (counts or {}).get("propagated_records"),
        "field_conflicts": len(conflicts),
    }
    result["checks"] = (audit or {}).get("checks", [])

    # 合同额外字段：为 null 者登记待补充
    contract = summary.get("output_contract") or []
    pending = [f for f in contract
               if f not in KNOWN_FIELDS and result.get(f) in (None, "", [], {})]
    if pending:
        result.setdefault("uncertainty", {})["pending_fields"] = pending
        code = max(code, 2)

    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": code == 0, "status": result["status"],
                      "pending_fields": pending, "path": str(result_path)},
                     ensure_ascii=False))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(3)
