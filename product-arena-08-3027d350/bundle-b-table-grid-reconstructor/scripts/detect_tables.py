#!/usr/bin/env python3
"""detect_tables.py — 表格区域检测层（表格结构重建技能 B 的第 2 步）。

在保版式页面文本中定位表格，支持两类证据：
    A. 空白对齐表：≥3 个连续行，每行含 ≥2 处宽度 ≥2 的内部空白，
       且空白列位与连续区共识列位重合度 ≥50%；
    B. 制表线表（ASCII 线框）：含 ─ - + | 等线框字符的行簇。
题注锚定：以 (Table|TABLE|Tab.|表)\\s*\\S*\\d 行作为表格身份与边界证据；
检测到区域但与题注距离 >3 行时在 uncertainty 中说明。

输出 tables_index.json：
    [{table_id, page, caption, region:[start,end], kind, confidence}]
行号为页内 0 基。退出码 0=检测到；2=未检测到（如实报告，不伪造表格）。
"""
import argparse
import glob
import json
import os
import re
import sys

CAPTION_RE = re.compile(r"^\s*(table|tab\.?|表)\s*[sS]?\d+", re.I)
RULED_RE = re.compile(r"^[\s+\-|=_]{6,}$")
RULED_BORDER = re.compile(r"[+|]")


def gap_positions(line):
    """返回行内所有 ≥2 空白区间的中心列位集合（环视匹配，允许空隙相邻）。"""
    pos = set()
    for m in re.finditer(r"(?<=\S)(  +)(?=\S)", line):
        start = m.start(1)
        pos.add(start + len(m.group(1)) // 2)
    return pos


def consensus_columns(rows):
    """连续区的共识分列位：先把各行的空白中心按 ±3 列聚类，
    再保留覆盖 ≥60% 行的簇（以簇心为分列位）。"""
    from collections import Counter
    c = Counter()
    for r in rows:
        for p in gap_positions(r):
            c[p] += 1
    thresh = max(2, int(0.6 * len(rows) + 0.5))
    clusters = []  # [ [positions...], total_count ]
    for p in sorted(c):
        if clusters and p - clusters[-1][0][-1] <= 3:
            clusters[-1][0].append(p)
            clusters[-1][1] += c[p]
        else:
            clusters.append([[p], c[p]])
    out = []
    for positions, total in clusters:
        if total >= thresh:
            out.append(round(sum(p * c[p] for p in positions)
                             / sum(c[p] for p in positions)))
    return out


def _is_continuation(line):
    """折行续接行：非空、缩进 ≥6 列、内部不足 2 处宽空白（如折行的单元格）。"""
    stripped = line.strip()
    if not stripped or CAPTION_RE.match(line):
        return False
    indent = len(line) - len(line.lstrip())
    return indent >= 6 and len(gap_positions(line)) < 2


def _qualifies(line):
    return len(gap_positions(line)) >= 2 or _is_continuation(line)


def detect_whitespace_tables(lines):
    """扫描连续区：成员为 ≥2 宽空白行或折行续接行；行间允许 ≤2 个
    空行（pdftotext -layout 在行距大时会插入空行），空行不计入核心。"""
    regions = []
    i, n = 0, len(lines)
    while i < n:
        if len(gap_positions(lines[i])) >= 2 and lines[i].strip():
            j = i
            run, core, blanks = [], [], 0
            while j < n:
                line = lines[j]
                if not line.strip():
                    # 向后看：下一个非空行仍是成员则容忍该空行
                    k = j + 1
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and _qualifies(lines[k]) \
                            and k - j <= 2 and core:
                        blanks += 1
                        j = k
                        continue
                    break
                if _qualifies(line):
                    run.append(j)
                    if len(gap_positions(line)) >= 2:
                        core.append(j)
                    j += 1
                else:
                    break
            if len(core) >= 3:
                cols = consensus_columns([lines[k] for k in core])
                if len(cols) >= 2:
                    regions.append({"region": [run[0], run[-1]],
                                    "kind": "whitespace",
                                    "n_rows": len(run),
                                    "blank_lines_inside": blanks,
                                    "columns": cols})
            i = max(j, i + 1)
        else:
            i += 1
    return regions


def detect_ruled_tables(lines):
    regions = []
    i, n = 0, len(lines)
    while i < n:
        if RULED_RE.match(lines[i]) and RULED_BORDER.search(lines[i]):
            j = i
            while j < n and (RULED_RE.match(lines[j])
                             or RULED_BORDER.search(lines[j])) \
                    and lines[j].strip():
                j += 1
            if j - i >= 3:
                regions.append({"region": [i, j - 1], "kind": "ruled",
                                "n_rows": j - i, "columns": []})
            i = j
        else:
            i += 1
    return regions


def bind_caption(lines, region):
    """题注绑定：区域上下 8 行内找最近的 Table/表 行；距离按**非空行**
    计（layout 文本常在题注与表格间插空行），>3 个非空行标疑。"""
    s, e = region

    def text_dist(k):
        if k > e:
            return sum(1 for t in lines[e + 1:k] if t.strip())
        if k < s:
            return sum(1 for t in lines[k + 1:s] if t.strip())
        return 0

    best = None
    for k in range(max(0, s - 8), min(len(lines), e + 8)):
        if CAPTION_RE.match(lines[k]):
            dist = text_dist(k)
            if best is None or dist < best[1]:
                best = (k, dist)
    if best is None:
        return None, None, None
    k, dist = best
    text = lines[k].strip()
    m = re.match(r"^\s*((?:table|tab\.?|表)\s*[sS]?\d+)", text, re.I)
    return text, m.group(1) if m else None, dist


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", required=True, help="pages/ 目录")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    tables, notes = [], []
    for path in sorted(glob.glob(os.path.join(args.pages, "page*.txt"))):
        pno = int(re.search(r"(\d+)", os.path.basename(path)).group(1))
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        ruled = detect_ruled_tables(lines)
        ws = detect_whitespace_tables(lines)
        # 线框表内部的空格对齐行会被空白检测重复命中，按重叠剔除
        ws = [w for w in ws if not any(
            not (w["region"][1] < r["region"][0]
                 or w["region"][0] > r["region"][1]) for r in ruled)]
        for reg in ws + ruled:
            caption, label, dist = bind_caption(lines, reg["region"])
            conf = 0.6
            if caption:
                conf += 0.2 if dist <= 3 else 0.0
            if reg["kind"] == "ruled":
                conf += 0.15
            tid = label or f"page{pno}-r{reg['region'][0]}"
            entry = {"table_id": tid.replace(" ", "_"), "page": pno,
                     "caption": caption, "region": reg["region"],
                     "kind": reg["kind"], "columns": reg.get("columns", []),
                     "n_source_lines": reg["n_rows"],
                     "confidence": round(min(conf, 0.95), 2)}
            if caption is None:
                entry["unresolved"] = "未找到邻近题注，表格身份按区域编号"
                notes.append(f"page {pno} 区域 {reg['region']} 无题注")
            elif dist and dist > 3:
                entry["unresolved"] = f"题注距离区域 {dist} 行，绑定可能错误"
                notes.append(f"page {pno} {tid} 题注距离偏远")
            tables.append(entry)

    out = os.path.join(args.out, "tables_index.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(tables, f, ensure_ascii=False, indent=2)
    report = {"status": "ok" if tables else "partial",
              "tables": len(tables), "index": out}
    if notes:
        report["uncertainty"] = notes
    if not tables:
        report["note"] = "未检测到表格区域；如实报告，未伪造"
    print(json.dumps(report, ensure_ascii=False))
    return 0 if tables else 2


if __name__ == "__main__":
    sys.exit(main())
