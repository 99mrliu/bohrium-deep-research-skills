#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 生成 /app/output/result.json 骨架。

从 /input/case.json 读取 case_id 与 output_contract，镜像填充契约全部字段，
并预置证据治理与风险分级所需的结构：
  case_id, status, claims（每条带 evidence 引用与 risk grade 占位）,
  legal_status（台账引用）, authorization（授权分级引用）,
  sources, uncertainty, change_records。

设计意图：执行预算紧张（64 次模型请求/900 秒），开工即先落一份诚实的
partial 骨架，之后每完成一步就地增量更新，确保任何中断都有可提交的
诚实部分结果。status 初始为 "partial"，全部核验通过后才允许改 "ok"。

CLI：
  python3 scaffold_result.py --case /input/case.json --out /app/output/result.json
      [--force] [--note "..."]
退出码：0 成功；1 输入非法或输出已存在且未 --force。仅依赖标准库。
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

CORE_FIELDS = {
    "case_id", "status", "claims", "legal_status", "authorization",
    "sources", "uncertainty", "change_records",
}


def _default_for_spec(spec):
    """按 output_contract 字段规格给出占位默认值。"""
    if isinstance(spec, dict):
        t = (spec.get("type") or "").casefold()
        if t == "array":
            return []
        if t == "object":
            return {}
        if t == "number":
            return 0
        if t == "boolean":
            return False
        return ""
    if isinstance(spec, list):
        return []
    return ""


def build_skeleton(case, note=None):
    now = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    case_id = case.get("case_id") or case.get("id") or "unknown-case"
    skeleton = {
        "case_id": case_id,
        "status": "partial",
        "claims": [],
        "legal_status": {
            "records": [],
            "protocol": "rules/legal_status_protocol.md（登记优先；未知纪律）",
            "note": "当前官方法律状态未核验前一律填'未知'，不得编造",
        },
        "authorization": {
            "tiers": [],
            "rules": "rules/authorization_boundary.md（绿/黄/红分级与降级方案）",
        },
        "sources": [],
        "uncertainty": [
            "骨架初始状态：各项结论尚未完成引文闸控与状态核验",
        ],
        "change_records": [
            {"timestamp": now, "action": "scaffold_created",
             "detail": note or "由 scaffold_result.py 生成；status=partial，待管线逐步填充"},
        ],
        "_evidence_governance": {
            "pipeline": [
                "scripts/evidence_ledger.py append/validate（登记证据）",
                "scripts/quote_audit.py（确定性引文回核）",
                "scripts/status_ledger.py validate（法律状态核验协议）",
                "scripts/license_tiers.py classify（数据源授权分级）",
                "scripts/risk_grade.py grade（结论风险分级）",
            ],
            "discipline": "所有输出论断必须引文闸控：逐字引文+定位+回核通过",
        },
    }
    # 镜像 output_contract 全部字段（契约字段优先于骨架占位）
    contract = case.get("output_contract") or {}
    mirrored = []
    if isinstance(contract, dict):
        for key, spec in contract.items():
            mirrored.append(key)
            if key in CORE_FIELDS or key in skeleton:
                continue  # 骨架已提供结构化占位，视为已镜像
            skeleton[key] = _default_for_spec(spec)
    skeleton["_contract_mirrored_fields"] = mirrored
    return skeleton


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成 result.json 骨架（镜像 output_contract）")
    ap.add_argument("--case", default="/input/case.json", help="case.json 路径")
    ap.add_argument("--out", default="/app/output/result.json", help="输出路径")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出")
    ap.add_argument("--note", default=None, help="写入首条 change_record 的说明")
    args = ap.parse_args(argv)

    case_path = Path(args.case)
    if not case_path.exists():
        print("ERROR: case.json 不存在: %s" % args.case, file=sys.stderr)
        return 1
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("ERROR: case.json 解析失败: %s" % e, file=sys.stderr)
        return 1
    if not isinstance(case, dict):
        print("ERROR: case.json 必须是 JSON 对象", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    if out_path.exists() and not args.force:
        print("ERROR: 输出已存在（%s），用 --force 覆盖" % args.out, file=sys.stderr)
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)

    skeleton = build_skeleton(case, note=args.note)
    out_path.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print("OK: 骨架已写入 %s（镜像契约字段 %d 个：%s）"
          % (out_path, len(skeleton["_contract_mirrored_fields"]),
             ",".join(skeleton["_contract_mirrored_fields"]) or "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
