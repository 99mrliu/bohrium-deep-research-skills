#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_annotations.py — 校验一份标注表：取值合法 + evidence_quote 子串锚定。

用法:
    python3 validate_annotations.py [--sheet /app/work/annotations_s1.jsonl] [--work /app/work]

校验规则（逐行）:
    1. record_id 必须存在于 records_dedup.jsonl；
    2. decision ∈ {include, exclude, uncertain}；
    3. reason_code 非空；
    4. evidence_quote 归一化（NFKC+小写+压缩空白）后必须是该记录
       title/abstract 归一化文本的子串；decision=uncertain 可免引用，但 note 必填。

失败: 失败清单写 <work>/validation_errors_<表名>.json 并 exit 3（重锚后重跑）。
退出码: 0=成功, 2=用法或IO错误, 3=校验失败
"""
import argparse
import json
import re
import sys
import traceback
import unicodedata
from pathlib import Path

DECISIONS = {"include", "exclude", "uncertain"}


def eprint(*a):
    print(*a, file=sys.stderr)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"\s+", " ", s).strip()


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser(description="校验标注表的合法性与证据锚定")
    ap.add_argument("--sheet", default=None, help="标注表路径（默认 <work>/annotations_s1.jsonl）")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    work = Path(args.work)
    sheet = Path(args.sheet) if args.sheet else work / "annotations_s1.jsonl"

    if not sheet.exists():
        eprint(f"[validate_annotations] 缺少标注表 {sheet}")
        return 2
    dedup_path = work / "records_dedup.jsonl"
    if not dedup_path.exists():
        eprint(f"[validate_annotations] 缺少 {dedup_path}")
        return 2

    records = {r["record_id"]: r for r in load_jsonl(dedup_path)}
    texts = {rid: norm(r.get("title", "") + " " + r.get("abstract", ""))
             for rid, r in records.items()}

    rows = load_jsonl(sheet)
    errors = []
    seen = set()
    for i, row in enumerate(rows, 1):
        rid = str(row.get("record_id", "")).strip()
        dec = str(row.get("decision", "")).strip()
        rc = str(row.get("reason_code", "")).strip()
        quote = str(row.get("evidence_quote", "")).strip()
        note = str(row.get("note", "")).strip()
        loc = f"行{i}(record_id={rid or '?'})"
        if not rid or rid not in records:
            errors.append({"loc": loc, "error": "record_id 未知或为空"})
            continue
        if rid in seen:
            errors.append({"loc": loc, "error": "record_id 重复标注"})
        seen.add(rid)
        if dec not in DECISIONS:
            errors.append({"loc": loc, "error": f"decision 非法: '{dec}'"})
        if not rc:
            errors.append({"loc": loc, "error": "reason_code 为空"})
        if dec == "uncertain":
            if not quote and not note:
                errors.append({"loc": loc,
                               "error": "uncertain 免引用时 note 必填（说明缺什么信息）"})
        else:
            if not quote:
                errors.append({"loc": loc, "error": "evidence_quote 为空"})
            elif norm(quote) not in texts[rid]:
                errors.append({"loc": loc,
                               "error": "evidence_quote 未锚定到该记录 title/abstract",
                               "quote": quote})

    missing = sorted(set(records) - seen)
    for rid in missing:
        errors.append({"loc": f"record_id={rid}", "error": "该记录未被标注"})

    if errors:
        err_path = work / f"validation_errors_{sheet.stem}.json"
        err_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        eprint(f"[validate_annotations] 校验失败 {len(errors)} 处 -> {err_path}；"
               f"请修正（重锚 evidence_quote）后重跑")
        return 3
    print(f"[validate_annotations] {sheet.name}: {len(rows)} 条全部通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[validate_annotations] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)
