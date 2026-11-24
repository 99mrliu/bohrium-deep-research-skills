#!/usr/bin/env python3
"""make_result.py — 写出/更新 result.json。

- case_id 从 case.json 原样复制（绝不改写）。
- output_contract 的全部字段以 case.json 实际内容为准，用 --artifact 字段=路径 逐个映射；
  未映射的字段置 null 并在 notes 注明。
- status ∈ {success, partial, unable_to_determine}，必须诚实：
  有 infeasible / pending_review / 材料缺失时不得写 success。
- sources 默认收录 materials 目录全部文件 + facts.jsonl 等中间产物，可用 --source 追加。
- --uncertainty / --note / --artifact / --change-record 均可重复。

用法（第一条命令就落一个合法的 partial result）：
  python3 make_result.py --case /input/case.json --materials-dir /input/materials \
      --out /app/output/result.json --status partial --note "boot placeholder"
定稿：
  python3 make_result.py --case /input/case.json --out /app/output/result.json \
      --status partial --artifact revised_manuscript=/app/output/revised-manuscript.md ...
仅 Python 3 标准库。
"""
import argparse
import json
import os
import sys


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser(description="写出/更新 result.json")
    ap.add_argument("--case", required=True, help="case.json 路径")
    ap.add_argument("--out", required=True, help="result.json 输出路径")
    ap.add_argument("--status", default="partial",
                    choices=["success", "partial", "unable_to_determine"])
    ap.add_argument("--materials-dir", default=None,
                    help="扫描该目录填充 sources")
    ap.add_argument("--artifact", action="append", default=[],
                    metavar="FIELD=PATH", help="output_contract 字段映射，可重复")
    ap.add_argument("--uncertainty", action="append", default=[])
    ap.add_argument("--note", action="append", default=[])
    ap.add_argument("--source", action="append", default=[])
    ap.add_argument("--change-record", action="append", default=[],
                    help="change_records JSON 文件路径，可重复")
    args = ap.parse_args()

    case = load_json(args.case)
    if not isinstance(case, dict):
        print("ERROR cannot read case.json: %s" % args.case, file=sys.stderr)
        sys.exit(2)
    case_id = case.get("case_id")
    contract = case.get("output_contract") or {}
    if isinstance(contract, list):  # 兼容 ["field1", ...] 形式
        contract = {k: None for k in contract}
    if not isinstance(contract, dict):
        contract = {}

    # 已有 result 则增量更新（boot 之后定稿不丢字段）
    old = load_json(args.out, {}) or {}

    artifacts = dict(old.get("artifacts") or {})
    for kv in args.artifact:
        if "=" not in kv:
            print("WARN bad --artifact %r (expect FIELD=PATH)" % kv, file=sys.stderr)
            continue
        k, v = kv.split("=", 1)
        artifacts[k.strip()] = v.strip()

    # 丢弃上一轮自动生成的"未映射字段"提示，按本轮 artifact 重新计算
    notes = [n for n in (old.get("notes") or [])
             if not str(n).startswith("output_contract 未映射字段")]
    notes += args.note
    unmapped = [k for k in contract if k not in artifacts]
    if unmapped:
        notes.append("output_contract 未映射字段（置 null）: %s" % ", ".join(unmapped))
    for k in contract:
        artifacts.setdefault(k, None)

    sources = list(old.get("sources") or [])
    if args.materials_dir and os.path.isdir(args.materials_dir):
        for root, _dirs, files in os.walk(args.materials_dir):
            for name in sorted(files):
                sources.append(os.path.join(root, name))
    sources += args.source
    seen, sources_u = set(), []
    for s in sources:
        if s not in seen:
            seen.add(s)
            sources_u.append(s)

    change_records = list(old.get("change_records") or [])
    for path in args.change_record:
        obj = load_json(path)
        if isinstance(obj, dict) and "changes" in obj:
            change_records += obj["changes"]
        elif isinstance(obj, list):
            change_records += obj
        else:
            notes.append("WARN change-record 无法解析: %s" % path)

    result = {
        "case_id": case_id,
        "status": args.status,
        "artifacts": artifacts,
        "sources": sources_u,
        "uncertainty": list(old.get("uncertainty") or []) + args.uncertainty,
        "change_records": change_records,
        "notes": notes,
        "disclaimer": ("本结果为基线摘要上的修订草案：意见按 reviewer-comments.md "
                       "摘要转述（非逐字审稿原文）；未补做任何真实实验；"
                       "不代表原作者已改稿或编辑部已接收。"),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("make_result: case_id=%r status=%s artifacts=%d -> %s"
          % (case_id, args.status, len(artifacts), args.out))


if __name__ == "__main__":
    main()
