#!/usr/bin/env python3
"""extract_facts.py — 从分章节 Markdown 工作稿中挖掘事实锚点，产出 facts.json。

事实类型：
  number_with_unit : 带单位数字（2.4 V、85%、1.2 mS/cm、60 °C ...）
  term_definition  : 术语/缩写首次定义，"全称（ABBR）" 模式
  citation         : [n] 数字引文
  figure_ref       : 图/表/Fig./Table 编号引用

每条事实：{id, type, value, context, file, line}
确定性：文件按路径排序、fact id 顺序编号，无时间戳、无绝对路径（file 为
相对 --chapters 的路径）。

用法：
  python3 extract_facts.py --chapters <章节目录> --out <facts.json>
"""
import argparse
import json
import os
import re
import sys

NUM = r"\d+(?:\.\d+)?"
# 长单位在前，避免 "mS/cm" 被 "cm" 截断、"mV" 被 "V" 截断
UNITS = [
    "mS/cm", "mAh/g", "Wh/kg", "mA/g", "S/cm",
    "GPa", "MPa", "kPa", "wt%", "vol%",
    "nm", "µm", "um", "mm", "cm",
    "mV", "mA", "°C", "mol/L", "Ω", "V", "K", "%", "h",
]
UNIT_RE = "|".join(re.escape(u) for u in UNITS)
RE_NUM_UNIT = re.compile(
    r"(?<![\w.])(%s(?:\s*[~\-–]\s*%s)?)\s*(%s)(?![\w/])" % (NUM, NUM, UNIT_RE)
)
RE_TERM_DEF = re.compile(
    r"([A-Za-z][A-Za-z0-9\- ]{1,40}|[一-鿿][一-鿿A-Za-z]{0,19})"
    r"[（(]([A-Z][A-Za-z0-9]{1,9})[）)]"
)
RE_CITATION = re.compile(r"\[(\d{1,3})\]")
RE_FIGREF = re.compile(r"(图|表|Fig\.?|Figure|Table)\s*(\d+(?:[.\-]\d+)?)")
RE_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
RE_REF_SECTION = re.compile(r"参考文献|references|bibliography", re.IGNORECASE)
RE_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+")


def iter_md_files(chapters_dir):
    paths = []
    for root, dirs, files in os.walk(chapters_dir):
        dirs.sort()
        for name in sorted(files):
            if name.lower().endswith(".md"):
                paths.append(os.path.join(root, name))
    return sorted(paths)


def sentence_of(line, start):
    """返回 line 中包含字符位置 start 的句子（去首尾空白）。"""
    pos = 0
    for seg in RE_SENT_SPLIT.split(line):
        if seg is None:
            continue
        seg_start = line.find(seg, pos)
        seg_end = seg_start + len(seg)
        pos = seg_end
        if seg_start <= start < seg_end:
            return seg.strip()
    return line.strip()


def extract_file(path, rel):
    facts = []
    in_code = False
    in_ref_section = False
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m_head = RE_HEADING.match(line)
        if m_head:
            in_ref_section = bool(RE_REF_SECTION.search(m_head.group(1)))
            continue
        if in_ref_section or not stripped:
            continue

        for m in RE_NUM_UNIT.finditer(line):
            value = m.group(0).strip()  # 保留原文表面形式（如 85%、60 °C）
            facts.append({
                "type": "number_with_unit",
                "value": value,
                "context": sentence_of(line, m.start()),
                "file": rel,
                "line": lineno,
            })
        for m in RE_TERM_DEF.finditer(line):
            facts.append({
                "type": "term_definition",
                "value": m.group(0).strip(),
                "context": sentence_of(line, m.start()),
                "file": rel,
                "line": lineno,
            })
        for m in RE_CITATION.finditer(line):
            facts.append({
                "type": "citation",
                "value": "[%s]" % m.group(1),
                "context": sentence_of(line, m.start()),
                "file": rel,
                "line": lineno,
            })
        for m in RE_FIGREF.finditer(line):
            facts.append({
                "type": "figure_ref",
                "value": m.group(0).strip(),
                "context": sentence_of(line, m.start()),
                "file": rel,
                "line": lineno,
            })
    return facts


def main():
    ap = argparse.ArgumentParser(description="挖掘章节事实锚点 → facts.json")
    ap.add_argument("--chapters", required=True, help="章节 Markdown 目录")
    ap.add_argument("--out", required=True, help="输出 facts.json 路径")
    args = ap.parse_args()

    if not os.path.isdir(args.chapters):
        print("ERROR: chapters dir not found: %s" % args.chapters, file=sys.stderr)
        return 2

    all_facts = []
    for path in iter_md_files(args.chapters):
        rel = os.path.relpath(path, args.chapters)
        all_facts.extend(extract_file(path, rel))

    # 术语定义只保留每个缩写的首次定义
    seen_abbr = set()
    facts = []
    for f in all_facts:
        if f["type"] == "term_definition":
            m = RE_TERM_DEF.search(f["value"])
            key = m.group(2) if m else f["value"]
            if key in seen_abbr:
                continue
            seen_abbr.add(key)
        facts.append(f)

    for i, f in enumerate(facts, start=1):
        f_with_id = {"id": "F%04d" % i}
        f_with_id.update(f)
        facts[i - 1] = f_with_id

    counts = {}
    for f in facts:
        counts[f["type"]] = counts.get(f["type"], 0) + 1

    payload = {
        "schema": "facts/v1",
        "chapters_dir": args.chapters,
        "counts": counts,
        "total": len(facts),
        "facts": facts,
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")
    print("extract_facts: %d facts (%s) -> %s"
          % (len(facts), counts, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
