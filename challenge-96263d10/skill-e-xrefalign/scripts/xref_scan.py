#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xref_scan.py -- 图表题注与正文交叉引用一致性扫描（排得对的语义层）。

抽取有序块流（DOCX 段落/表格/图片段，或 MD/TXT 空行分块），识别：
  题注：行首 图N / 表N / Figure N / Fig. N / Table N
  正文引用：行内 图N / 表N / 见图N / Fig. N / Table N（题注行自身除外）
检查：编号重复、编号断档、悬空引用（引用了不存在的编号）、
题注位置（表题注应在表上方、图题注应在图下方——可被任务规则覆盖）。

用法: python3 xref_scan.py 稿件.docx|稿件.md --out xref_report.json \
        [--figure-caption below|above] [--table-caption above|below]
退出码: 0 无 ERROR; 1 有 ERROR（WARNING 不阻断）。
"""
import argparse, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
RE_CAP = re.compile(r"^\s*(图|表|Figure|Fig\.|Table)\s*([0-9]+(?:[-.][0-9]+)?)", re.I)
RE_REF = re.compile(r"(图|表|Figure|Fig\.?|Table)\s*([0-9]+(?:[-.][0-9]+)?)", re.I)

def kind_of(label):
    return "figure" if label.lower() in ("图", "figure", "fig.", "fig") else "table"

def blocks_docx(path):
    zf = zipfile.ZipFile(path)
    doc = ET.fromstring(zf.read("word/document.xml"))
    blocks = []
    body = doc.find("%sbody" % W)
    for child in list(body):
        if child.tag == "%sp" % W:
            text = "".join(t.text or "" for t in child.findall(".//%st" % W))
            has_img = child.find(".//%sdrawing" % W) is not None or child.find(".//%spict" % W) is not None
            blocks.append({"type": "image" if has_img else "para", "text": text})
        elif child.tag == "%stbl" % W:
            text = " ".join(t.text or "" for t in child.findall(".//%st" % W))
            blocks.append({"type": "table", "text": text})
    return blocks

def blocks_text(path):
    text = open(path, encoding="utf-8").read()
    out = []
    for b in re.split(r"\n\s*\n", text):
        b = b.strip()
        if not b:
            continue
        if re.search(r"!\[[^\]]*\]\(|\\includegraphics", b):
            out.append({"type": "image", "text": re.sub(r"!\[[^\]]*\]\([^)]*\)|\\includegraphics(\[[^]]*\])?\{[^}]*\}", "", b).strip()})
        elif b.lstrip().startswith("|") or "\\begin{tabular}" in b:
            out.append({"type": "table", "text": b})
        else:
            out.append({"type": "para", "text": b})
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("doc")
    ap.add_argument("--out", required=True)
    ap.add_argument("--figure-caption", default="below", choices=["below", "above"])
    ap.add_argument("--table-caption", default="above", choices=["above", "below"])
    a = ap.parse_args()

    ext = os.path.splitext(a.doc)[1].lower()
    try:
        blocks = blocks_docx(a.doc) if ext == ".docx" else blocks_text(a.doc)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        print("ERROR: 输入不可读: %s" % e, file=sys.stderr)
        sys.exit(2)

    captions, refs = [], []
    for i, b in enumerate(blocks):
        m = RE_CAP.match(b["text"])
        if m:
            captions.append({"block": i, "kind": kind_of(m.group(1)), "label": m.group(1),
                             "num": m.group(2), "text": b["text"][:100]})
            continue  # 题注行不再抽取正文引用
        for m in RE_REF.finditer(b["text"]):
            refs.append({"block": i, "kind": kind_of(m.group(1)), "num": m.group(2),
                         "context": b["text"][max(0, m.start() - 20):m.end() + 20]})

    issues = []
    by_kind = {"figure": {}, "table": {}}
    for c in captions:
        by_kind[c["kind"]].setdefault(c["num"], []).append(c["block"])
    for kind, d in by_kind.items():
        for num, blks in d.items():
            if len(blks) > 1:
                issues.append({"severity": "ERROR", "code": "duplicate_number",
                               "detail": "%s %s 题注重复（块 %s）" % (kind, num, blks)})
        nums = sorted(d.keys(), key=lambda s: [int(x) for x in re.split(r"[-.]", s)])
        simple = [n for n in nums if n.isdigit()]
        if simple and [int(n) for n in simple] != list(range(1, len(simple) + 1)):
            issues.append({"severity": "WARNING", "code": "numbering_gap",
                           "detail": "%s 编号序列 %s 非 1..N 连续（含子编号时属正常）" % (kind, simple)})
    cap_keys = {(c["kind"], c["num"]) for c in captions}
    for r in refs:
        if (r["kind"], r["num"]) not in cap_keys:
            issues.append({"severity": "ERROR", "code": "dangling_reference",
                           "detail": "块 %d 引用了不存在的 %s %s：…%s…" % (r["block"], r["kind"], r["num"], r["context"][:60])})
    ref_keys = {(r["kind"], r["num"]) for r in refs}
    for c in captions:
        if (c["kind"], c["num"]) not in ref_keys:
            issues.append({"severity": "WARNING", "code": "unreferenced_caption",
                           "detail": "%s %s 未被正文引用（块 %d）" % (c["kind"], c["num"], c["block"])})
    # 题注位置
    for c in captions:
        i, want = c["block"], (a.figure_caption if c["kind"] == "figure" else a.table_caption)
        obj_type = "image" if c["kind"] == "figure" else "table"
        prev = blocks[i - 1] if i > 0 else None
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        ok = (want == "below" and prev and prev["type"] == obj_type) or \
             (want == "above" and nxt and nxt["type"] == obj_type)
        if not ok:
            issues.append({"severity": "ERROR", "code": "caption_position",
                           "detail": "%s %s 题注应在%s方（块 %d 未满足）" % (c["label"], c["num"], "下" if want == "below" else "上", i)})

    n_err = sum(1 for x in issues if x["severity"] == "ERROR")
    report = {"doc": a.doc, "rules": {"figure_caption": a.figure_caption, "table_caption": a.table_caption},
              "captions": captions, "references": refs,
              "summary": {"captions": len(captions), "in_text_refs": len(refs),
                          "errors": n_err, "warnings": len(issues) - n_err},
              "issues": issues}
    json.dump(report, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("captions=%d refs=%d ERROR=%d WARNING=%d -> %s" % (
        len(captions), len(refs), n_err, len(issues) - n_err, a.out))
    for x in issues:
        print("  [%s] %s: %s" % (x["severity"], x["code"], x["detail"][:90]))
    sys.exit(1 if n_err else 0)

if __name__ == "__main__":
    main()
