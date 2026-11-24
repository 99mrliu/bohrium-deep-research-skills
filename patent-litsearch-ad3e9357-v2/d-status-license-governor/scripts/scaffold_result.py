#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 结果骨架生成器（骨架先行 / honest partial first）。

用法:
    python3 scaffold_result.py --case case.json --out DIR [--fill fill.json] [--status ok|partial|failed]

行为:
    从 case.json 的 output_contract 提取全部字段名（容忍 dict / list / 缺失三种形态），
    生成镜像全部契约字段的 result.json 骨架，字段一律置 null 待填充；
    case_id / status / sources / uncertainty / change_records 填防御性默认值。
    对任何形态的 case.json 均防御：文件缺失、JSON 非法、契约缺失时仍产出最小骨架并警告。
    --fill 指定的 JSON 会按顶层键合并进骨架（填充值优先）。

退出码: 0 = 骨架已生成（含降级情形）; 2 = 用法错误。
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CONTRACT = ["case_id", "status", "legal_status", "license_report", "degradation_plan",
                    "conflicts", "wording_check", "sources", "uncertainty", "change_records"]
CORE_FIELDS = ["case_id", "status", "sources", "uncertainty", "change_records"]


def warn(msg):
    print(f"[scaffold 警告] {msg}", file=sys.stderr)


def load_case(path):
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        warn(f"case 文件不存在: {path}，按最小骨架继续")
        return {}
    try:
        case = json.loads(raw)
    except json.JSONDecodeError as exc:
        warn(f"case 文件不是合法 JSON: {exc}，按最小骨架继续")
        return {}
    if not isinstance(case, dict):
        warn("case 文件顶层不是 JSON 对象，按最小骨架继续")
        return {}
    return case


def contract_fields(case):
    oc = case.get("output_contract")
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        fields = []
        for item in oc:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field")
                if isinstance(name, str):
                    fields.append(name)
    else:
        if oc is not None:
            warn("output_contract 形态无法识别，使用默认契约字段")
        fields = list(DEFAULT_CONTRACT)
    if not fields:
        fields = list(DEFAULT_CONTRACT)
    for f in CORE_FIELDS:
        if f not in fields:
            fields.append(f)
    return fields


def deep_merge(base, fill):
    """一层深合并：dict 与 dict 合并，其余 fill 覆盖。"""
    for key, value in fill.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def main(argv=None):
    ap = argparse.ArgumentParser(description="结果骨架生成器（骨架先行）")
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True, help="输出目录，骨架写入 DIR/result.json")
    ap.add_argument("--fill", default=None, help="可选：填充值 JSON 文件")
    ap.add_argument("--status", default="partial", choices=["ok", "partial", "failed"],
                    help="骨架诚实状态，默认 partial")
    args = ap.parse_args(argv)

    case = load_case(args.case)
    fields = contract_fields(case)

    skeleton = {f: None for f in fields}
    skeleton["case_id"] = case.get("case_id") or "UNKNOWN"
    skeleton["status"] = args.status
    skeleton["sources"] = []
    skeleton["uncertainty"] = [
        "骨架先行：各契约字段待填充；任何未核验字段不得编造，法律状态未核验时一律声明 unknown。"
    ]
    skeleton["change_records"] = [{
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": "scaffold",
        "note": "预算纪律：先交付诚实 partial 骨架，再在剩余预算内逐字段改进。",
    }]

    if args.fill:
        try:
            fill = json.loads(Path(args.fill).read_text(encoding="utf-8"))
            if not isinstance(fill, dict):
                warn("--fill 顶层不是 JSON 对象，忽略填充")
            else:
                deep_merge(skeleton, fill)
        except FileNotFoundError:
            warn(f"--fill 文件不存在: {args.fill}，忽略填充")
        except json.JSONDecodeError as exc:
            warn(f"--fill 文件不是合法 JSON: {exc}，忽略填充")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "result.json"
    out_path.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[scaffold_result] 骨架已生成: {out_path}（status={skeleton['status']}，契约字段 {len(fields)} 个）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
