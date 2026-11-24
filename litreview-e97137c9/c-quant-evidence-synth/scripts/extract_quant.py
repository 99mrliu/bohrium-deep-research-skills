#!/usr/bin/env python3
"""extract_quant.py — 数值证据候选抽取（bundle C 签名脚本 1）。

从 work/pages/<doc_id>.jsonl 逐页逐段抽取数值候选句子：
  数字+可选单位（% / ms / s / min / kg / g / cm / m …）、n=样本量、p<0.05、
  CI [..] / (..)、mean±sd、0.xx 小数。
每个候选按 vocab/metric_terms.json 标注规范化指标名（取句内距数值最近的指标词），
带 p<页>.¶<段> 定位，写 work/quant_candidates.jsonl，每行：
  {qid, doc_id, locator, sentence, value, unit, metric, context,
   kind, op, ci_low, ci_high, sd}
find_tokens() 同时被 verify_quant.py 复用，保证"抽取口径 = 门控口径"。
仅用标准库。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

NUM = r"(?:\d+(?:\.\d+)?|\.\d+)"
# 置信度百分数（如 "95% CI"）整体屏蔽，不作为数值候选
RE_CI_CONF = re.compile(r"\d+(?:\.\d+)?\s*%\s*(?:CI|confidence)", re.I)
RE_CI = re.compile(r"(?:CI|confidence interval)\s*[\[\(]?\s*(" + NUM + r")\s*[,–—-]\s*(" + NUM + r")\s*[\]\)]?", re.I)
RE_MEANSD = re.compile("(" + NUM + r")\s*±\s*(" + NUM + r")")
RE_N = re.compile(r"\bn\s*=\s*(\d[\d,]*)")
RE_P = re.compile(r"\bp\s*([<≤=])\s*(0?\.\d+)")
RE_UNIT = re.compile("(" + NUM + r")\s*(%|percent|ms|sec|min|kg|mg|cm|mm|km|s|h|g|m)(?![A-Za-z])", re.I)
RE_DEC = re.compile(r"(?<![\w.])(\d*\.\d+)(?![\w])")


def load_vocab():
    path = os.path.join(HERE, "..", "vocab", "metric_terms.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_tokens(text):
    """从任意文本中抽取数值 token。

    返回 (tokens, cis)：
      tokens: [{start,end,value,unit,kind,op,sd}]，kind ∈ value|meansd|sample_size|pvalue
      cis:    [(ci_low, ci_high, char_pos)]，区间本身已消耗、不产生独立 token
    """
    consumed = [(m.start(), m.end()) for m in RE_CI_CONF.finditer(text)]
    cis = []
    for m in RE_CI.finditer(text):
        consumed.append((m.start(), m.end()))
        cis.append((float(m.group(1)), float(m.group(2)), m.start()))
    tokens = []

    def free(pos):
        return not any(s <= pos < e for s, e in consumed)

    for m in RE_MEANSD.finditer(text):
        consumed.append((m.start(), m.end()))
        tokens.append({"start": m.start(), "end": m.end(), "value": float(m.group(1)),
                       "unit": None, "kind": "meansd", "op": None,
                       "sd": float(m.group(2)), "ci": None})
    for m in RE_N.finditer(text):
        if free(m.start(1)):
            consumed.append((m.start(), m.end()))
            tokens.append({"start": m.start(), "end": m.end(),
                           "value": float(m.group(1).replace(",", "")),
                           "unit": None, "kind": "sample_size", "op": None,
                           "sd": None, "ci": None})
    for m in RE_P.finditer(text):
        if free(m.start(2)):
            consumed.append((m.start(), m.end()))
            tokens.append({"start": m.start(), "end": m.end(), "value": float(m.group(2)),
                           "unit": None, "kind": "pvalue", "op": m.group(1),
                           "sd": None, "ci": None})
    for m in RE_UNIT.finditer(text):
        if free(m.start(1)):
            consumed.append((m.start(), m.end()))
            tokens.append({"start": m.start(), "end": m.end(), "value": float(m.group(1)),
                           "unit": m.group(2).lower(), "kind": "value", "op": None,
                           "sd": None, "ci": None})
    for m in RE_DEC.finditer(text):
        if free(m.start(1)):
            tokens.append({"start": m.start(), "end": m.end(), "value": float(m.group(1)),
                           "unit": None, "kind": "value", "op": None,
                           "sd": None, "ci": None})
    tokens.sort(key=lambda t: t["start"])
    return tokens, cis


def label_metric(sentence, char_pos, terms):
    """取句内距 char_pos 最近的指标词（最长优先匹配），返回规范化指标名或 None。"""
    low = sentence.lower()
    occ = []
    for term in sorted(terms, key=len, reverse=True):
        t = term.lower()
        start = 0
        while True:
            i = low.find(t, start)
            if i < 0:
                break
            occ.append((abs(i + len(t) / 2.0 - char_pos), terms[term]))
            start = i + 1
    return min(occ)[1] if occ else None


def split_sentences(para):
    flat = re.sub(r"\s+", " ", para).strip()
    return [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+", flat) if s.strip()]


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def run(work):
    terms = load_vocab()["terms"]
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    candidates = []
    qn = 0
    for d in docs:
        if d.get("tier") not in ("fulltext", "abstract_only"):
            continue
        doc_id = d["doc_id"]
        for row in load_jsonl(os.path.join(work, "pages", f"{doc_id}.jsonl")):
            paras = [p for p in re.split(r"\n\s*\n", row["text"]) if p.strip()]
            for pi, para in enumerate(paras, 1):
                for sent in split_sentences(para):
                    if not re.search(r"\d", sent):
                        continue
                    tokens, cis = find_tokens(sent)
                    if not tokens:
                        continue
                    # CI 区间附着到句内第一个数值型 token
                    pending_ci = cis[0] if cis else None
                    for tok in tokens:
                        qn += 1
                        cand = {
                            "qid": f"Q{qn}",
                            "doc_id": doc_id,
                            "locator": f"p{row['page']}.¶{pi}",
                            "sentence": sent,
                            "value": tok["value"],
                            "unit": tok["unit"],
                            "metric": (tok["kind"] if tok["kind"] in ("sample_size", "pvalue")
                                       else label_metric(sent, tok["start"], terms)),
                            "context": para.strip()[:300],
                            "kind": tok["kind"],
                            "op": tok["op"],
                            "ci_low": None, "ci_high": None, "sd": tok["sd"],
                        }
                        if pending_ci and tok["kind"] in ("value", "meansd"):
                            cand["ci_low"], cand["ci_high"] = pending_ci[0], pending_ci[1]
                            pending_ci = None
                        candidates.append(cand)
    out_path = os.path.join(work, "quant_candidates.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return candidates


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)
    cands = run(args.work)
    by_metric = {}
    for c in cands:
        by_metric[str(c["metric"])] = by_metric.get(str(c["metric"]), 0) + 1
    print(json.dumps({"candidates": len(cands), "by_metric": by_metric}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
