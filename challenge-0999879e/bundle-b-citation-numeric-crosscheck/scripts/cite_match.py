#!/usr/bin/env python3
"""cite_match.py — 引文标记与参考文献表机械对照（bundle-b）

解析参考文献小节（编号制 [1] / `1.` 与作者-年制均尝试），正文引文标记
逐处定位（上下 80 字符语境），机械判定：
  - 悬空引用（正文引了不存在的编号/条目）
  - 未被引用条目
  - 重复著录（DOI 相同或条目文本高度相似）
  - DOI 格式异常
支持判定：仅当 /input 中存在被引文献全文/摘要文件（命名含 ref<n> 或
fulltext/ 子目录）时做确定性重叠判定；否则一律 cannot_verify 进待复核。
无参考文献小节 → WARNING 并如实记录。

输出：work/citation_ledger.json 与 work/citation_ledger.md。
退出码：0 成功；非 0 失败并打印原因到 stderr。仅用标准库。
"""
import argparse
import difflib
import json
import os
import re
import sys
import tempfile

VERSION = "1.0.0"

REF_HEAD = re.compile(
    r"^\s*(?:#{1,6}\s*)?(参考文献|references|bibliography|参考书目)\s*[:：]?\s*$",
    re.I)
MD_HEAD = re.compile(r"^#{1,6}\s+")
NUM_ENTRY = re.compile(r"^\s*(?:\[(\d{1,3})\]|(\d{1,3})\s*[\.、\)])\s+(.+)")
CITE_BRACKET = re.compile(
    r"\[((?:\d{1,3}\s*(?:[,，、]\s*|\s*[-–—]\s*)?)+)\]")
AUTHOR_YEAR = re.compile(
    r"\(([A-Z][A-Za-z\-]+)(?:\s+et\s+al\.)?,\s*((?:19|20)\d{2})[a-z]?\)")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s,;\]\)\"']+")
DOI_HINT = re.compile(r"\bdoi\b\s*[:：]?\s*(\S+)", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

TEXT_EXT = {".md", ".txt", ".tex"}
SKIP_FILES = {"case.json", "task.md", "answers.json"}


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def norm_text(s):
    return re.sub(r"[\s\W_]+", "", s.lower())


def locate_references(text):
    """返回 (ref_start_line, ref_lines[(line_no, line)], found, style_hint)。"""
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        if REF_HEAD.match(line.strip()):
            ref_lines = []
            for j in range(i, len(lines)):
                ln = lines[j]
                if j > i and MD_HEAD.match(ln.strip()):
                    break
                ref_lines.append((j + 1, ln))
            return i, ref_lines, True, "numbered_or_authoryear"
    return None, [], False, None


def parse_numbered_entries(ref_lines):
    entries = {}
    cur_no = None
    for ln, line in ref_lines:
        m = NUM_ENTRY.match(line)
        if m:
            cur_no = int(m.group(1) or m.group(2))
            entries[cur_no] = {"n": cur_no, "line": ln, "raw": m.group(3).strip()}
        elif cur_no is not None and line.strip():
            entries[cur_no]["raw"] += " " + line.strip()
    return [entries[k] for k in sorted(entries)]


def parse_authoryear_entries(ref_lines):
    entries = []
    for ln, line in ref_lines:
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^([A-Z][A-Za-z\-]+)", s)
        y = YEAR_RE.search(s)
        if m and y:
            entries.append({"n": None, "line": ln, "raw": s,
                            "surname": m.group(1).lower(),
                            "year": y.group(0)})
    return entries


def expand_citation_group(body):
    nums = []
    for part in re.split(r"[,，、]", body):
        part = part.strip()
        m = re.match(r"^(\d{1,3})\s*[-–—]\s*(\d{1,3})$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < a <= b and b - a <= 50:
                nums.extend(range(a, b + 1))
            else:
                nums.append(a)
        elif part.isdigit():
            nums.append(int(part))
    return nums


def find_intext_citations(text, ref_start_line):
    cites = []
    lines = text.splitlines()
    line_offsets = []
    off = 0
    for ln in lines:
        line_offsets.append(off)
        off += len(ln) + 1
    for m in CITE_BRACKET.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        if ref_start_line and line_no >= ref_start_line:
            continue  # 参考文献小节内部的 [n] 是著录标记而非引文
        ctx = text[max(0, m.start() - 80):m.end() + 80].replace("\n", " ")
        for n in expand_citation_group(m.group(1)):
            cites.append({"n": n, "line": line_no, "marker": m.group(0),
                          "context": ctx.strip()[:200]})
    return cites


def find_authoryear_citations(text, ref_start_line):
    cites = []
    for m in AUTHOR_YEAR.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        if ref_start_line and line_no >= ref_start_line:
            continue
        ctx = text[max(0, m.start() - 80):m.end() + 80].replace("\n", " ")
        cites.append({"surname": m.group(1).lower(), "year": m.group(2),
                      "line": line_no, "marker": m.group(0),
                      "context": ctx.strip()[:200]})
    return cites


def check_duplicates(entries):
    dups = []
    dois = {}
    for e in entries:
        m = DOI_RE.search(e["raw"])
        e["doi"] = m.group(0).rstrip(".") if m else None
        if e["doi"]:
            dois.setdefault(e["doi"].lower(), []).append(e["n"])
    for doi, ns in sorted(dois.items()):
        if len(ns) > 1:
            dups.append({"entries": ns, "reason": "DOI 相同: %s" % doi,
                         "severity": "major"})
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            na, nb = norm_text(a["raw"]), norm_text(b["raw"])
            if not na or not nb:
                continue
            ratio = difflib.SequenceMatcher(None, na, nb).ratio()
            ya, yb = YEAR_RE.search(a["raw"]), YEAR_RE.search(b["raw"])
            same_year = ya and yb and ya.group(0) == yb.group(0)
            if ratio >= 0.85 and (same_year or (a.get("doi") and a["doi"] == b.get("doi"))):
                pair = sorted(x for x in (a["n"], b["n"]) if x is not None)
                if not any(set(d["entries"]) == set(pair) for d in dups):
                    dups.append({"entries": pair,
                                 "reason": "条目文本相似度 %.2f" % ratio,
                                 "severity": "major"})
    return dups


def check_dois(entries):
    issues = []
    for e in entries:
        for hint in DOI_HINT.findall(e["raw"]):
            token = hint.rstrip(".;,")
            if token.lower() in ("https://doi.org", "http://doi.org"):
                continue
            token = re.sub(r"^https?://doi\.org/", "", token, flags=re.I)
            if not DOI_RE.fullmatch(token):
                issues.append({"entry": e["n"], "token": hint,
                               "issue": "DOI 格式异常"})
    return issues


def load_fulltexts(input_dir):
    """查找被引文献全文/摘要材料：fulltext/ 子目录或文件名含 ref<n>。"""
    ft = {}
    candidates = []
    ft_dir = os.path.join(input_dir, "fulltext")
    if os.path.isdir(ft_dir):
        candidates.extend(os.path.join(ft_dir, f) for f in sorted(os.listdir(ft_dir)))
    candidates.extend(os.path.join(input_dir, f)
                      for f in sorted(os.listdir(input_dir))
                      if re.search(r"ref\d+", f, re.I))
    for path in candidates:
        if not os.path.isfile(path):
            continue
        if os.path.splitext(path)[1].lower() not in TEXT_EXT:
            continue
        m = re.search(r"ref\D{0,4}(\d{1,3})", os.path.basename(path), re.I)
        if m:
            ft[int(m.group(1))] = read_text(path)
    return ft


def judge_support(cite, source_text):
    """确定性重叠启发式：引语句与文献文本的词元 Jaccard。
    仅作初判，结论必须人工复核；阈值见 references/support_rubric.md。"""
    stop = {"the", "a", "an", "of", "and", "in", "on", "is", "are", "was",
            "we", "our", "that", "this", "with", "for", "to", "by"}
    def toks(s):
        return set(w for w in re.findall(r"[a-z]{3,}|[\u4e00-\u9fff]{2,}",
                                         s.lower()) if w not in stop)
    a, b = toks(cite["context"]), toks(source_text)
    if not a or not b:
        return "cannot_verify", 0.0
    j = len(a & b) / len(a | b)
    if j >= 0.25:
        return "supports", j
    if j >= 0.08:
        return "partially_supports", j
    return "cannot_verify", j  # 重叠过低时不下 not_supported，防误报


def render_md(ledger):
    out = ["# 引文对照台账", "",
           "- 参考文献小节: %s" % ("已找到" if ledger["references_section_found"]
                                   else "未找到（WARNING）"),
           "- 著录条目: %d；正文引文标记: %d" % (len(ledger["entries"]),
                                              len(ledger["citations"])), ""]
    c = ledger["checks"]
    out.append("## 机械检查结果")
    out.append("- 悬空引用: %d 处" % len(c["dangling"]))
    for d in c["dangling"]:
        out.append("  - [%s] @ 第%d行: …%s…" % (d["n"], d["line"], d["context"][:80]))
    out.append("- 未被引用条目: %s" % (", ".join("[%s]" % n for n in c["uncited"]) or "无"))
    out.append("- 重复著录: %d 组" % len(c["duplicates"]))
    for d in c["duplicates"]:
        out.append("  - 条目 %s: %s" % (d["entries"], d["reason"]))
    out.append("- DOI 格式异常: %d 处" % len(c["doi_issues"]))
    for d in c["doi_issues"]:
        out.append("  - 条目[%s]: %s (%s)" % (d["entry"], d["token"], d["issue"]))
    out.append("")
    out.append("## 支持判定（仅全文/摘要可见时；否则 cannot_verify）")
    for s in ledger["support"]:
        out.append("- [%s] %s（%s）" % (s["entry"], s["verdict"], s["note"]))
    if ledger["warnings"]:
        out.append("")
        out.append("## 警告")
        out.extend("- %s" % w for w in ledger["warnings"])
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="引文标记与参考文献表机械对照 + 支持判定台账")
    ap.add_argument("--input", default="/input", help="输入目录")
    ap.add_argument("--work", default="/app/work", help="工作目录")
    ap.add_argument("--manuscript", default=None,
                    help="指定稿件文件（默认取 input 下首个 md/txt/tex）")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.input):
        print("错误: 输入目录不存在: %s" % args.input, file=sys.stderr)
        return 2
    os.makedirs(args.work, exist_ok=True)

    mpath = args.manuscript
    if not mpath:
        for fn in sorted(os.listdir(args.input)):
            if fn in SKIP_FILES:
                continue
            p = os.path.join(args.input, fn)
            if os.path.isfile(p) and os.path.splitext(fn)[1].lower() in TEXT_EXT:
                mpath = p
                break
    if not mpath or not os.path.isfile(mpath):
        print("错误: 未找到可解析的稿件文本文件", file=sys.stderr)
        return 3

    text = read_text(mpath)
    warnings = []
    ref_start, ref_lines, found, _ = locate_references(text)
    entries, citations, style = [], [], "none"
    dangling, uncited, dups, doi_issues, support = [], [], [], [], []

    if not found:
        warnings.append("WARNING: 未找到参考文献小节，引文对照降级为仅扫描正文标记")
    else:
        entries = parse_numbered_entries(ref_lines)
        if entries:
            style = "numbered"
            citations = find_intext_citations(text, ref_start)
            have = {e["n"] for e in entries}
            cited = {c["n"] for c in citations}
            for c in citations:
                if c["n"] not in have:
                    dangling.append(c)
            uncited = sorted(have - cited)
            dups = check_duplicates(entries)
            doi_issues = check_dois(entries)
        else:
            entries = parse_authoryear_entries(ref_lines)
            if entries:
                style = "author-year"
                ay_cites = find_authoryear_citations(text, ref_start)
                citations = ay_cites
                have = {(e["surname"], e["year"]) for e in entries}
                seen = set()
                for c in ay_cites:
                    key = (c["surname"], c["year"])
                    if key not in have:
                        dangling.append({"n": "%s %s" % key, "line": c["line"],
                                         "context": c["context"]})
                    seen.add(key)
                uncited = ["%s %s" % (e["surname"], e["year"]) for e in entries
                           if (e["surname"], e["year"]) not in seen]
                dups = check_duplicates(entries)
            else:
                warnings.append("WARNING: 参考文献小节存在但未能解析出任何条目")

    # 支持判定：全文/摘要可见才判，否则 cannot_verify
    fulltexts = load_fulltexts(args.input)
    dangling_ns = {d["n"] for d in dangling}
    cited_ns = sorted({c["n"] for c in citations
                       if isinstance(c.get("n"), int) and c["n"] not in dangling_ns})
    for n in cited_ns:
        if n in fulltexts:
            verdict, score = judge_support(
                next(c for c in citations if c.get("n") == n), fulltexts[n])
            note = "全文可见，词元重叠 %.3f（启发式初判，需人工复核）" % score
        else:
            verdict, note = "cannot_verify", "被引文献全文/摘要不可见"
        support.append({"entry": n, "verdict": verdict, "note": note})

    ledger = {
        "tool": "cite_match", "version": VERSION,
        "manuscript": os.path.basename(mpath),
        "references_section_found": found,
        "style": style,
        "entries": entries,
        "citations": citations,
        "checks": {"dangling": dangling, "uncited": uncited,
                   "duplicates": dups, "doi_issues": doi_issues},
        "support": support,
        "warnings": warnings,
    }
    fd, tmp = tempfile.mkstemp(dir=args.work, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(args.work, "citation_ledger.json"))
    with open(os.path.join(args.work, "citation_ledger.md"), "w",
              encoding="utf-8") as f:
        f.write(render_md(ledger))
    print("cite_match 完成: 条目 %d, 引文 %d 处, 悬空 %d, 未引 %d, 重复 %d 组, DOI 异常 %d, 支持判定 %d 条" % (
        len(entries), len(citations), len(dangling), len(uncited),
        len(dups), len(doi_issues), len(support)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
