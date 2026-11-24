#!/usr/bin/env python3
"""step1_dedupe.py — 合成示例流水线·步骤1：题录去重。

去重键 = 规范化标题（小写、去非字母数字/中日韩文字符）+ "|" + 年份。
确定性：无时间戳/随机数/绝对路径；输出 JSON sort_keys、记录按 record_id 排序。
退出码：0=成功；2=输入缺失或非法（R1/R2）。
"""
import argparse
import json
import re
import sys


def eprint(*a):
    print(*a, file=sys.stderr)


def norm_title(s):
    return re.sub(r"[\W_]+", "", s.lower())


def main():
    ap = argparse.ArgumentParser(description="题录去重（规范化标题+年份为键）。")
    ap.add_argument("--input", required=True, help="题录 records.json")
    ap.add_argument("--output", required=True, help="输出去重结果 deduped.json")
    args = ap.parse_args()

    try:
        with open(args.input, encoding="utf-8") as f:
            records = json.load(f)
    except FileNotFoundError:
        eprint(f"R1: 输入文件不存在: {args.input}")
        return 2
    except json.JSONDecodeError as e:
        eprint(f"R2: 输入 JSON 非法: {e}")
        return 2
    if not isinstance(records, list):
        eprint("R2: 题录 JSON 顶层必须是数组")
        return 2

    seen = {}
    for r in records:
        key = norm_title(str(r.get("title", ""))) + "|" + str(r.get("year", ""))
        if key not in seen:
            seen[key] = r
    deduped = sorted(seen.values(), key=lambda r: str(r.get("record_id", "")))
    out = {
        "identified": len(records),
        "duplicates_removed": len(records) - len(deduped),
        "records": deduped,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"dedupe: identified={out['identified']} "
          f"duplicates_removed={out['duplicates_removed']} kept={len(deduped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
