#!/usr/bin/env python3
"""coverage_ledger.py — 字符覆盖台账（证据与契约核验技能 C 的组件 2）。

回答"提得全吗、丢的东西去哪了"：把原始抽取文本的字符总量，对账为
    kept     —— 进入了交付物（全文/表格/引文等）的字符；
    dropped  —— 有类别记账的剔除（页眉页脚、图形像素、重复抽取等）；
    unaccounted —— 两边都没解释的剩余（>2% 时整体状态必须为 partial）。
用法：
    python3 coverage_ledger.py --raw raw_dump.txt \
        --kept fulltext.md table_1.csv ... \
        --dropped drops.jsonl --out /app/work
drops.jsonl 每行：{"category": "header_footer|figure_pixels|duplicate|unreadable",
                   "chars": <int>}  （按类记账，可多条累加）
输出 coverage_ledger.json；退出码 0=对账平衡；2=存在未解释字符；3=输入不可用。
"""
import argparse
import json
import os
import re
import sys

CATEGORIES = ("header_footer", "figure_pixels", "duplicate",
              "unreadable", "other_declared")


def visible_chars(text):
    return len(re.sub(r"\s+", "", text))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True, help="原始抽取全文（pdftotext 等）")
    ap.add_argument("--kept", nargs="+", required=True,
                    help="进入交付物的文本文件（可多个）")
    ap.add_argument("--dropped", help="drops.jsonl（可选）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=float, default=2.0,
                    help="unaccounted 占比阈值（%%），默认 2")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if not os.path.exists(args.raw):
        print(json.dumps({"status": "failed", "reason": "raw_missing"}))
        return 3
    with open(args.raw, encoding="utf-8", errors="replace") as f:
        raw_chars = visible_chars(f.read())
    kept, kept_detail = 0, []
    for kp in args.kept:
        if not os.path.exists(kp):
            kept_detail.append({"file": kp, "missing": True})
            continue
        with open(kp, encoding="utf-8", errors="replace") as f:
            n = visible_chars(f.read())
        kept += n
        kept_detail.append({"file": os.path.basename(kp), "chars": n})

    dropped = {c: 0 for c in CATEGORIES}
    bad = []
    if args.dropped and os.path.exists(args.dropped):
        with open(args.dropped, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                cat = d.get("category", "other_declared")
                if cat not in dropped:
                    bad.append(f"未知剔除类别 {cat}，归入 other_declared")
                    cat = "other_declared"
                dropped[cat] += int(d.get("chars", 0))
    dropped_total = sum(dropped.values())
    unaccounted = max(0, raw_chars - kept - dropped_total)
    pct = round(100.0 * unaccounted / raw_chars, 2) if raw_chars else 0.0
    balanced = pct <= args.threshold
    ledger = {
        "status": "balanced" if balanced else "unbalanced",
        "raw_chars": raw_chars,
        "kept_chars": kept,
        "kept_detail": kept_detail,
        "dropped": {k: v for k, v in dropped.items() if v},
        "dropped_total": dropped_total,
        "unaccounted_chars": unaccounted,
        "unaccounted_pct": pct,
        "threshold_pct": args.threshold,
        "rule": "unaccounted_pct > 阈值时，result.json 的 status 必须为 partial，"
                "并在 uncertainty 列出未解释字符的可能来源",
        "notes": bad,
    }
    with open(os.path.join(args.out, "coverage_ledger.json"), "w",
              encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": ledger["status"],
                      "unaccounted_pct": pct}, ensure_ascii=False))
    return 0 if balanced else 2


if __name__ == "__main__":
    sys.exit(main())
