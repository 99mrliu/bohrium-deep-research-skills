#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citeaudit.py — LaTeX 引用图谱静态审计（不编译，仅标准库）。

从全部 .tex 抽取 \\cite/\\ref/\\eqref/\\label（含多键 \\cite{a,b}、可选参数），
从 .bib 抽取条目键与字段，构建引用图谱并诊断：
  - 未定义引用（给出正文 file:line 与最接近的 bib 键候选，标注弱匹配）
  - 未定义 / 重复 \\label
  - 未被引用的 bib 条目
  - bib 字段缺失（按 entrytype 最小字段，规则说明见 references/bib-field-rules.md）
  - \\cite 顺序与重复（信息级）

红线：只报告建议，绝不自动改稿、绝不自动删 bib 条目。

用法：
  python3 citeaudit.py --project <工程目录> [--main main.tex] [--bib refs.bib ...]
                       --work <输出目录> [--banner "页眉标注文本"]
退出码：0 审计完成（问题写在报告里）；1 参数/运行错误。
"""
import argparse
import difflib
import json
import os
import re
import sys

# ---- 按 entrytype 的最小字段规则（与 references/bib-field-rules.md 对应）----
# required 中元素为字符串表示必需；为元组表示其中任意一个即可。
FIELD_RULES = {
    "article":       {"required": ["author", "title", "journal", "year"],
                      "recommended": ["volume", "number", "pages", "doi"]},
    "book":          {"required": [("author", "editor"), "title", "publisher", "year"],
                      "recommended": ["edition", "isbn", "doi"]},
    "booklet":       {"required": ["title"],
                      "recommended": ["author", "howpublished", "year"]},
    "inbook":        {"required": [("author", "editor"), "title", ("chapter", "pages"),
                                   "publisher", "year"],
                      "recommended": ["edition"]},
    "incollection":  {"required": ["author", "title", "booktitle", "publisher", "year"],
                      "recommended": ["editor", "pages", "doi"]},
    "inproceedings": {"required": ["author", "title", "booktitle", "year"],
                      "recommended": ["editor", "pages", "publisher", "doi"]},
    "conference":    {"required": ["author", "title", "booktitle", "year"],
                      "recommended": ["editor", "pages", "publisher", "doi"]},
    "manual":        {"required": ["title"],
                      "recommended": ["author", "organization", "year"]},
    "mastersthesis": {"required": ["author", "title", "school", "year"],
                      "recommended": ["type", "address"]},
    "phdthesis":     {"required": ["author", "title", "school", "year"],
                      "recommended": ["type", "address"]},
    "misc":          {"required": [],
                      "recommended": ["author", "title", "year", "howpublished"]},
    "online":        {"required": ["title"], "recommended": ["author", "url", "urldate", "year"]},
    "proceedings":   {"required": ["title", "year"],
                      "recommended": ["editor", "publisher", "volume"]},
    "techreport":    {"required": ["author", "title", "institution", "year"],
                      "recommended": ["number", "type", "doi"]},
    "unpublished":   {"required": ["author", "title", "note"],
                      "recommended": ["year"]},
}

CITE_RE = re.compile(
    r"\\(cite\w*|parencite|textcite|autocite|footcite|nocite|no\w*cite)"
    r"\s*(?:\[[^\]]*\])?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
REF_RE = re.compile(r"\\(ref|eqref|pageref|autoref|nameref|vref|cref|Cref)\s*\{([^}]*)\}")
LABEL_RE = re.compile(r"\\label\s*\{([^}]*)\}")
INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]*)\}")
BIBLIO_RE = re.compile(r"\\bibliography\s*\{([^}]*)\}")
ADDBIB_RE = re.compile(r"\\addbibresource(?:\[[^\]]*\])?\s*\{([^}]*)\}")
BIBENTRY_RE = re.compile(r"@(\w+)\s*([({])")
FIELDNAME_RE = re.compile(r"\s*(\w+)\s*=\s*")

STRONG_MATCH = 0.8   # difflib 相似度 >= 此值视为强候选
WEAK_MATCH = 0.5     # [此值, STRONG_MATCH) 视为弱匹配，低于则不给候选


def strip_comment(line):
    """去掉未转义 % 之后的注释。"""
    out = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "%":
            # 数前面连续反斜杠个数，奇数表示被转义
            bs = 0
            j = i - 1
            while j >= 0 and line[j] == "\\":
                bs += 1
                j -= 1
            if bs % 2 == 0:
                break
        out.append(ch)
        i += 1
    return "".join(out)


def rel(path, root):
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def find_tex_files(project):
    texs = []
    for dirpath, dirnames, filenames in os.walk(project):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "_citebuild", "_run", "build", "__pycache__")]
        for f in filenames:
            if f.endswith(".tex"):
                texs.append(os.path.join(dirpath, f))
    return sorted(texs)


def order_tex_files(project, tex_files, main=None):
    """按 main → \\input/\\include 深度优先排序，未到达的按字典序附后。"""
    tex_set = {os.path.normpath(t) for t in tex_files}

    def resolve(name, base_dir):
        name = name.strip()
        cands = [name] if name.endswith(".tex") else [name + ".tex", name]
        for c in cands:
            for base in (base_dir, project):
                p = os.path.normpath(os.path.join(base, c))
                if p in tex_set:
                    return p
        return None

    if main is None:
        for t in tex_files:
            try:
                with open(t, encoding="utf-8", errors="replace") as fh:
                    if "\\documentclass" in fh.read():
                        main = t
                        break
            except OSError:
                pass
    order, seen = [], set()

    def visit(path):
        if path is None or path in seen or path not in tex_set:
            return
        seen.add(path)
        order.append(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = "\n".join(strip_comment(l) for l in fh)
        except OSError:
            return
        for m in INPUT_RE.finditer(text):
            visit(resolve(m.group(1), os.path.dirname(path)))

    visit(main)
    for t in tex_files:
        visit(t)
    return order


def parse_bib_file(path):
    """解析 .bib，返回 (entries, duplicate_keys)。entries: key -> dict。"""
    entries, duplicates = {}, []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return {}, [], [{"file": path, "error": str(exc)}]
    errors = []
    pos = 0
    while True:
        m = BIBENTRY_RE.search(text, pos)
        if not m:
            break
        etype = m.group(1).lower()
        line_no = text.count("\n", 0, m.start()) + 1
        if etype in ("string", "preamble", "comment"):
            pos = m.end()
            continue
        # 平衡扫描到条目结束（{ } 始终计数；( ) 条目额外计数）
        depth = 1
        i = m.end()
        paren = 1 if m.group(2) == "(" else 0
        while i < len(text) and depth + paren > 0:
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == "(" and m.group(2) == "(":
                paren += 1
            elif ch == ")" and m.group(2) == "(":
                paren -= 1
            i += 1
        body = text[m.end():i - 1]
        pos = i
        comma = body.find(",")
        if comma < 0:
            errors.append({"file": path, "line": line_no,
                           "error": "条目缺少键或字段"})
            continue
        key = body[:comma].strip()
        fields = {}
        fpos = comma + 1
        while fpos < len(body):
            fm = FIELDNAME_RE.match(body, fpos)
            if not fm:
                break
            fname = fm.group(1).lower()
            vpos = fm.end()
            value_parts = []
            # 值可用 # 拼接多段
            while vpos <= len(body):
                while vpos < len(body) and body[vpos] in " \t\n":
                    vpos += 1
                if vpos < len(body) and body[vpos] == "{":
                    d, j = 1, vpos + 1
                    while j < len(body) and d > 0:
                        if body[j] == "{":
                            d += 1
                        elif body[j] == "}":
                            d -= 1
                        j += 1
                    value_parts.append(body[vpos + 1:j - 1])
                    vpos = j
                elif vpos < len(body) and body[vpos] == '"':
                    d, j = 0, vpos + 1
                    buf = []
                    while j < len(body):
                        if body[j] == "{":
                            d += 1
                        elif body[j] == "}":
                            d -= 1
                        elif body[j] == '"' and d == 0:
                            break
                        buf.append(body[j])
                        j += 1
                    value_parts.append("".join(buf))
                    vpos = j + 1
                else:
                    j = vpos
                    while j < len(body) and body[j] not in ",\n":
                        j += 1
                    value_parts.append(body[vpos:j].strip())
                    vpos = j
                # 拼接符 #
                k = vpos
                while k < len(body) and body[k] in " \t\n":
                    k += 1
                if k < len(body) and body[k] == "#":
                    vpos = k + 1
                    continue
                vpos = k
                break
            fields[fname] = " ".join(p.split()) if False else " ".join(
                " ".join(p.split()) for p in value_parts)
            # 跳到下一个字段（逗号之后）
            while vpos < len(body) and body[vpos] != ",":
                vpos += 1
            fpos = vpos + 1
        if key in entries:
            duplicates.append({"key": key, "file": path, "line": line_no,
                               "first_line": entries[key]["line"]})
        else:
            entries[key] = {"key": key, "entrytype": etype,
                            "file": path, "line": line_no, "fields": fields}
    return entries, duplicates, errors


def missing_fields(entry):
    etype = entry["entrytype"]
    rules = FIELD_RULES.get(etype)
    if rules is None:
        return None, None  # 未知 entrytype，跳过
    have = set(entry["fields"])
    miss_req, miss_rec = [], []
    for item in rules["required"]:
        if isinstance(item, tuple):
            if not any(f in have for f in item):
                miss_req.append("/".join(item))
        elif item not in have:
            miss_req.append(item)
    for item in rules["recommended"]:
        if item not in have:
            miss_rec.append(item)
    return miss_req, miss_rec


def candidates(key, bib_keys):
    out = []
    for match in difflib.get_close_matches(key, list(bib_keys), n=3, cutoff=WEAK_MATCH):
        ratio = difflib.SequenceMatcher(None, key, match).ratio()
        out.append({"key": match, "similarity": round(ratio, 3),
                    "weak": ratio < STRONG_MATCH})
    return out


def audit(project, main=None, bib_args=None):
    project = os.path.abspath(project)
    tex_files = find_tex_files(project)
    ordered = order_tex_files(project, tex_files, main and os.path.abspath(
        os.path.join(project, main)))

    citations, references, labels = [], [], []
    bib_names = list(bib_args or [])
    nocite_all = False
    for path in ordered:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        rpath = rel(path, project)
        for ln, raw in enumerate(lines, 1):
            line = strip_comment(raw)
            for m in CITE_RE.finditer(line):
                cmd = m.group(1)
                keys = [k.strip() for k in m.group(2).split(",") if k.strip()]
                if cmd == "nocite" and keys == ["*"]:
                    nocite_all = True
                for k in keys:
                    citations.append({"key": k, "command": cmd,
                                      "file": rpath, "line": ln})
            for m in REF_RE.finditer(line):
                for k in (x.strip() for x in m.group(2).split(",") if x.strip()):
                    references.append({"key": k, "command": m.group(1),
                                       "file": rpath, "line": ln})
            for m in LABEL_RE.finditer(line):
                labels.append({"key": m.group(1).strip(),
                               "file": rpath, "line": ln})
            for m in BIBLIO_RE.finditer(line):
                bib_names.extend(b.strip() for b in m.group(1).split(",") if b.strip())
            for m in ADDBIB_RE.finditer(line):
                bib_names.append(m.group(1).strip())

    # 定位 .bib 文件
    bib_paths = []
    for name in bib_names:
        cands = [name] if name.endswith(".bib") else [name + ".bib", name]
        for c in cands:
            p = os.path.join(project, c)
            if os.path.isfile(p) and p not in bib_paths:
                bib_paths.append(p)
    if not bib_paths:
        for dirpath, dirnames, filenames in os.walk(project):
            dirnames[:] = [d for d in dirnames if d not in (".git", "_citebuild")]
            for f in filenames:
                if f.endswith(".bib"):
                    bib_paths.append(os.path.join(dirpath, f))
    bib_paths = sorted(bib_paths)

    bib_entries, bib_duplicates, bib_errors = {}, [], []
    for bp in bib_paths:
        es, ds, errs = parse_bib_file(bp)
        for k, e in es.items():
            e["file"] = rel(bp, project)
            bib_entries.setdefault(k, e)
        bib_duplicates.extend(ds)
        bib_errors.extend(errs)

    bib_keys = set(bib_entries)
    label_keys = {}
    duplicate_labels = []
    for lab in labels:
        if lab["key"] in label_keys:
            duplicate_labels.append({"key": lab["key"],
                                     "sites": [label_keys[lab["key"]],
                                               {"file": lab["file"],
                                                "line": lab["line"]}]})
        else:
            label_keys[lab["key"]] = {"file": lab["file"], "line": lab["line"]}

    for c in citations:
        e = bib_entries.get(c["key"])
        c["resolved"] = e is not None
        c["bib"] = ({"file": e["file"], "line": e["line"],
                     "entrytype": e["entrytype"]} if e else None)
        c["candidates"] = [] if e else candidates(c["key"], bib_keys)
    for r in references:
        r["resolved"] = r["key"] in label_keys
        r["candidates"] = [] if r["resolved"] else candidates(r["key"], label_keys)

    undefined_cites = sorted({c["key"] for c in citations if not c["resolved"]})
    undefined_refs = sorted({r["key"] for r in references if not r["resolved"]})

    field_issues = []
    for key, e in sorted(bib_entries.items()):
        miss_req, miss_rec = missing_fields(e)
        if miss_req is None:
            field_issues.append({"key": key, "entrytype": e["entrytype"],
                                 "file": e["file"], "line": e["line"],
                                 "unknown_entrytype": True,
                                 "missing_required": [], "missing_recommended": []})
        elif miss_req or miss_rec:
            field_issues.append({"key": key, "entrytype": e["entrytype"],
                                 "file": e["file"], "line": e["line"],
                                 "unknown_entrytype": False,
                                 "missing_required": miss_req,
                                 "missing_recommended": miss_rec})

    cited_keys = {c["key"] for c in citations if c["command"] != "nocite"}
    unreferenced = []
    for key, e in sorted(bib_entries.items()):
        e["cited"] = nocite_all or key in cited_keys
        if not e["cited"]:
            unreferenced.append({"key": key, "file": e["file"], "line": e["line"],
                                 "entrytype": e["entrytype"]})

    # \cite 顺序与重复（信息级）
    first_appearance, seen = [], set()
    repeats = {}
    for c in citations:
        if c["key"] not in seen:
            seen.add(c["key"])
            first_appearance.append(c["key"])
        else:
            repeats.setdefault(c["key"], []).append(
                {"file": c["file"], "line": c["line"]})

    graph = {
        "generated_by": "citeaudit.py（静态解析，未经编译验证）",
        "project": project,
        "tex_files": [rel(t, project) for t in ordered],
        "bib_files": [rel(b, project) for b in bib_paths],
        "citations": citations,
        "references": references,
        "labels": labels,
        "duplicate_labels": duplicate_labels,
        "bib_entries": {k: {kk: vv for kk, vv in v.items()} for k, v in
                        sorted(bib_entries.items())},
        "bib_duplicate_keys": bib_duplicates,
        "bib_parse_errors": bib_errors,
        "field_issues": field_issues,
        "undefined_citations": undefined_cites,
        "undefined_references": undefined_refs,
        "unreferenced_bib_entries": unreferenced,
        "cite_first_appearance_order": first_appearance,
        "cite_repeats": repeats,
        "summary": {
            "tex_files": len(tex_files), "bib_files": len(bib_paths),
            "cite_sites": len(citations),
            "distinct_cited_keys": len({c['key'] for c in citations}),
            "undefined_citations": len(undefined_cites),
            "ref_sites": len(references),
            "undefined_references": len(undefined_refs),
            "labels": len(labels), "duplicate_labels": len(duplicate_labels),
            "bib_entries": len(bib_entries),
            "bib_duplicate_keys": len(bib_duplicates),
            "unreferenced_bib_entries": len(unreferenced),
            "entries_missing_required_fields":
                sum(1 for f in field_issues if f["missing_required"]),
            "entries_with_field_issues": len(field_issues),
        },
    }
    return graph


def render_report(graph, banner=None):
    s = graph["summary"]
    L = []
    if banner:
        L.append(banner)
        L.append("")
    L.append("# 引用图谱静态审计报告（citeaudit，未编译）")
    L.append("")
    L.append("## 概要")
    L.append("")
    L.append("| 指标 | 数量 |")
    L.append("| --- | --- |")
    rows = [(".tex 文件", s["tex_files"]), (".bib 文件", s["bib_files"]),
            ("引用点（\\cite 出现次数）", s["cite_sites"]),
            ("去重后的被引键", s["distinct_cited_keys"]),
            ("**未定义引用（undefined citations）**", s["undefined_citations"]),
            ("交叉引用点（\\ref/\\eqref 等）", s["ref_sites"]),
            ("**未定义交叉引用**", s["undefined_references"]),
            ("\\label 总数", s["labels"]),
            ("**重复 \\label**", s["duplicate_labels"]),
            ("bib 条目数", s["bib_entries"]),
            ("**bib 重复键**", s["bib_duplicate_keys"]),
            ("**未被引用的 bib 条目**", s["unreferenced_bib_entries"]),
            ("**缺必需字段的 bib 条目**", s["entries_missing_required_fields"]),
            ("有字段问题（含建议字段）的 bib 条目",
             s["entries_with_field_issues"])]
    for k, v in rows:
        L.append(f"| {k} | {v} |")
    L.append("")
    L.append("> 本报告只给建议（suggestions），不自动修改任何 .tex/.bib 文件；"
             "是否采纳由 Agent 判断。")
    L.append("")

    L.append("## 1. 未定义引用（undefined citations）")
    L.append("")
    bad = [c for c in graph["citations"] if not c["resolved"]]
    if not bad:
        L.append("无。所有 \\cite 键都能解析到 bib 条目。")
    else:
        by_key = {}
        for c in bad:
            by_key.setdefault(c["key"], []).append(c)
        for key in graph["undefined_citations"]:
            sites = by_key[key]
            L.append(f"### `{key}`")
            L.append("")
            L.append("- 引用点：" + "；".join(
                f"`{c['file']}:{c['line']}`（\\{c['command']}）" for c in sites))
            cands = sites[0]["candidates"]
            if cands:
                L.append("- 最接近的 bib 键候选（仅建议，需人工核对）：")
                for cd in cands:
                    tag = "弱匹配" if cd["weak"] else "强匹配"
                    L.append(f"  - `{cd['key']}`（相似度 {cd['similarity']}，{tag}）")
            else:
                L.append("- 未找到相近的 bib 键候选（可能确实缺少条目）。")
            L.append("")
    L.append("")

    L.append("## 2. 未定义交叉引用与重复标签")
    L.append("")
    if graph["undefined_references"]:
        L.append("### 未定义交叉引用（\\ref/\\eqref 指向不存在的 \\label）")
        L.append("")
        by_key = {}
        for r in graph["references"]:
            if not r["resolved"]:
                by_key.setdefault(r["key"], []).append(r)
        for key in graph["undefined_references"]:
            sites = by_key[key]
            L.append(f"- `{key}`：引用点 " + "；".join(
                f"`{r['file']}:{r['line']}`（\\{r['command']}）" for r in sites))
            cands = sites[0]["candidates"]
            if cands:
                L.append("  - 候选 label：" + "；".join(
                    f"`{c['key']}`（{'弱匹配' if c['weak'] else '强匹配'}）"
                    for c in cands))
        L.append("")
    if graph["duplicate_labels"]:
        L.append("### 重复 \\label（同一键定义多次）")
        L.append("")
        for d in graph["duplicate_labels"]:
            sites = "；".join(f"`{x['file']}:{x['line']}`" for x in d["sites"])
            L.append(f"- `{d['key']}` 定义于 {sites}")
        L.append("")
    if not graph["undefined_references"] and not graph["duplicate_labels"]:
        L.append("无。")
        L.append("")

    L.append("## 3. 未被引用的 bib 条目")
    L.append("")
    if graph["unreferenced_bib_entries"]:
        L.append("以下条目在 .bib 中存在但正文从未 \\cite（**不要直接删除**："
                 "可能是漏引，也可能是备查文献，由 Agent 判断处置）：")
        L.append("")
        for u in graph["unreferenced_bib_entries"]:
            L.append(f"- `{u['key']}`（@{u['entrytype']}，`{u['file']}:{u['line']}`）")
    else:
        L.append("无。")
    L.append("")

    L.append("## 4. bib 字段缺失（按 entrytype 最小字段）")
    L.append("")
    L.append("规则详见 references/bib-field-rules.md。")
    L.append("")
    if graph["field_issues"]:
        L.append("| 条目 | entrytype | 位置 | 缺必需字段 | 缺建议字段 |")
        L.append("| --- | --- | --- | --- | --- |")
        for f in graph["field_issues"]:
            if f["unknown_entrytype"]:
                L.append(f"| `{f['key']}` | @{f['entrytype']} | "
                         f"`{f['file']}:{f['line']}` | 未知 entrytype，跳过检查 | — |")
            else:
                req = "、".join(f["missing_required"]) or "—"
                rec = "、".join(f["missing_recommended"]) or "—"
                L.append(f"| `{f['key']}` | @{f['entrytype']} | "
                         f"`{f['file']}:{f['line']}` | {req} | {rec} |")
    else:
        L.append("无。")
    L.append("")

    L.append("## 5. \\cite 顺序与重复（信息级）")
    L.append("")
    L.append("首次出现顺序（数字编号样式下参考文献表通常按此排序）：")
    L.append("")
    order = graph["cite_first_appearance_order"]
    L.append(" → ".join(f"`{k}`" for k in order) if order else "无引用")
    L.append("")
    if graph["cite_repeats"]:
        L.append("")
        L.append("重复引用（同一键被 \\cite 多次，一般无害，列出供核对）：")
        L.append("")
        for key, sites in sorted(graph["cite_repeats"].items()):
            L.append(f"- `{key}` 另见于 " + "；".join(
                f"`{x['file']}:{x['line']}`" for x in sites))
    if graph["bib_duplicate_keys"]:
        L.append("")
        L.append("### .bib 中的重复键（bibtex 会报 Repeated entry）")
        L.append("")
        for d in graph["bib_duplicate_keys"]:
            L.append(f"- `{d['key']}`：`{d['file']}:{d['line']}`"
                     f"（首次在 {d['first_line']} 行）")
    if graph["bib_parse_errors"]:
        L.append("")
        L.append("### .bib 解析异常")
        L.append("")
        for e in graph["bib_parse_errors"]:
            L.append(f"- `{e.get('file')}`"
                     + (f":{e['line']}" if e.get("line") else "")
                     + f"：{e['error']}")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="LaTeX 引用图谱静态审计（不编译）")
    ap.add_argument("--project", required=True, help="LaTeX 工程目录")
    ap.add_argument("--main", default=None, help="主 .tex（相对工程目录），缺省自动探测")
    ap.add_argument("--bib", action="append", default=None,
                    help="指定 .bib（可多次），缺省按 \\bibliography/\\addbibresource/全目录探测")
    ap.add_argument("--work", required=True, help="输出目录")
    ap.add_argument("--banner", default=None,
                    help="写入报告页眉的一行标注（如合成示例声明）")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.project):
        print(f"[citeaudit] 错误：工程目录不存在：{args.project}", file=sys.stderr)
        return 1
    os.makedirs(args.work, exist_ok=True)
    graph = audit(args.project, main=args.main, bib_args=args.bib)
    graph_path = os.path.join(args.work, "citation_graph.json")
    with open(graph_path, "w", encoding="utf-8") as fh:
        json.dump(graph, fh, ensure_ascii=False, indent=2)
    report = render_report(graph, banner=args.banner)
    report_path = os.path.join(args.work, "citation_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    s = graph["summary"]
    print(f"[citeaudit] 完成：{s['cite_sites']} 个引用点，"
          f"未定义引用 {s['undefined_citations']}，"
          f"未定义交叉引用 {s['undefined_references']}，"
          f"重复 label {s['duplicate_labels']}，"
          f"未被引用 bib 条目 {s['unreferenced_bib_entries']}，"
          f"字段问题条目 {s['entries_with_field_issues']}")
    print(f"[citeaudit] 输出：{graph_path}")
    print(f"[citeaudit] 输出：{report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
