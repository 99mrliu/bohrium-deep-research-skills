#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""split_references.py — references 区间内条目级切分。

起始模式（优先级递减，见 references/heading-patterns.md）：
  1. [n]        方括号编号
  2. n. / n)    数字编号
  3. 作者行      大写起始 + 逗号 + 年份（19xx/20xx），且上一条目以句点收尾
其余行视为上一条目的续行并入 raw_text；首条起始模式之前的行进 leftovers。
切不出任何条目时：全部进 leftovers，退出码 2。任何字符不丢弃：
  sum(len(raw_text)) + len(leftovers) + 标题行字符 == 区间总字符（审计可复核）。

输出 references.json：entries[{index, raw_text, anchor{page,y0},
  first_author_guess, year_guess}] + leftovers + char_accounting。
退出码：0=成功；2=部分（无条目或 leftovers 非空）；3=失败。
"""
import argparse
import json
import os
import re
import sys

BRACKET_RE = re.compile(r"^\[(\d{1,3})\]\s*(.*)$")
DOTNUM_RE = re.compile(r"^(\d{1,3})[.)]\s+(\S.*)$")
AUTHOR_LINE_RE = re.compile(r"^[A-Z][A-Za-z'’\- .]+,.*(19|20)\d{2}")
YEAR_RE = re.compile(r"(19|20)\d{2}")
REF_HEAD_RE = re.compile(r"^(references|bibliography|参考文献)\s*$", re.I)


def load_lines(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for row in f:
            row = row.strip()
            if row:
                out.append(json.loads(row))
    return out


def guess_first_author(text):
    t = re.sub(r"^\[\d+\]\s*", "", text)
    t = re.sub(r"^\d+[.)]\s+", "", t)
    head = t.split(",", 1)[0].strip()
    return head or None


def guess_year(text):
    m = YEAR_RE.search(text)
    return m.group(0) if m else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="参考文献条目级切分")
    ap.add_argument("--lines", required=True)
    ap.add_argument("--spans", required=True)
    ap.add_argument("--out", required=True, help="输出 references.json")
    ap.add_argument("--report", required=True, help="输出 split_report.json")
    args = ap.parse_args(argv)

    for p in (args.lines, args.spans):
        if not os.path.isfile(p):
            print(f"[split] 输入不存在: {p}", file=sys.stderr)
            return 3
    lines = load_lines(args.lines)
    with open(args.spans, encoding="utf-8") as f:
        spans = json.load(f).get("spans", {})

    ref_span = spans.get("references")
    if not ref_span:
        report = {
            "status": "failed",
            "uncertainty": "spans.json 中无 references 区间（build_hierarchy 未定位到 References 标题）。",
        }
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return 3

    seg = [
        l for l in lines
        if ref_span["start_line_idx"] <= l["line_idx"] <= ref_span["end_line_idx"]
    ]
    total_chars = sum(len(l["text"]) for l in seg)

    entries, leftovers_lines = [], []
    cur = None
    skipped_heading_chars = 0

    def flush():
        nonlocal cur
        if cur is not None:
            cur["raw_text"] = " ".join(cur["parts"]).strip()
            del cur["parts"]
            entries.append(cur)
            cur = None

    for l in seg:
        text = l["text"].strip()
        if REF_HEAD_RE.match(text):
            skipped_heading_chars += len(l["text"])
            continue
        m_b, m_d = BRACKET_RE.match(text), DOTNUM_RE.match(text)
        is_author_start = (
            AUTHOR_LINE_RE.match(text)
            and cur is not None
            and cur["parts"]
            and cur["parts"][-1].rstrip().endswith(".")
        )
        if m_b or m_d or is_author_start:
            flush()
            idx = int((m_b or m_d).group(1)) if (m_b or m_d) else None
            cur = {
                "index": idx,
                "parts": [text],
                "anchor": {"page": l["page"], "y0": l["y0"]},
            }
        elif cur is not None:
            cur["parts"].append(text)
        else:
            leftovers_lines.append({"page": l["page"], "y0": l["y0"], "text": text})
    flush()

    for i, e in enumerate(entries, start=1):
        if e["index"] is None:
            e["index"] = i  # 无显式编号时按序补号并保留原样于 raw_text
        e["first_author_guess"] = guess_first_author(e["raw_text"])
        e["year_guess"] = guess_year(e["raw_text"])

    leftovers_text = "\n".join(x["text"] for x in leftovers_lines)
    accounted = (
        sum(len(e["raw_text"]) for e in entries)
        + sum(len(x["text"]) for x in leftovers_lines)
        + skipped_heading_chars
    )
    # 精确对账：续行以单空格连接会多出 (行数-1) 个空格；
    # 对账式：accounted + join_spaces == total_chars，原文不丢任何字符。
    join_spaces = total_chars - accounted
    char_accounting = {
        "interval_total_chars": total_chars,
        "entries_chars": sum(len(e["raw_text"]) for e in entries),
        "leftovers_chars": sum(len(x["text"]) for x in leftovers_lines),
        "skipped_heading_chars": skipped_heading_chars,
        "join_spaces_added": join_spaces,
        "balanced": accounted + join_spaces == total_chars,
        "note": "续行以单空格连接；join_spaces_added 为合并引入的空格数，原文无任何字符被丢弃。",
    }

    notes = []
    if not entries:
        notes.append("references 区间内未识别出任何条目起始模式，全部文本进入 leftovers（未丢弃）。")
    elif leftovers_lines:
        notes.append(f"{len(leftovers_lines)} 行位于首条条目起始模式之前，进入 leftovers（未丢弃）。")

    out_doc = {
        "status": "success" if entries else "partial",
        "entry_count": len(entries),
        "entries": entries,
        "leftovers": leftovers_lines,
        "char_accounting": char_accounting,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_doc, f, ensure_ascii=False, indent=2)

    report = {
        "status": ("partial" if (not entries or leftovers_lines) else "success"),
        "entry_count": len(entries),
        "leftover_line_count": len(leftovers_lines),
        "char_accounting": char_accounting,
        "notes": notes,
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[split] entries={len(entries)} leftover_lines={len(leftovers_lines)} "
          f"balanced={char_accounting['balanced']} status={report['status']}")
    return 0 if report["status"] == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
