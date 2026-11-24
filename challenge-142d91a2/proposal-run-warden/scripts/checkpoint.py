#!/usr/bin/env python3
"""checkpoint.py -- 原子检查点工具：保证任何时刻 result.json 都是有效交付。

子命令：
  init    CASE RESULT [--log LOG]      读 case.json，生成诚实 partial 骨架
  save    RESULT [--log LOG] [选项]    原子替换 result.json 并追加检查点日志
  status  RESULT [--log LOG]           随时报告当前有效交付状态

原子性约定：所有 result.json 写入先落 <path>.tmp、fsync 后再 os.replace；
检查点日志为 append-only JSONL（时间戳 / 预算消耗自报 / 完成度自评 / 当前降级层级）。
"""
import argparse
import datetime
import json
import os
import sys

LEVELS = ("L0", "L1", "L2", "L3", "L4")


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write_json(path, obj):
    """先写临时文件再 os.replace：崩溃不会留下半个 JSON。"""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, os.path.basename(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _append_log(log_path, entry):
    if not log_path:
        return
    directory = os.path.dirname(os.path.abspath(log_path))
    os.makedirs(directory, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _filled_fields(doc):
    fields = doc.get("_contract_fields", [])
    return [k for k in fields if doc.get(k) not in (None, "", [], {})]


def cmd_init(a):
    case = _read_json(a.case)
    contract = case.get("output_contract") or {}
    fields = list(contract.keys()) if isinstance(contract, dict) else list(contract)
    now = _utc_now()
    doc = {
        "case_id": case.get("case_id", "unknown"),
        "status": "partial",
        "generated_by": "proposal-run-warden (run-warden checkpoint protocol)",
        "created_at": now,
        "sources": [],
        "uncertainty": ["初始化完成：仅读取契约，七要素尚未起草，全部字段待填"],
        "change_records": [
            {"at": now, "action": "init",
             "detail": "按 output_contract 逐字段抄录建立骨架，初始降级层级 L4"}
        ],
    }
    for key in fields:
        doc.setdefault(key, None)
    doc["_contract_fields"] = fields
    _atomic_write_json(a.result, doc)
    _append_log(a.log, {
        "at": now, "event": "init", "case_id": doc["case_id"],
        "requests_used": a.requests_used, "tokens_used": None,
        "completion_pct": 0, "level": "L4",
        "note": "契约骨架建立，诚实 partial 已可交付"})
    print(json.dumps({"case_id": doc["case_id"], "status": "partial",
                      "contract_fields": fields, "level": "L4"},
                     ensure_ascii=False))


def cmd_save(a):
    doc = _read_json(a.result)
    now = _utc_now()
    updated = []
    for pair in a.set or []:
        key, sep, raw = pair.partition("=")
        if not sep:
            sys.exit("--set 需要 KEY=JSON_VALUE 形式: %r" % pair)
        try:
            doc[key] = json.loads(raw)
        except json.JSONDecodeError:
            doc[key] = raw
        updated.append(key)
    for pair in a.set_file or []:
        key, sep, path = pair.partition("=")
        if not sep:
            sys.exit("--set-file 需要 KEY=PATH 形式: %r" % pair)
        with open(path, encoding="utf-8") as fh:
            doc[key] = fh.read()
        updated.append(key)
    if a.level and a.level not in LEVELS:
        sys.exit("--level 必须是 %s 之一" % "/".join(LEVELS))
    entry = {
        "at": now, "event": "checkpoint", "note": a.note,
        "requests_used": a.requests_used, "tokens_used": a.tokens_used,
        "completion_pct": a.completion, "level": a.level,
        "fields_updated": updated,
    }
    _append_log(a.log, entry)
    doc.setdefault("change_records", []).append({
        "at": now, "action": "checkpoint",
        "detail": a.note or ("更新字段: " + ",".join(updated)),
        "level": a.level, "completion_pct": a.completion})
    if a.sources_file:
        with open(a.sources_file, encoding="utf-8") as fh:
            doc["sources"] = json.load(fh)
        updated.append("sources")
    doc["updated_at"] = now
    _atomic_write_json(a.result, doc)
    filled = _filled_fields(doc)
    missing = [k for k in doc.get("_contract_fields", []) if k not in filled]
    print(json.dumps({"checkpoint_logged": True, "fields_updated": updated,
                      "fields_filled": filled, "fields_missing": missing,
                      "level": a.level, "completion_pct": a.completion},
                     ensure_ascii=False))


def cmd_status(a):
    doc = _read_json(a.result)
    filled = _filled_fields(doc)
    missing = [k for k in doc.get("_contract_fields", []) if k not in filled]
    last = None
    if a.log and os.path.exists(a.log):
        with open(a.log, encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        if lines:
            last = json.loads(lines[-1])
    print(json.dumps({
        "status": doc.get("status"),
        "valid_json": True,
        "fields_filled": filled,
        "fields_missing": missing,
        "uncertainty_count": len(doc.get("uncertainty", [])),
        "last_checkpoint": last,
    }, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(
        description="原子检查点工具（详见文件顶部 docstring）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="读契约，生成诚实 partial 骨架")
    p.add_argument("case")
    p.add_argument("result")
    p.add_argument("--log", default=None, help="检查点日志 JSONL 路径")
    p.add_argument("--requests-used", type=int, default=1)

    p = sub.add_parser("save", help="原子替换 result.json 并打点")
    p.add_argument("result")
    p.add_argument("--log", default=None)
    p.add_argument("--set", action="append", metavar="KEY=JSON",
                   help="以 JSON 字面量更新字段，可重复")
    p.add_argument("--set-file", action="append", metavar="KEY=PATH",
                   help="以文本文件内容更新字段，可重复")
    p.add_argument("--sources-file", default=None,
                   help="来源清单 JSON 文件路径")
    p.add_argument("--note", default="")
    p.add_argument("--requests-used", type=int, default=None)
    p.add_argument("--tokens-used", type=int, default=None)
    p.add_argument("--completion", type=int, default=None,
                   help="完成度自评 0-100")
    p.add_argument("--level", default=None, help="当前降级层级 L0-L4")

    p = sub.add_parser("status", help="报告当前有效交付状态")
    p.add_argument("result")
    p.add_argument("--log", default=None)

    a = ap.parse_args()
    {"init": cmd_init, "save": cmd_save, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
