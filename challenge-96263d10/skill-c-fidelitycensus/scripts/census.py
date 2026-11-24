#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""census.py -- 内容单元普查：把文档抽成可全等比对的内容清单（转得全的上游）。

支持 .docx（stdlib OOXML）与 .md/.txt/.tex（文本型）。
普查对象：有序文本单元、数字 token、引用 token、对象计数（图/表/公式/脚注/
批注/超链接/域/书签）。格式可以变，内容单元不许无声增减。

用法:
  python3 census.py 文档.docx --out census.json
  python3 census.py 稿件.md  --out census.json
退出码: 0 成功; 2 输入不可读。
"""
import argparse, hashlib, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET
from collections import Counter

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

RE_NUM = re.compile(r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?(?:%|‰)?")
RE_CITE_NUM = re.compile(r"\[\d+(?:\s*[-,]\s*\d+)*\]")
RE_CITE_AD = re.compile(r"\([A-Z][A-Za-z]+(?:\s+et\s+al\.?)?(?:\s*&\s*[A-Z][A-Za-z]+)?,\s*(?:19|20)\d{2}[a-z]?\)|（[^（）]{1,20}?，\s*(?:19|20)\d{2}[a-z]?）")

def tokens(text):
    return {"numeric": sorted(Counter(RE_NUM.findall(text)).items()),
            "citation": sorted(Counter(RE_CITE_NUM.findall(text) + RE_CITE_AD.findall(text)).items())}

def census_docx(path):
    try:
        zf = zipfile.ZipFile(path)
        doc = ET.fromstring(zf.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        print("ERROR: 不可读 DOCX: %s" % e, file=sys.stderr)
        sys.exit(2)
    units, objects = [], Counter()
    full_text = []
    body = doc.find("%sbody" % W)
    for child in list(body):
        tag = child.tag
        if tag == "%sp" % W:
            text = "".join(t.text or "" for t in child.findall(".//%st" % W))
            st = child.find("%spPr/%spStyle" % (W, W))
            flags = []
            if child.find(".//%sdrawing" % W) is not None or child.find(".//%spict" % W) is not None:
                flags.append("drawing"); objects["images"] += 1
            if child.find(".//%soMath" % M) is not None or child.find(".//%soMathPara" % M) is not None:
                flags.append("omml_math"); objects["equations"] += 1
            if child.findall(".//%sinstrText" % W) or child.findall(".//%sfldSimple" % W):
                flags.append("field"); objects["fields"] += 1
            for _ in child.findall(".//%sfootnoteReference" % W):
                objects["footnote_refs"] += 1
            for _ in child.findall(".//%sendnoteReference" % W):
                objects["endnote_refs"] += 1
            for _ in child.findall(".//%scommentReference" % W):
                objects["comment_refs"] += 1
            hyp = child.findall(".//%shyperlink" % W)
            if hyp:
                flags.append("hyperlink"); objects["hyperlinks"] += len(hyp)
            for _ in child.findall(".//%sbookmarkStart" % W):
                objects["bookmarks"] += 1
            units.append({"kind": "paragraph",
                          "style": st.get("%sval" % W) if st is not None else None,
                          "text": text, "flags": flags})
            full_text.append(text)
        elif tag == "%stbl" % W:
            rows = child.findall("%str" % W)
            cells = child.findall(".//%stc" % W)
            text = " | ".join("".join(t.text or "" for t in tc.findall(".//%st" % W)) for tc in cells)
            objects["tables"] += 1
            units.append({"kind": "table", "style": None,
                          "text": text, "flags": ["rows=%d" % len(rows), "cells=%d" % len(cells)]})
            full_text.append(text)
    # 独立部件：脚注/尾注/批注正文
    notes = {}
    for part, key in (("word/footnotes.xml", "footnotes"), ("word/endnotes.xml", "endnotes"),
                      ("word/comments.xml", "comments")):
        try:
            root = ET.fromstring(zf.read(part))
            texts = ["".join(t.text or "" for t in n.findall(".//%st" % W))
                     for n in list(root) if n.get("%stype" % W) not in ("separator", "continuationSeparator")]
            texts = [t for t in texts if t.strip()]
            notes[key] = texts
            objects[key] = len(texts)
        except KeyError:
            pass
    full = "\n".join(full_text + [t for v in notes.values() for t in v])
    return units, objects, tokens(full)

def census_text(path):
    try:
        text = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as e:
        print("ERROR: 不可读文本: %s" % e, file=sys.stderr)
        sys.exit(2)
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    objects = Counter()
    objects["images"] = len(re.findall(r"!\[[^\]]*\]\(|\\includegraphics", text))
    objects["equations"] = len(re.findall(r"\$\$.*?\\begin\{equation\}|\$\$", text, re.S)) or len(re.findall(r"\\begin\{equation\}", text))
    objects["tables"] = len(re.findall(r"\\begin\{tabular\}", text)) + sum(1 for b in blocks if b.count("\n") >= 1 and b.lstrip().startswith("|"))
    objects["footnotes"] = len(re.findall(r"\\footnote\{|\[\^[^\]]+\]:", text))
    objects["hyperlinks"] = len(re.findall(r"https?://|\]\(http", text))
    units = [{"kind": "block", "style": None, "text": b, "flags": []} for b in blocks]
    return units, objects, tokens(text)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("doc")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ext = os.path.splitext(a.doc)[1].lower()
    if ext == ".docx":
        units, objects, tk = census_docx(a.doc)
    elif ext in (".md", ".txt", ".tex", ".markdown"):
        units, objects, tk = census_text(a.doc)
    else:
        print("ERROR: 不支持的格式 %s（支持 .docx/.md/.txt/.tex）" % ext, file=sys.stderr)
        sys.exit(2)
    h = hashlib.sha256()
    with open(a.doc, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    out = {"census_version": "1.0", "file": a.doc, "sha256": h.hexdigest(),
           "format": ext.lstrip("."), "unit_count": len(units), "units": units,
           "objects": dict(sorted(objects.items())), "tokens": tk}
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("units=%d objects=%d numeric_tokens=%d citation_tokens=%d -> %s" % (
        len(units), sum(objects.values()), sum(c for _, c in tk["numeric"]),
        sum(c for _, c in tk["citation"]), a.out))

if __name__ == "__main__":
    main()
