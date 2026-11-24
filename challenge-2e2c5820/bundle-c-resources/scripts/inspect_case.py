#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inspect_case.py — schema 无关的 case.json 结构探针。

用法: python3 inspect_case.py <case.json> <out.json>

case.json 的字段名不固定，本脚本按键名模式递归定位:
方案列表 / 库存清单 / 供应商与报价合同 / 预订日历 / 样本台账 /
伦理状态字段 / output_contract，输出 JSON 路径映射供后续步骤使用。
匹配结果为候选（候选路径需模型或人工确认语义），绝不据此直接下结论。

退出码: 0 正常; 2 用法错误; 3 case 文件不可读或不是合法 JSON。
"""
import json
import sys
from pathlib import Path

KEY_PATTERNS = {
    "plans": ["plan", "方案"],
    "inventory": ["inventory", "equipment", "device", "material", "stock",
                  "仪器", "设备", "物料", "库存", "清单"],
    "contracts": ["contract", "supplier", "price", "quote", "vendor",
                  "合同", "报价", "采购", "外协", "供应商"],
    "booking": ["booking", "calendar", "schedule", "reservation",
                "预订", "预约", "排期", "日历"],
    "samples": ["sample", "specimen", "样本", "样品"],
    "ethics": ["ethic", "伦理"],
    "output_contract": ["output_contract", "outputcontract", "输出契约", "输出字段"],
}


def walk(node, path, hits, ethics_fields):
    if isinstance(node, dict):
        for key, value in node.items():
            p = "{}.{}".format(path, key)
            kl = str(key).casefold()
            for cat, pats in KEY_PATTERNS.items():
                if any(pt in kl for pt in pats):
                    hits.setdefault(cat, []).append({
                        "path": p,
                        "type": type(value).__name__,
                        "length": len(value) if isinstance(value, (list, dict)) else None,
                    })
            if any(pt in kl for pt in KEY_PATTERNS["ethics"]) \
                    and not isinstance(value, (dict, list)):
                ethics_fields.append({"path": p, "value": value})
            walk(value, p, hits, ethics_fields)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            walk(item, "{}[{}]".format(path, i), hits, ethics_fields)


def main(argv):
    if len(argv) != 3:
        print("用法: python3 inspect_case.py <case.json> <out.json>", file=sys.stderr)
        return 2
    case_path, out_path = Path(argv[1]), Path(argv[2])
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("ERROR: 无法读取 case 文件 {}: {}".format(case_path, e), file=sys.stderr)
        return 3
    hits, ethics_fields = {}, []
    walk(case, "$", hits, ethics_fields)
    case_id = None
    if isinstance(case, dict):
        for k in ("case_id", "caseId", "id", "案例编号"):
            if isinstance(case.get(k), (str, int)):
                case_id = case[k]
                break
    oc = None
    if isinstance(case, dict):
        for k, v in case.items():
            if "output_contract" in str(k).casefold():
                oc = {"path": "$." + str(k),
                      "fields": sorted(v.keys()) if isinstance(v, dict) else v}
    result = {
        "case_id": case_id,
        "candidates": hits,
        "ethics_fields": ethics_fields,
        "output_contract": oc,
        "note": "候选路径由键名模式匹配得到，使用前须由模型/人工确认语义，"
                "不得仅凭键名直接采信。",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print("inspect_case: 写入 {} (case_id={})".format(out_path, case_id))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
