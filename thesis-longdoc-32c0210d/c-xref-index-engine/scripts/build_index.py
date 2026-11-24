#!/usr/bin/env python3
"""build_index.py — 扫描分章节 Markdown 工作稿，构建跨章节一致性注册表 index.json。

注册表内容（schema: xref-index/v1）：
  headings       章节内 # 标题及其编号
  floats         图/表 题注（图 2-1 / 表2-1 / Figure 2-1 / Fig. 2-1 / Table 2-1，容忍全角空格与连字符变体）
  float_refs     正文对 图x-y / 表x-y 的引用点
  citations      [n] 引用点 vs “参考文献/References”小节的条目编号
  abbreviations  “全称（ABBR）”首次定义点及后续使用点
  term_forms     --terms 指定术语各变体的全部出现位置（参考文献条目行除外）

用法：
  python3 build_index.py --chapters DIR --out index.json \
      [--terms "规范写法|变体1;术语B|变体B1"] [--note TEXT]

仅使用 python3 标准库。所有位置均为相对文件名 + 1 起始行号，输出确定性。
"""
import argparse
import json
import os
import re
import sys

SCHEMA = "xref-index/v1"

# 全角数字/括号 → 半角；各类连字符 → '-'
_TRANS = str.maketrans("０１２３４５６７８９（）", "0123456789()")
_HYPHENS = "‐‑‒–—−"


def normalize(s):
    s = s.translate(_TRANS)
    for h in _HYPHENS:
        s = s.replace(h, "-")
    return s


NUM_RE = r"\d+(?:[-.]\d+)+"
FLOAT_RE = re.compile(r"(?<!意)(图|表|Figure|Fig\.?|Table)[\s\u3000]*(" + NUM_RE + r")")
HEADING_RE = re.compile(r"^(#{1,6})[\s\u3000]+(.*?)[\s\u3000#]*$")
BIB_RE = re.compile(r"^(参考文献|references|bibliography)\s*$", re.IGNORECASE)
CIT_RE = re.compile(r"\[(\d+(?:\s*[-,，]\s*\d+)*)\]")
ENTRY_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.、)])[\s\u3000]+\S")
ABBR_DEF_RE = re.compile(r"([^，。；、：:,()（）\s]{2,40}?)[（(]([A-Z][A-Z0-9]{1,11})[）)]")
HEAD_NUM_RE = re.compile(r"^第?(\d+(?:\.\d+)*)(?:[章\s\u3000.、]|$)")
LEAD_MD_RE = re.compile(r"^[\s\u3000>`*_~]+")

_KIND = {"图": "figure", "figure": "figure", "fig": "figure", "fig.": "figure",
         "表": "table", "table": "table"}


def kind_of(token):
    return _KIND[token.lower()]


def canon_number(n):
    return "-".join(re.split(r"[-.]+", normalize(n)))


def heading_number(text):
    m = HEAD_NUM_RE.match(text)
    return m.group(1) if m else None


def expand_citation(spec):
    """'1-3' -> [1,2,3]; '1,3' -> [1,3]"""
    out = []
    for part in re.split(r"[,，]", spec):
        part = part.strip()
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(range(a, b + 1) if a <= b else [a])
        elif part.isdigit():
            out.append(int(part))
    return out


def parse_terms(spec):
    """"规范|变体1;术语B|变体B1" -> [{'canonical':..., 'variants':[...]}]"""
    groups = []
    if not spec:
        return groups
    for g in spec.split(";"):
        variants = [v.strip() for v in g.split("|") if v.strip()]
        if variants:
            groups.append({"canonical": variants[0], "variants": variants})
    return groups


def scan_file(path, rel):
    with open(path, encoding="utf-8") as fh:
        raw_lines = fh.read().splitlines()
    res = {"headings": [], "floats": [], "float_refs": [], "citations": [],
           "entries": [], "abbr_defs": [], "body_lines": [], "bib_found": False}
    in_bib = False
    bib_level = 0
    for i, raw in enumerate(raw_lines, 1):
        line = normalize(raw)
        hm = HEADING_RE.match(line.strip())
        if hm:
            level = len(hm.group(1))
            text = hm.group(2).strip()
            if BIB_RE.match(text):
                in_bib, bib_level = True, level
                res["bib_found"] = True
            elif in_bib and level <= bib_level:
                in_bib = False
            res["headings"].append({"file": rel, "line": i, "level": level,
                                    "number": heading_number(text), "text": text})
            continue
        if in_bib:
            em = ENTRY_RE.match(line)
            if em:
                num = int(em.group(1) or em.group(2))
                res["entries"].append({"file": rel, "line": i, "number": num,
                                       "text": line.strip()[:160]})
            continue
        res["body_lines"].append((i, line))
        stripped = LEAD_MD_RE.sub("", line)
        cm = FLOAT_RE.match(stripped)
        if cm:
            res["floats"].append({"file": rel, "line": i, "kind": kind_of(cm.group(1)),
                                  "number": canon_number(cm.group(2)),
                                  "caption": stripped.strip()[:160]})
        else:
            for rm in FLOAT_RE.finditer(line):
                res["float_refs"].append({"file": rel, "line": i, "kind": kind_of(rm.group(1)),
                                          "number": canon_number(rm.group(2)),
                                          "context": line.strip()[:160]})
        for cit in CIT_RE.finditer(line):
            nums = expand_citation(cit.group(1))
            if nums:
                res["citations"].append({"file": rel, "line": i, "numbers": nums,
                                         "context": line.strip()[:160]})
        for am in ABBR_DEF_RE.finditer(line):
            res["abbr_defs"].append({"file": rel, "line": i,
                                     "full": am.group(1).strip(), "abbr": am.group(2)})
    return res


def find_occurrences(line, needle):
    start = 0
    while True:
        j = line.find(needle, start)
        if j < 0:
            return
        yield j + 1
        start = j + max(1, len(needle))


def main():
    ap = argparse.ArgumentParser(description="构建跨章节一致性注册表 index.json")
    ap.add_argument("--chapters", required=True, help="章节目录（递归扫描 .md/.markdown/.txt）")
    ap.add_argument("--out", required=True, help="输出 index.json 路径")
    ap.add_argument("--terms", default="", help="术语组：'规范|变体1;术语B|变体B1'")
    ap.add_argument("--note", default="", help="写入索引并随报告传播的备注（如合成示例标注）")
    args = ap.parse_args()

    if not os.path.isdir(args.chapters):
        print("ERROR: chapters dir not found: %s" % args.chapters, file=sys.stderr)
        return 2

    files = []
    for root, dirs, names in os.walk(args.chapters):
        dirs.sort()
        for n in sorted(names):
            if n.lower().endswith((".md", ".markdown", ".txt")):
                files.append(os.path.relpath(os.path.join(root, n), args.chapters))
    if not files:
        print("ERROR: no chapter files found under %s" % args.chapters, file=sys.stderr)
        return 2

    term_groups = parse_terms(args.terms)
    idx = {"schema": SCHEMA, "chapters_dir": os.path.basename(os.path.abspath(args.chapters)),
           "files": files, "term_groups": term_groups,
           "headings": [], "floats": [], "float_refs": [],
           "citations": {"bibliography_found": False, "bibliography_files": [],
                         "references": [], "entries": []},
           "abbreviations": {"definitions": [], "uses": []},
           "term_forms": {}, "counts": {}}
    if args.note:
        idx["note"] = args.note

    corpus_body = []  # (file, line_no, normalized_line)，不含标题与参考文献条目行
    scanned = {}
    for rel in files:
        r = scan_file(os.path.join(args.chapters, rel), rel)
        scanned[rel] = r
        idx["headings"].extend(r["headings"])
        idx["floats"].extend(r["floats"])
        idx["float_refs"].extend(r["float_refs"])
        idx["citations"]["references"].extend(r["citations"])
        idx["citations"]["entries"].extend(r["entries"])
        idx["abbreviations"]["definitions"].extend(r["abbr_defs"])
        if r["bib_found"]:
            idx["citations"]["bibliography_files"].append(rel)
        corpus_body.extend((rel, i, l) for (i, l) in r["body_lines"])
    idx["citations"]["bibliography_found"] = bool(idx["citations"]["bibliography_files"])

    # 缩略语使用点（全语料第二遍；定义点所在行标记 is_definition_site）
    defs = idx["abbreviations"]["definitions"]
    def_sites = {}
    for d in defs:
        def_sites.setdefault(d["abbr"], set()).add((d["file"], d["line"]))
    for ab in sorted(def_sites):
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(ab) + r"(?![A-Za-z0-9])")
        for (rel, i, line) in corpus_body:
            for m in pat.finditer(line):
                idx["abbreviations"]["uses"].append(
                    {"abbr": ab, "file": rel, "line": i, "column": m.start() + 1,
                     "is_definition_site": (rel, i) in def_sites[ab]})

    # 术语变体出现位置
    for g in term_groups:
        for v in g["variants"]:
            occ = idx["term_forms"].setdefault(v, [])
            for (rel, i, line) in corpus_body:
                for col in find_occurrences(line, v):
                    occ.append({"file": rel, "line": i, "column": col,
                                "context": line.strip()[:160]})

    idx["counts"] = {"files": len(files), "headings": len(idx["headings"]),
                     "floats": len(idx["floats"]), "float_refs": len(idx["float_refs"]),
                     "citation_points": len(idx["citations"]["references"]),
                     "reference_entries": len(idx["citations"]["entries"]),
                     "abbrev_definitions": len(defs),
                     "term_variants": len(idx["term_forms"])}

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("index written: %s (%s)" % (args.out, json.dumps(idx["counts"], ensure_ascii=False)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
