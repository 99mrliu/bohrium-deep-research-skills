#!/usr/bin/env python3
"""fact_ledger.py — 编译事实台账 facts.jsonl。

扫描 materials/ 目录中的文本材料（markdown/txt/yaml/csv 等），排除 case.json 形状的
JSON（含 case_id / output_contract / result 字段的文件不入台账），抽取四类事实：

  number   数字（含单位），如 92–95、88.2%、1.5×10^-3、3.7 V、mAh g-1 前的数字
  term     术语/专有名词（首字母大写词组、缩写、中文术语标记）
  citation 引用标记，如 [1]、[12,13]、(Author et al., 2020)
  claim    关键论断（含"表明/显示/证明/优于/demonstrate/show"等触发词的句子）

每行 JSON：{id, kind, surface, unit, source:{file, heading, paragraph_index, quote}}
quote 为逐字截取，surface 必须能在 quote 中逐字找到（数字按原文形态）。

数字识别注意：92–95 按一个区间整体收录并同时收录端点；88.2% 带 % 为单位；
1.5×10^-3 整体为一个数；mAh g-1 中 -1 是单位的一部分，不是数字。
仅 Python 3 标准库。
"""
import argparse
import json
import os
import re
import sys

TEXT_EXTS = {".md", ".txt", ".markdown", ".rst", ".tex", ".csv", ".tsv",
             ".yaml", ".yml", ".json", ".bib"}
CASE_JSON_KEYS = {"case_id", "output_contract", "result"}

# ---- 数字形态 ----
NUM_CORE = r"\d+(?:\.\d+)?"
NUM_PATTERNS = [
    # 科学计数法：1.5×10^-3 / 1.5e-3 / 1.5×10−3（整体一个数）
    re.compile(r"%s(?:×10\^?[−\-]?\d+|e[+\-]?\d+)" % NUM_CORE),
    # 区间：92–95 / 92-95 / 92~95（区间内部不含小数点，避免吞掉 88.2-3.1 这类）
    re.compile(r"\d+(?:–|—|~|(?<=\d)-(?=\d))\d+"),
    # 百分数：88.2%
    re.compile(r"%s%%" % NUM_CORE),
    # 普通数字（整数/小数），不匹配单位里的 -1（前面带 ^ 或字母上标语境）
    re.compile(r"(?<![\w\-\.^])%s(?![\w.])" % NUM_CORE),
]

UNIT_PATTERN = re.compile(
    r"(?:mAh\s*g[−\-]?1|g\s*cm[−\-]?3|mS\s*cm[−\-]?1|kg\s*m[−\-]?3|"
    r"mol\s*L[−\-]?1|wt%|at%|vol%|nm|µm|um|mm|cm|mA|mV|mW|kWh|Wh|"
    r"MPa|GPa|kPa|Pa|eV|keV|V|K|°C|℃|wt|h|min|s|mL|L|g|mg|kg|%|"
    r"cycles?|周|次|小时|天|年|篇|个|条|倍|款|种|页)\b", re.UNICODE)

CITATION_PATTERNS = [
    re.compile(r"\[\d+(?:\s*[,\-–]\s*\d+)*\]"),                 # [1] [12,13] [3-5]
    re.compile(r"\([A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?,?\s*\d{4}[a-z]?\)"),  # (Author et al., 2020)
    re.compile(r"(?:doi|DOI)[:：]\s*10\.\d{4,9}/\S+"),          # doi:10.xxxx/...
]

TERM_PATTERN = re.compile(
    r"(?:[A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*){0,3})|"   # 英文大写词组
    r"\b[A-Z]{2,}(?:-[A-Z0-9]+)*\b")                             # 缩写 LLZO, SEM

CLAIM_TRIGGERS = re.compile(
    r"表明|显示|证明|证实|优于|显著|首次|最高|最低|提升|降低|改善了?|归因于|"
    r"demonstrat\w*|show\w*|prov\w*|outperform\w*|achiev\w*|attribut\w*",
    re.IGNORECASE)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def looks_like_case_json(path):
    """排除 case.json 形状的 JSON 文件。"""
    if not path.lower().endswith(".json"):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        return False
    if isinstance(obj, dict) and CASE_JSON_KEYS & set(obj.keys()):
        return True
    return False


def iter_material_files(materials_dir):
    for root, dirs, files in os.walk(materials_dir):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(root, name)
            ext = os.path.splitext(name)[1].lower()
            if ext not in TEXT_EXTS:
                continue  # 二进制/PDF 等不处理（可选依赖缺失时降级，由调用方记录）
            if looks_like_case_json(path):
                continue
            yield path


def split_paragraphs(text):
    """按空行分段；返回 [(paragraph_index, text)]，index 从 1 开始。"""
    paras = re.split(r"\n\s*\n", text)
    out = []
    for i, p in enumerate(paras, 1):
        p = p.strip()
        if p:
            out.append((i, p))
    return out


def heading_of(para_text):
    m = HEADING_RE.match(para_text)
    return m.group(2).strip() if m else None


def extract_numbers(para):
    """返回 [(surface, unit, span)]。区间整体 + 端点；科学计数法整体。"""
    found = []
    occupied = []  # 已占用的 span，避免重复
    for pat in NUM_PATTERNS:
        for m in pat.finditer(para):
            s, e = m.span()
            if any(not (e <= a or s >= b) for a, b in occupied):
                continue
            surface = m.group(0)
            # mAh g-1 之类：检查紧邻后缀单位
            tail = para[e:e + 12]
            um = UNIT_PATTERN.match(tail.lstrip(" ") if tail.startswith(" ") else tail)
            unit = um.group(0) if um else None
            # 百分比形态已自带 %
            if surface.endswith("%"):
                unit = "%"
            found.append((surface, unit, (s, e)))
            occupied.append((s, e))
    # 区间的端点也单独入账（便于 ground_guard 命中单个端点）
    extra = []
    for surface, unit, span in found:
        mm = re.match(r"^(\d+)(?:–|—|~|-)(\d+)$", surface)
        if mm:
            for ep in mm.groups():
                extra.append((ep, unit, span))
    return found + extra


def quote_around(para, span, width=80):
    s, e = span
    a = max(0, s - width)
    b = min(len(para), e + width)
    q = para[a:b].strip()
    return q


def process_file(path, rel, facts, seen):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (UnicodeDecodeError, OSError) as exc:
        print("WARN skip %s: %s" % (rel, exc), file=sys.stderr)
        return
    current_heading = None
    for pidx, para in split_paragraphs(text):
        h = heading_of(para)
        if h is not None:
            current_heading = h
            continue
        src = {"file": rel, "heading": current_heading,
               "paragraph_index": pidx, "quote": None}

        def add(kind, surface, unit, span):
            key = (kind, surface, rel, pidx)
            if key in seen:
                return
            seen.add(key)
            entry = {"kind": kind, "surface": surface, "unit": unit,
                     "source": dict(src, quote=quote_around(para, span))}
            facts.append(entry)

        for surface, unit, span in extract_numbers(para):
            add("number", surface, unit, span)
        for pat in CITATION_PATTERNS:
            for m in pat.finditer(para):
                add("citation", m.group(0), None, m.span())
        for m in TERM_PATTERN.finditer(para):
            tok = m.group(0).strip()
            if len(tok) < 2 or tok.lower() in {"the", "and", "for", "with"}:
                continue
            add("term", tok, None, m.span())
        if CLAIM_TRIGGERS.search(para):
            # 论断以整段为 surface（截断到 200 字符），锚点是逐字段落
            surface = para if len(para) <= 200 else para[:200]
            add("claim", surface, None, (0, min(len(para), 200)))


def main():
    ap = argparse.ArgumentParser(description="编译事实台账 facts.jsonl")
    ap.add_argument("--materials", required=True, help="materials 目录")
    ap.add_argument("--out", required=True, help="输出 facts.jsonl 路径")
    args = ap.parse_args()

    if not os.path.isdir(args.materials):
        print("ERROR materials dir not found: %s" % args.materials, file=sys.stderr)
        sys.exit(2)

    facts, seen = [], set()
    n_files = 0
    for path in iter_material_files(args.materials):
        rel = os.path.relpath(path, args.materials)
        process_file(path, rel, facts, seen)
        n_files += 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for i, entry in enumerate(facts, 1):
            entry2 = {"id": "F%04d" % i}
            entry2.update(entry)
            f.write(json.dumps(entry2, ensure_ascii=False) + "\n")

    print("fact_ledger: %d files, %d facts -> %s" % (n_files, len(facts), args.out))


if __name__ == "__main__":
    main()
