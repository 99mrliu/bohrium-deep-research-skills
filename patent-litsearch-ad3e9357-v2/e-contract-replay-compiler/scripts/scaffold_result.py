#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_result.py — 契约镜像脚手架生成器（result-contract-replay-compiler）

在任何检索/分析工作开始之前先落地一份诚实的 result.json：
  * case_id 与 output_contract 从任意形态的 case.json 中防御式提取；
  * 契约字段一律镜像为 null 并列入 uncertainty（绝不编造）；
  * 初始 status 默认 partial；
  * 后续每次调用（--fill 深度合并）都会重写 result.json 并追加 change_records；
  * fill 永远不会覆盖 case_id。

退出码：0 成功；2 用法/输入错误（文件不存在、JSON 解析失败等）。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

RESERVED_KEYS = ("case_id", "status", "sources", "uncertainty", "change_records")
STATUSES = ("ok", "partial", "failed")
CASE_ID_KEYS = ("case_id", "caseId", "id", "case_no", "case_number")
CONTRACT_KEYS = ("output_contract", "outputContract", "output-contract",
                 "deliverable_contract")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path, what):
    if not os.path.isfile(path):
        print(f"[错误] {what} 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[错误] {what} JSON 解析失败: {path}: {e}", file=sys.stderr)
        sys.exit(2)


def find_case_id(case):
    """防御式提取 case_id；返回 (case_id, warning_or_None)。"""
    if isinstance(case, dict):
        for k in CASE_ID_KEYS:
            v = case.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip(), None
        for holder in ("case", "meta", "header", "task"):
            sub = case.get(holder)
            if isinstance(sub, dict):
                for k in CASE_ID_KEYS:
                    v = sub.get(k)
                    if isinstance(v, str) and v.strip():
                        return v.strip(), None
    return "UNKNOWN-CASE", "未能在 case.json 中定位 case_id，已使用占位值 UNKNOWN-CASE"


def find_contract_fields(case):
    """防御式提取 output_contract 字段名列表；返回 (fields, warning_or_None)。

    支持三种契约形态：{字段名: 描述}、["字段名", ...]、[{"name": ...}, ...]。
    """
    def extract(c):
        if isinstance(c, dict):
            return [str(k) for k in c.keys()]
        if isinstance(c, list):
            out = []
            for item in c:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict) and isinstance(item.get("name"), str):
                    out.append(item["name"])
            return out
        return []

    if isinstance(case, dict):
        for k in CONTRACT_KEYS:
            if k in case:
                return extract(case[k]), None
        for holder in ("task", "spec", "requirements", "case"):
            sub = case.get(holder)
            if isinstance(sub, dict):
                for k in CONTRACT_KEYS:
                    if k in sub:
                        return extract(sub[k]), None
    return [], "未在 case.json 中找到 output_contract，生成空契约镜像（请人工确认交付要求）"


def deep_merge(base, patch):
    """深度合并：dict 递归合并，其余类型（含 list）整体替换。返回新对象。"""
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = dict(base)
        for k, v in patch.items():
            merged[k] = deep_merge(merged[k], v) if k in merged else v
        return merged
    return patch


def field_entry(field):
    return f"{field}: 未填写（脚手架初始化为 null，待补）"


def sync_uncertainty(result, fields):
    """按契约字段当前取值同步 uncertainty：null → 确保有名目；非 null → 移除名目。"""
    unc = result.get("uncertainty")
    if not isinstance(unc, list):
        unc = []
    kept = []
    for entry in unc:
        s = str(entry)
        named = next((f for f in fields
                      if s.startswith(f + ":") or s.startswith(f + "：") or s == f), None)
        if named is not None and result.get(named) is not None:
            continue  # 字段已填写，移除其 uncertainty 名目
        kept.append(entry)
    for f in fields:
        if result.get(f) is None and not any(
                str(e).startswith(f + ":") or str(e).startswith(f + "：") or str(e) == f
                for e in kept):
            kept.append(field_entry(f))
    result["uncertainty"] = kept


def main():
    ap = argparse.ArgumentParser(
        description="生成/更新契约镜像 result.json（诚实 partial 优先落地）")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--out", required=True, help="输出目录（result.json 写入其中）")
    ap.add_argument("--fill", help="可选：fill.json，深度合并进结果")
    ap.add_argument("--status", choices=STATUSES, default=None,
                    help="交付状态；首次缺省为 partial，后续缺省沿用既有值")
    ap.add_argument("--note", default=None, help="写入 change_records 的说明")
    args = ap.parse_args()

    case = load_json(args.case, "case.json")
    case_id, warn_id = find_case_id(case)
    fields, warn_contract = find_contract_fields(case)
    for w in (warn_id, warn_contract):
        if w:
            print(f"[警告] {w}", file=sys.stderr)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "result.json")

    if os.path.isfile(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        print(f"[信息] 复用既有结果文件: {out_path}")
        # 契约里新出现的字段补镜像
        for fld in fields:
            if fld not in result:
                result[fld] = [] if fld in ("sources", "uncertainty") else None
    else:
        result = {
            "case_id": case_id,
            "status": "partial",
            "sources": [],
            "uncertainty": [],
            "change_records": [],
        }
        for fld in fields:
            if fld not in result:
                result[fld] = None

    if args.status:
        result["status"] = args.status

    if args.fill:
        fill = load_json(args.fill, "fill.json")
        if isinstance(fill, dict):
            fill = {k: v for k, v in fill.items() if not k.startswith("_")}
            if "case_id" in fill:
                del fill["case_id"]
                print("[警告] fill.json 中含 case_id，已忽略（case_id 只能来自 case.json）",
                      file=sys.stderr)
        result = deep_merge(result, fill)

    result["case_id"] = case_id if result.get("case_id") in (None, "UNKNOWN-CASE") \
        else result["case_id"]
    if warn_id is None:
        result["case_id"] = case_id  # case.json 永远权威

    sync_uncertainty(result, fields)

    if not isinstance(result.get("change_records"), list):
        result["change_records"] = []
    result["change_records"].append({
        "ts": utc_now(),
        "note": args.note or ("脚手架初始化" if not args.fill else f"合并 fill: {args.fill}"),
    })

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    null_fields = [f_ for f_ in fields if result.get(f_) is None]
    print(f"[完成] result.json 已写入: {out_path}")
    print(f"  case_id        : {result['case_id']}")
    print(f"  status         : {result['status']}")
    print(f"  契约字段数     : {len(fields)}（仍为 null: {len(null_fields)}）")
    print(f"  uncertainty    : {len(result['uncertainty'])} 条")
    print(f"  change_records : {len(result['change_records'])} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
