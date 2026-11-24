#!/usr/bin/env python3
"""resultkit.py -- result.json 的初始化 / 填值 / 收尾校验（独立实现）。

纪律（SPEC 第 4 节）：
  init  读 case.json，生成骨架：case_id、output_contract 全部字段
        （初值 null）、status="partial"、sources、uncertainty、
        change_records；先落盘一个诚实的 partial，再逐步改进。
  set   给契约字段填值（JSON 文本，或 @路径 从文件读取），自动登记
        change_records。
  final 校验契约字段齐备度：空值（null/""/[]/{}）即缺项，缺项强制
        status="partial" 并在 uncertainty 逐一点名；齐全才允许 "ok"。

用法:
    python3 resultkit.py init CASE_JSON OUT_JSON
    python3 resultkit.py set RESULT_JSON KEY VALUE
    python3 resultkit.py final RESULT_JSON
退出码: init/set 0=成功 2=用法或文件错误; final 0=ok 1=partial(缺项)
"""
import json
import sys
import time

EMPTY = (None, "", [], {})


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _contract_fields(case):
    oc = case.get("output_contract", [])
    fields = []
    for item in oc:
        if isinstance(item, str):
            fields.append(item)
        elif isinstance(item, dict) and item.get("name"):
            fields.append(item["name"])
    return fields


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def cmd_init(case_path, out_path):
    case = _load(case_path)
    fields = _contract_fields(case)
    if not case.get("case_id") or not fields:
        sys.stderr.write("resultkit init: case.json 缺 case_id 或 "
                         "output_contract\n")
        return 2
    doc = {"case_id": case["case_id"], "status": "partial",
           "sources": [], "uncertainty": [
               "result.json 由 resultkit init 生成，契约字段待填"],
           "change_records": [{"ts": _now(), "action": "init",
                               "detail": "按 output_contract 生成骨架，"
                                         "status=partial"}]}
    for k in fields:
        doc[k] = None
    _save(out_path, doc)
    print(json.dumps({"status": "partial", "contract_fields": fields},
                     ensure_ascii=False))
    return 0


def cmd_set(result_path, key, value):
    doc = _load(result_path)
    if value.startswith("@"):
        val = _load(value[1:])
    else:
        try:
            val = json.loads(value)
        except json.JSONDecodeError:
            val = value
    doc[key] = val
    doc.setdefault("change_records", []).append(
        {"ts": _now(), "action": "set", "detail": "填字段 %s" % key})
    _save(result_path, doc)
    print(json.dumps({"set": key}, ensure_ascii=False))
    return 0


def cmd_final(result_path):
    doc = _load(result_path)
    if not doc.get("case_id"):
        sys.stderr.write("resultkit final: 缺 case_id\n")
        return 2
    # 契约字段 = 除元字段外的全部顶层键
    meta = {"case_id", "status", "sources", "uncertainty", "change_records"}
    fields = [k for k in doc if k not in meta]
    missing = [k for k in fields if doc[k] in EMPTY]
    unc = [u for u in doc.get("uncertainty", [])
           if not str(u).startswith("契约字段缺失")]
    if missing:
        doc["status"] = "partial"
        unc += ["契约字段缺失: %s" % k for k in missing]
    else:
        doc["status"] = "ok"
    doc["uncertainty"] = unc
    doc.setdefault("change_records", []).append(
        {"ts": _now(), "action": "final",
         "detail": "契约校验：缺项 %d 个 -> status=%s"
                   % (len(missing), doc["status"])})
    _save(result_path, doc)
    print(json.dumps({"status": doc["status"], "missing": missing},
                     ensure_ascii=False))
    return 0 if doc["status"] == "ok" else 1


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    cmd = argv[1]
    try:
        if cmd == "init" and len(argv) == 4:
            return cmd_init(argv[2], argv[3])
        if cmd == "set" and len(argv) == 5:
            return cmd_set(argv[2], argv[3], argv[4])
        if cmd == "final" and len(argv) == 3:
            return cmd_final(argv[2])
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write("resultkit %s: %s\n" % (cmd, e))
        return 2
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
