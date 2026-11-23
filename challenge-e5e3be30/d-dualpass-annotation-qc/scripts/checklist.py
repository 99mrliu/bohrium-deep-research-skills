#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""checklist.py — 批量核验清单生成器。

把 claims 列表转成可勾选的批量引用检查清单（CSV + Markdown），供人工复核、
其他 Agent 复跑或标注项目复用。

输入 claims.json 支持两种形态：
  1. 字符串数组：["论断1", "论断2", ...]（claim_id 自动编为 C1..Cn）；
  2. 对象数组：[{"claim_id": "C1", "claim_text": "...", "slots": ["数值", "页码"]}, ...]
     （claim_id 可缺省，slots 可缺省）。

输出：
  - checklist.csv（UTF-8 带 BOM，Excel 可直接打开）：勾选/claim_id/论断原文/
    待查槽位/证据位置(页)/判定/复核人/复核日期 八列；
  - checklist.md：每条论断一个 "- [ ]" 勾选项 + 待填表格。

schema 错误 exit 1；用法错误 exit 2；正常 exit 0。
"""
import argparse
import csv
import json
import sys

VERDICTS = "supported / partially_supported / contradicted / insufficient_evidence"
DEFAULT_SLOTS = ["关键数值/实体", "原文页码", "原文引句", "四级判定"]
CSV_HEADER = ["勾选", "claim_id", "论断原文", "待查槽位", "证据位置(页)",
              "判定", "复核人", "复核日期"]


def fail(msg):
    print(f"[checklist] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def load_claims(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"文件不存在: {path}")
    except json.JSONDecodeError as e:
        fail(f"JSON 解析失败: {path}: {e}")
    if isinstance(data, dict):
        for key in ("claims", "claims_to_verify", "records"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
    if not isinstance(data, list) or not data:
        fail("claims 必须是非空数组（或含 claims/claims_to_verify 数组的对象）")
    claims = []
    for i, item in enumerate(data):
        if isinstance(item, str):
            if not item.strip():
                fail(f"claims[{i}]: 空字符串论断")
            claims.append({"claim_id": f"C{i + 1}", "claim_text": item.strip(),
                           "slots": list(DEFAULT_SLOTS)})
        elif isinstance(item, dict):
            text = item.get("claim_text") or item.get("claim") or item.get("text")
            if not isinstance(text, str) or not text.strip():
                fail(f"claims[{i}]: 缺少非空 claim_text 字段")
            slots = item.get("slots", list(DEFAULT_SLOTS))
            if not isinstance(slots, list) or any(not isinstance(s, str) for s in slots):
                fail(f"claims[{i}]: slots 必须是字符串数组")
            claims.append({
                "claim_id": str(item.get("claim_id") or f"C{i + 1}"),
                "claim_text": text.strip(),
                "slots": slots or list(DEFAULT_SLOTS),
            })
        else:
            fail(f"claims[{i}]: 元素必须是字符串或对象")
    return claims


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="claims.json → 可勾选批量核验清单（CSV + Markdown）。")
    ap.add_argument("claims", help="claims JSON 路径（字符串数组或对象数组）")
    ap.add_argument("-o", "--csv", default="checklist.csv",
                    help="CSV 输出路径（默认 checklist.csv）")
    ap.add_argument("--md", default="checklist.md",
                    help="Markdown 输出路径（默认 checklist.md）")
    args = ap.parse_args(argv)

    claims = load_claims(args.claims)

    with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for c in claims:
            w.writerow(["[ ]", c["claim_id"], c["claim_text"],
                        "；".join(c["slots"]), "", "", "", ""])

    lines = [
        "# 批量引用核验清单",
        "",
        f"- 论断总数：{len(claims)}",
        f"- 判定取值：{VERDICTS}",
        "- 使用方法：逐条对照原文，勾选完成项并填写下表；"
        "主题相关≠支持，未报告≠反驳，冲突并列双方原话。",
        "",
        "## 勾选条目",
        "",
    ]
    for c in claims:
        lines.append(f"- [ ] **{c['claim_id']}**：{c['claim_text']}")
        lines.append(f"  - 待查槽位：{'；'.join(c['slots'])}")
    lines += [
        "",
        "## 核验记录表",
        "",
        "| claim_id | 论断原文 | 证据位置(页) | 判定 | 复核人 | 复核日期 |",
        "|---|---|---|---|---|---|",
    ]
    for c in claims:
        text = c["claim_text"].replace("|", "\\|")
        lines.append(f"| {c['claim_id']} | {text} |  |  |  |  |")
    lines.append("")
    with open(args.md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[checklist] {len(claims)} 条论断 → {args.csv} + {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
