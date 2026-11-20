#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""harvest_numbers.py — 从 pages/<doc_id>.jsonl 正则采集全部"数字声明"。

产出 numbers/<doc_id>.jsonl，每行：
  {"doc_id", "kind", "value_fields": {...}, "sentence", "page", "span": [s, e],
   "fragment": 匹配到的原文片段}

kind ∈ {freq_percent, sample_size, percent, p_value, ci, mean_sd,
        median_iqr, test_stat, effect}
仅标准库。句切分为保守近似（标点+换行），句文本保持原文 verbatim 以便回验。
"""
import argparse
import json
import os
import re
import sys

NUM = r"(\d+(?:\.\d+)?)"

PATTERNS = [
    # 31/60 (52%) —— 频数+百分比同现，优先于单独百分比
    ("freq_percent", re.compile(
        r"(\d+)\s*/\s*(\d+)\s*\(\s*" + NUM + r"\s*%\s*\)")),
    # 52% (31/60) —— 百分比在前、频数语境在后的反序形态
    ("freq_percent_rev", re.compile(
        NUM + r"\s*%\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)")),
    # n = 120 / N=120
    ("sample_size", re.compile(r"\b[nN]\s*=\s*(\d+)")),
    # p < 0.05 / p=0.032 / P ≤ 0.001
    ("p_value", re.compile(
        r"\bp\s*(≤|≥|<=|>=|<|>|=)\s*(0?\.\d+|\.\d+)", re.IGNORECASE)),
    # 95% CI: 1.1 to 2.9 / 95% CI [0.4, 0.9] / 95% CI 1.1-2.9
    ("ci", re.compile(
        r"95\s*%\s*CI\s*[:=]?\s*[\[\(]?\s*(-?\d+(?:\.\d+)?)"
        r"\s*(?:,|;|–|—|\bto\b|(?<=\d)-)\s*(-?\d+(?:\.\d+)?)\s*[\]\)]?",
        re.IGNORECASE)),
    # 12.3 ± 4.5
    ("mean_sd", re.compile(NUM + r"\s*±\s*" + NUM)),
    # median 6.5 (IQR 4.0-9.1) / median (IQR) 6.5 (4.0, 9.1)
    ("median_iqr", re.compile(
        r"[Mm]edian\s+(?:\(\s*IQR\s*\)\s+)?" + NUM +
        r"\s*\(\s*(?:IQR\s*[: ]*)?" + NUM +
        r"\s*(?:,|;|–|—|\bto\b|(?<=\d)-)\s*" + NUM + r"\s*\)")),
    # t(118) = 2.31 / χ² = 4.61 / F(2, 117)=5.02 / z = 1.96
    ("test_stat", re.compile(
        r"\b(t|z|F|χ²|chi2|chi-?square)\s*"
        r"(?:\(\s*(\d+(?:\s*,\s*\d+)?)\s*\))?\s*=\s*(-?\d+(?:\.\d+)?)",
        re.IGNORECASE)),
    # OR = 1.8 / HR=0.73 / RR = 1.21
    ("effect", re.compile(r"\b(OR|HR|RR)\s*=\s*" + NUM)),
    # 52%（排除 95% CI 中的 95% 与 freq_percent 已覆盖的）
    ("percent", re.compile(NUM + r"\s*%(?!\s*CI)")),
]

SENT_SPLIT = re.compile(r"[.!?。！？]\s+|\n+")


def sentence_spans(text):
    spans = []
    start = 0
    for m in SENT_SPLIT.finditer(text):
        end = m.end()
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    if start < len(text) and text[start:].strip():
        spans.append((start, len(text)))
    return spans


def sentence_at(spans, text, pos):
    for s, e in spans:
        if s <= pos < e:
            return text[s:e].strip(), s
    # 退化：取所在行
    s = text.rfind("\n", 0, pos) + 1
    e = text.find("\n", pos)
    if e < 0:
        e = len(text)
    return text[s:e].strip(), s


def dec_places(s):
    s = str(s)
    return len(s.split(".")[1]) if "." in s else 0


def build_value_fields(kind, m):
    g = m.groups()
    try:
        if kind == "freq_percent":
            return {"count": int(g[0]), "total": int(g[1]),
                    "percent": float(g[2]), "percent_decimals": dec_places(g[2])}
        if kind == "freq_percent_rev":
            return {"count": int(g[1]), "total": int(g[2]),
                    "percent": float(g[0]), "percent_decimals": dec_places(g[0])}
        if kind == "sample_size":
            return {"n": int(g[0])}
        if kind == "p_value":
            comp = g[0].replace("<=", "≤").replace(">=", "≥")
            return {"comparator": comp, "value": float(g[1]),
                    "decimals": dec_places(g[1])}
        if kind == "ci":
            return {"lo": float(g[0]), "hi": float(g[1])}
        if kind == "mean_sd":
            return {"mean": float(g[0]), "sd": float(g[1])}
        if kind == "median_iqr":
            return {"median": float(g[0]), "q1": float(g[1]), "q3": float(g[2])}
        if kind == "test_stat":
            name = g[0]
            name = {"χ²": "chi2", "chi-square": "chi2", "chisquare": "chi2",
                    "chi2": "chi2"}.get(name.lower(), name)
            df = None
            if g[1]:
                df = [int(x) for x in re.split(r"\s*,\s*", g[1])]
            return {"stat": name, "df": df, "value": float(g[2])}
        if kind == "effect":
            return {"measure": g[0].upper(), "value": float(g[1])}
        if kind == "percent":
            return {"percent": float(g[0]), "decimals": dec_places(g[0])}
    except (ValueError, IndexError):
        return None
    return None


def harvest_doc(doc_id, pages_path, out_path):
    n = 0
    with open(pages_path, "r", encoding="utf-8") as fin, \
            open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            page = rec.get("page")
            text = rec.get("text") or ""
            spans = sentence_spans(text)
            freq_spans = []
            for kind, pat in PATTERNS:
                for m in pat.finditer(text):
                    if kind == "percent":
                        # 跳过已被 freq_percent 覆盖的百分比
                        if any(fs <= m.start() < fe for fs, fe in freq_spans):
                            continue
                    vf = build_value_fields(kind, m)
                    if vf is None:
                        continue
                    if kind in ("freq_percent", "freq_percent_rev"):
                        freq_spans.append((m.start(), m.end()))
                    sent, _s = sentence_at(spans, text, m.start())
                    row = {
                        "doc_id": doc_id,
                        "kind": ("freq_percent" if kind == "freq_percent_rev"
                                 else kind),
                        "value_fields": vf,
                        "sentence": sent,
                        "fragment": m.group(0),
                        "page": page,
                        "span": [m.start(), m.end()],
                    }
                    fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                    n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="采集数字声明")
    ap.add_argument("--work-dir", default="/app/work")
    args = ap.parse_args()
    pages_dir = os.path.join(args.work_dir, "pages")
    out_dir = os.path.join(args.work_dir, "numbers")
    os.makedirs(out_dir, exist_ok=True)
    total = 0
    if not os.path.isdir(pages_dir):
        print(json.dumps({"error": "no pages dir", "total": 0}))
        return 0
    for fn in sorted(os.listdir(pages_dir)):
        if not fn.endswith(".jsonl"):
            continue
        doc_id = fn[:-len(".jsonl")]
        total += harvest_doc(doc_id, os.path.join(pages_dir, fn),
                             os.path.join(out_dir, doc_id + ".jsonl"))
    print(json.dumps({"numeric_claims": total}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
