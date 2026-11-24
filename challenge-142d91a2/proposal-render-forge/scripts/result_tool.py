#!/usr/bin/env python3
"""result_tool.py -- result.json 初始化 / 填值 / 收尾校验（本 bundle 独立实现）。

用法:
    python3 result_tool.py init  CASE_JSON RESULT_JSON
    python3 result_tool.py set   RESULT_JSON KEY VALUE
    python3 result_tool.py final RESULT_JSON

纪律（对应 SPEC 第 4 节）:
  init   读 case.json，逐字段抄录 output_contract（不凭题面猜字段名），
         生成 status=partial 骨架：全部契约字段置 null，附 sources /
         uncertainty / change_records；
  set    填充单个契约字段或 sources/uncertainty（KEY 为这些键之一），
         并自动追加一条 change_records；
  final  校验契约字段齐备度：任何字段仍为 null/空字符串则强制
         status=partial 并在 uncertainty 点名；齐全才允许 status=ok。
         校验结论以 JSON 打印到 stdout；退出码恒为 0（结论看 stdout）。

值编码: set 的 VALUE 若是合法 JSON（如 ["a","b"]）按 JSON 解析，
否则按普通字符串处理。
"""
import json
import sys
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def cmd_init(case_path, result_path):
    case = load(case_path)
    contract = case.get("output_contract")
    if not isinstance(contract, dict) or not contract:
        sys.exit("case.json 缺少 output_contract 对象，无法初始化 result.json")
    result = {
        "case_id": case.get("case_id"),
        "status": "partial",
        "sources": [],
        "uncertainty": ["result 骨架已初始化，契约字段尚未填充：%s"
                        % "、".join(contract.keys())],
        "change_records": [{"time": now(), "op": "init",
                            "detail": "按 output_contract 逐字段抄录生成 partial 骨架"}],
    }
    for key in contract:
        result[key] = None
    save(result_path, result)
    print(json.dumps({"op": "init", "case_id": result["case_id"],
                      "contract_fields": list(contract.keys()),
                      "status": "partial"}, ensure_ascii=False))


def parse_value(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def cmd_set(result_path, key, raw_value):
    result = load(result_path)
    if key not in result:
        sys.exit("result.json 中不存在键 %s（契约字段须先由 init 建立）" % key)
    if key in ("status", "case_id", "change_records"):
        sys.exit("键 %s 不允许用 set 直接改写" % key)
    result[key] = parse_value(raw_value)
    result["change_records"].append(
        {"time": now(), "op": "set", "detail": "填充字段 %s" % key})
    save(result_path, result)
    print(json.dumps({"op": "set", "key": key}, ensure_ascii=False))


def cmd_final(result_path):
    result = load(result_path)
    contract_keys = [k for k in result
                     if k not in ("case_id", "status", "sources",
                                  "uncertainty", "change_records")]
    missing = [k for k in contract_keys
               if result[k] is None or result[k] == ""]
    if missing:
        result["status"] = "partial"
        note = "契约字段未齐备，强制 partial；缺项：%s" % "、".join(missing)
        if note not in result["uncertainty"]:
            result["uncertainty"].append(note)
    else:
        result["status"] = "ok"
        result["uncertainty"] = [u for u in result["uncertainty"]
                                 if not u.startswith("契约字段未齐备")
                                 and not u.startswith("result 骨架已初始化")]
    result["change_records"].append(
        {"time": now(), "op": "final",
         "detail": "契约字段校验：缺项 %d 个" % len(missing)})
    save(result_path, result)
    print(json.dumps({"op": "final", "status": result["status"],
                      "missing": missing}, ensure_ascii=False))


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        sys.exit("usage: result_tool.py init CASE_JSON RESULT_JSON\n"
                 "       result_tool.py set RESULT_JSON KEY VALUE\n"
                 "       result_tool.py final RESULT_JSON")
    cmd = argv[1]
    if cmd == "init" and len(argv) == 4:
        cmd_init(argv[2], argv[3])
    elif cmd == "set" and len(argv) == 5:
        cmd_set(argv[2], argv[3], argv[4])
    elif cmd == "final" and len(argv) == 3:
        cmd_final(argv[2])
    else:
        sys.exit("参数数量错误，见 --help")


if __name__ == "__main__":
    main(sys.argv)
