#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rules_spec.py -- 从任务说明/投稿须知等文字材料中抽取格式规则（带行号溯源）。

只抽取文本中明确写出的规则（status=stated），命中行原文进 quote。
识别不出的要求不猜——留给 Agent 阅读原文后在 spec.json 手工补项（status=assumed，
必须在 result.json 的 uncertainties 声明）。纯标准库。

用法:
  python3 rules_spec.py RULES.txt --out rules_spec.json
  pdftotext guide.pdf - | python3 rules_spec.py - --out rules_spec.json
"""
import argparse, hashlib, json, re, sys

# 中文字号 -> pt（识别辅助表，见 references/spec-schema.md；案件明示值优先）
CN_SIZE = {"初号": 42, "小初": 36, "一号": 26, "小一": 24, "二号": 22, "小二": 18,
           "三号": 16, "小三": 15, "四号": 14, "小四": 12, "五号": 10.5,
           "小五": 9, "六号": 7.5, "小六": 6.5}

def it(item_id, cat, prop, val, unit, line_no, line):
    return {"id": item_id, "category": cat, "property": prop, "value": val,
            "unit": unit, "status": "stated",
            "source": {"file": None, "pointer": "line %d" % line_no,
                       "quote": line.strip()[:120]}}

def scan(text):
    items = []
    lines = text.splitlines()
    for i, ln in enumerate(lines, 1):
        # 页边距：上 3.17 cm / 上下2.54厘米 / margin: 1 inch
        for m in re.finditer(r"(上|下|左|右)\s*(?:边距|页边距)?\s*[:：为]?\s*(\d+(?:\.\d+)?)\s*(cm|厘米|mm|毫米|in|inch|英寸)", ln):
            side = {"上": "top", "下": "bottom", "左": "left", "右": "right"}[m.group(1)]
            v, u = float(m.group(2)), m.group(3)
            cm = v if u in ("cm", "厘米") else (v / 10.0 if u in ("mm", "毫米") else round(v * 2.54, 3))
            items.append(it("page.margin.%s" % side, "page", "margin_%s" % side, cm, "cm", i, ln))
        m = re.search(r"(?:上下|top(?:/bottom)?)\s*(?:边距|margins?)?\s*[:：为]?\s*(\d+(?:\.\d+)?)\s*(cm|厘米|mm|in|inch)", ln, re.I)
        if m and not any(x["id"].endswith(".top") and x["source"]["pointer"] == "line %d" % i for x in items):
            cm = float(m.group(1)) if m.group(2) in ("cm", "厘米") else (float(m.group(1)) / 10 if m.group(2) == "mm" else round(float(m.group(1)) * 2.54, 3))
            items.append(it("page.margin.top", "page", "margin_top", cm, "cm", i, ln))
            items.append(it("page.margin.bottom", "page", "margin_bottom", cm, "cm", i, ln))
        # 栏数
        if re.search(r"双栏|两栏|two[- ]column|double[- ]column", ln, re.I):
            items.append(it("page.columns", "page", "columns", 2, "栏", i, ln))
        elif re.search(r"单栏|one[- ]column|single[- ]column", ln, re.I):
            items.append(it("page.columns", "page", "columns", 1, "栏", i, ln))
        # 行距
        m = re.search(r"行距\s*[:：为]?\s*(\d+(?:\.\d+)?)\s*倍", ln)
        if m:
            items.append(it("text.line_spacing", "text", "line_spacing", float(m.group(1)), "倍", i, ln))
        m = re.search(r"(?:line[- ]spacing|leading)\s*[:：]?\s*(single|double|1\.5|one[- ]and[- ]a[- ]half)", ln, re.I)
        if m:
            v = {"single": 1.0, "double": 2.0, "1.5": 1.5, "one-and-a-half": 1.5}.get(m.group(1).lower(), 1.5)
            items.append(it("text.line_spacing", "text", "line_spacing", v, "倍", i, ln))
        m = re.search(r"行距\s*[:：为]?\s*(?:固定值)?\s*(\d+(?:\.\d+)?)\s*(?:磅|pt)", ln)
        if m:
            items.append(it("text.line_spacing", "text", "line_spacing", float(m.group(1)), "pt(exact)", i, ln))
        # 字号：正文小四 / 标题三号 / 12 pt
        for m in re.finditer(r"(正文|标题|一级标题|二级标题|摘要|关键词|参考文献|图注|表注|题注|脚注)\s*[^，。；;]{0,8}?(" + "|".join(CN_SIZE) + r")(?:\s*字)?", ln):
            scope, cn = m.group(1), m.group(2)
            items.append(it("text.%s.size" % scope, "text", "%s.size" % scope, CN_SIZE[cn], "pt", i, ln))
        for m in re.finditer(r"(正文|标题|摘要|参考文献|图注|表注|题注|body|heading|title|abstract|references?|caption)\s*[^，。；;.]{0,10}?(\d+(?:\.\d+)?)\s*(?:pt|磅|point)", ln, re.I):
            items.append(it("text.%s.size" % m.group(1), "text", "%s.size" % m.group(1), float(m.group(2)), "pt", i, ln))
        # 字体
        m = re.search(r"(?:英文|西文)?\s*字体\s*[:：为]?\s*(Times New Roman|Liberation Serif|Arial|宋体|黑体|仿宋|楷体)", ln, re.I)
        if m:
            items.append(it("text.font", "text", "font", m.group(1), "", i, ln))
        # 参考文献标准
        if re.search(r"GB/?T?\s*7714", ln):
            items.append(it("refs.standard", "refs", "reference_standard", "GB/T 7714", "", i, ln))
        m = re.search(r"(APA|Vancouver|IEEE|Chicago|Harvard)\s*(?:格式|样式|style)?", ln, re.I)
        if m and "参考文献" in ln or (m and re.search(r"reference|citation", ln, re.I)):
            items.append(it("refs.standard", "refs", "reference_standard", m.group(1), "", i, ln))
        # 题注位置
        if re.search(r"图.{0,6}(?:题注|标题|caption).{0,4}(?:下方|置于下|below)", ln, re.I):
            items.append(it("caption.figure.position", "caption", "figure_caption_position", "below", "", i, ln))
        if re.search(r"表.{0,6}(?:题注|标题|caption).{0,4}(?:上方|置于上|above)", ln, re.I):
            items.append(it("caption.table.position", "caption", "table_caption_position", "above", "", i, ln))
    # 正文级规则同时落到 OOXML 默认样式 style.Normal.*，以便与模板实测项冲突裁决
    alias = []
    for x in items:
        if x["id"] == "text.line_spacing":
            y = dict(x); y["id"] = "style.Normal.line_spacing"; y["property"] = "Normal.line_spacing"; alias.append(y)
        if x["id"] == "text.正文.size":
            y = dict(x); y["id"] = "style.Normal.size"; y["property"] = "Normal.size"; alias.append(y)
    items.extend(alias)
    # 去重（同 id 同值同行只留一条）
    seen, uniq = set(), []
    for x in items:
        k = (x["id"], json.dumps(x["value"], ensure_ascii=False), x["source"]["pointer"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rules", help="规则文本路径，'-' 表示标准输入")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.rules == "-":
        text, name = sys.stdin.read(), "<stdin>"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    else:
        with open(a.rules, "rb") as f:
            raw = f.read()
        digest = hashlib.sha256(raw).hexdigest()
        text, name = raw.decode("utf-8", errors="replace"), a.rules
    items = scan(text)
    for x in items:
        x["source"]["file"] = name
    spec = {"spec_version": "1.0", "generator": "rules_spec.py",
            "sources": [{"file": name, "sha256": digest, "kind": "prose-rules"}],
            "items": items}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    print("stated rules: %d -> %s" % (len(items), a.out))

if __name__ == "__main__":
    main()
