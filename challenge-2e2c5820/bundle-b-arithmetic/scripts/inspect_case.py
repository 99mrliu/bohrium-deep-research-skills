#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inspect_case.py — case.json 结构探针（schema 无关）

用法:
    python3 inspect_case.py <case.json> <out.json>

功能:
    不假设 case.json 的字段名。递归扫描整个 JSON，按关键字模式定位:
      - 顶层键清单
      - case_id
      - 候选方案 (plan / 方案 / candidate)
      - 合同 (contract / price / booking / 合同 / 价格 / 预约)
      - 参数域 (domain / 参数域 / parameter)
      - 预算上限 (cap / 上限 / budget / 预算)
      - 截止时间窗 (deadline / 截止 / 窗口 / window)
      - output_contract / 输出契约
    输出一份 "JSON 路径地图"，模型据此从真实位置抽取，而不是猜字段名。

退出码:
    0  成功
    2  用法错误
    3  case.json 不可读 / 不是合法 JSON
"""
import json
import re
import sys
from pathlib import Path

PATTERNS = {
    "plans": re.compile(r"plan|方案|candidate", re.IGNORECASE),
    "contracts": re.compile(r"contract|price|booking|合同|价格|报价|预约", re.IGNORECASE),
    "domains": re.compile(r"domain|参数域|参数范围|parameter", re.IGNORECASE),
    "caps": re.compile(r"cap|上限|budget|预算", re.IGNORECASE),
    "deadlines": re.compile(r"deadline|window|截止|窗口", re.IGNORECASE),
    "output_contract": re.compile(r"output_contract|输出契约", re.IGNORECASE),
}
CASE_ID_KEY = re.compile(r"^case_?id$", re.IGNORECASE)


def preview(value, depth=0):
    if isinstance(value, dict):
        keys = list(value.keys())[:8]
        return "dict{" + ", ".join(str(k) for k in keys) + ("..." if len(value) > 8 else "") + "}"
    if isinstance(value, list):
        head = "list[%d]" % len(value)
        if value and isinstance(value[0], dict):
            ids = []
            for item in value[:10]:
                if isinstance(item, dict):
                    for k in ("plan_id", "id", "name", "version"):
                        if k in item:
                            ids.append(str(item[k]))
                            break
            if ids:
                head += " ids=" + ",".join(ids)
        return head
    if isinstance(value, (str, int, float, bool)):
        s = str(value)
        return s if len(s) <= 60 else s[:57] + "..."
    return type(value).__name__


def walk(node, path, hits, case_ids):
    if isinstance(node, dict):
        for k, v in node.items():
            p = "%s.%s" % (path, k) if path else str(k)
            if CASE_ID_KEY.search(str(k)) and isinstance(v, (str, int)):
                case_ids.append({"path": p, "value": str(v)})
            for name, pat in PATTERNS.items():
                if pat.search(str(k)):
                    hits.setdefault(name, []).append(
                        {"path": p, "kind": type(v).__name__, "preview": preview(v)}
                    )
            walk(v, p, hits, case_ids)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, "%s[%d]" % (path, i), hits, case_ids)


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("用法: python3 inspect_case.py <case.json> <out.json>\n")
        return 2
    case_path, out_path = Path(argv[1]), Path(argv[2])
    try:
        text = case_path.read_text(encoding="utf-8")
        case = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("错误(exit 3): 无法读取或解析 case.json %s: %s\n" % (case_path, exc))
        return 3
    if not isinstance(case, (dict, list)):
        sys.stderr.write("错误(exit 3): case.json 顶层必须是 object 或 array\n")
        return 3

    hits, case_ids = {}, []
    walk(case, "", hits, case_ids)
    top_keys = list(case.keys()) if isinstance(case, dict) else ["<list[%d]>" % len(case)]

    contract_fields = []
    for hit in hits.get("output_contract", []):
        # 尝试取回该路径的值，列出字段名
        node = case
        try:
            for part in re.findall(r"[^.\[\]]+|\[\d+\]", hit["path"]):
                node = node[int(part[1:-1])] if part.startswith("[") else node[part]
            if isinstance(node, dict):
                props = node.get("properties") if isinstance(node.get("properties"), dict) else node
                contract_fields = [str(k) for k in props.keys()]
                hit["fields"] = contract_fields
        except Exception:  # noqa: BLE001
            pass

    result = {
        "probe": "inspect_case.py",
        "case_file": str(case_path),
        "top_level_keys": top_keys,
        "case_id": case_ids[0]["value"] if case_ids else None,
        "case_id_path": case_ids[0]["path"] if case_ids else None,
        "candidates": hits,
        "output_contract_fields": contract_fields,
        "note": "所有 path 均为 case.json 内的真实 JSON 路径；模型必须按这些路径定位后再抽取。",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("inspect 完成: 顶层键 %d 个; 命中 " % len(top_keys) +
          ", ".join("%s=%d" % (k, len(v)) for k, v in hits.items()))
    print("地图已写入 %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
