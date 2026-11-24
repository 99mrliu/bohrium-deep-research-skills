#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refstyle_check.py -- 参考文献条目 GB/T 7714 机器初筛（排得对的著录层）。

从 DOCX 或 MD/TXT 中提取参考文献条目（"参考文献/References"节之后，
或全文以 [n] 开头的行），逐条检查：
  ERROR   缺年份；条目无法解析
  WARNING 缺文献类型标志 [J]/[M]/[D]...；[J] 条目缺 年,卷(期):页 模式；
          [M] 条目缺 出版地:出版社 模式；>3 作者未用"等/et al."截断；
          条末缺句点；中英文标点混用嫌疑
机器初筛只抓形式特征，著录语义仍须人工抽核（进 manual_confirm）。

用法: python3 refstyle_check.py 稿件.docx|稿件.md --out ref_report.json
退出码: 0 无 ERROR; 1 有 ERROR。
"""
import argparse, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
RE_NUM_ENTRY = re.compile(r"^\s*\[(\d+)\]\s*(.+)")
RE_TYPE = re.compile(r"\[(J|M|D|C|R|P|A|N|S|EB/OL|DB/OL|CP|OL)\]")
RE_YEAR = re.compile(r"(19|20)\d{2}")
RE_J_PATTERN = re.compile(r"(19|20)\d{2}\s*,\s*\d+\s*(\(\d+\))?\s*:\s*\d")
RE_M_PATTERN = re.compile(r"[:：]\s*[^，。,.]{2,30}(出版社|Press|Publisher|Wiley|Springer|Elsevier|Cambridge|Oxford|MIT)")
RE_ETAL = re.compile(r"等|et\s+al", re.I)

def extract_entries(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        zf = zipfile.ZipFile(path)
        doc = ET.fromstring(zf.read("word/document.xml"))
        lines = ["".join(t.text or "" for t in p.findall(".//%st" % W))
                 for p in doc.findall(".//%sp" % W)]
    else:
        lines = open(path, encoding="utf-8").read().splitlines()
    # 定位参考文献节；找不到则全文中以 [n] 开头的行
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^\s*(参考文献|References|REFERENCES)\s*$", ln.strip()) or \
           re.match(r"^#{1,3}\s*(参考文献|References)", ln.strip()):
            start = i + 1
    zone = lines[start:] if start is not None else lines
    entries, cur = [], None
    for ln in zone:
        m = RE_NUM_ENTRY.match(ln)
        if m:
            if cur:
                entries.append(cur)
            cur = {"num": int(m.group(1)), "text": m.group(2).strip()}
        elif cur is not None and ln.strip():
            cur["text"] += " " + ln.strip()
    if cur:
        entries.append(cur)
    return entries, start is not None

def check_entry(e):
    problems = []
    t = e["text"]
    if not RE_YEAR.search(t):
        problems.append({"severity": "ERROR", "code": "missing_year",
                         "detail": "未检出年份 (19xx/20xx)"})
    tm = RE_TYPE.search(t)
    if not tm:
        problems.append({"severity": "WARNING", "code": "missing_type_marker",
                         "detail": "缺文献类型标志（[J]/[M]/[D]/[EB/OL] 等）"})
        typ = None
    else:
        typ = tm.group(1)
    if typ == "J" and not RE_J_PATTERN.search(t):
        problems.append({"severity": "WARNING", "code": "journal_pattern",
                         "detail": "[J] 条目未匹配“年, 卷(期): 页码”模式"})
    if typ == "M" and not RE_M_PATTERN.search(t):
        problems.append({"severity": "WARNING", "code": "book_pattern",
                         "detail": "[M] 条目未匹配“出版地: 出版社”模式"})
    head = re.split(r"\.\s|．", t)[0]
    n_auth = len([x for x in re.split(r"[,，]\s*", head) if x.strip()])
    if n_auth > 3 and not RE_ETAL.search(t):
        problems.append({"severity": "WARNING", "code": "author_truncation",
                         "detail": "作者约 %d 名（>3）未见“等/et al.”截断" % n_auth})
    if not t.rstrip().endswith((".", "。", "．")):
        problems.append({"severity": "WARNING", "code": "missing_period",
                         "detail": "条目未以句点结尾"})
    if re.search(r"[一-鿿]", t) and re.search(r"[一-鿿]\s*,\s*[A-Za-z]", t):
        problems.append({"severity": "WARNING", "code": "mixed_punctuation",
                         "detail": "中英文标点混用嫌疑（中文语境出现半角逗号）"})
    return problems

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("doc")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        entries, found_section = extract_entries(a.doc)
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        print("ERROR: 输入不可读: %s" % e, file=sys.stderr)
        sys.exit(2)
    results = []
    n_err = 0
    for e in entries:
        probs = check_entry(e)
        n_err += sum(1 for p in probs if p["severity"] == "ERROR")
        results.append({"num": e["num"], "text": e["text"][:120], "problems": probs,
                        "verdict": "ERROR" if any(p["severity"] == "ERROR" for p in probs)
                        else ("WARN" if probs else "PASS")})
    report = {"doc": a.doc, "reference_section_found": found_section,
              "style": "GB/T 7714 数字顺序制（形式初筛）",
              "summary": {"entries": len(entries), "errors": n_err,
                          "entries_with_warnings": sum(1 for r in results if r["verdict"] == "WARN"),
                          "entries_pass": sum(1 for r in results if r["verdict"] == "PASS")},
              "results": results}
    json.dump(report, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("entries=%d ERROR=%d WARN=%d PASS=%d -> %s" % (
        len(entries), n_err, report["summary"]["entries_with_warnings"],
        report["summary"]["entries_pass"], a.out))
    sys.exit(1 if n_err else 0)

if __name__ == "__main__":
    main()
