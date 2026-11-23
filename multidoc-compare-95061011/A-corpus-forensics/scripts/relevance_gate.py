#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
relevance_gate.py — 相关性门控（relevance gating），自包含脚本。

读取 build_registry.py 产出的 registry.json（及其段落 jsonl），再读取
comparison-workorder.json（对未知 schema 健壮：递归提取其中的字符串作为维度词，
跳过 case_id/路径类字段，另加内置常见维度词表），对每篇注册文档打分：
  score = 命中的 distinct 维度词数；score >= 2 -> in_scope，否则 out_of_scope。

out_of_scope 的文档保留记录但不得进入比较矩阵（verify_anchors.py 会机检拦截）。

用法：
  python3 relevance_gate.py --registry <dir-or-registry.json> \
      [--workorder comparison-workorder.json] --out relevance.json
不带 --workorder 时全部记 in_scope 并注明 no_workorder。
退出码：0 正常；1 用法或 IO 错误。
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata

# 内置常见维度词（光催化/环境化学工单高频词），与工单提取词合并使用
BUILTIN_TERMS = [
    "photocatalysis", "photocatalytic", "photocatalyst", "degradation", "decolorization",
    "dye", "rhodamine", "methylene blue", "pollutant", "wastewater",
    "removal", "adsorption", "kinetics", "rate constant", "irradiation",
    "visible light", "catalyst", "catalyst dosage", "g-c3n4", "tio2",
    "reaction time", "initial concentration", "removal efficiency",
]
SCORE_THRESHOLD = 2
# 递归提取工单时跳过的键（身份/路径类字段不是维度词）
SKIP_KEYS = {"case_id", "id", "documents", "document", "files", "file", "paths", "path",
             "corpus", "corpus_dir", "urls", "url", "output_contract", "schema"}
STOPWORDS = {"the", "and", "for", "with", "from", "this", "that", "are", "was", "were",
             "all", "any", "each", "per", "min", "json", "com", "https", "http", "org",
             # 元词（描述工单/语料本身而非学科维度），不作为相关性证据
             "synthetic", "example", "paper", "papers", "corpus", "study", "reported",
             "compare", "comparison", "source", "full", "sample", "demonstration",
             "time", "data", "results", "values", "work", "using", "based"}


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^0-9a-z一-鿿]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_term(term):
    return normalize_text(term)


def looks_like_id_or_path(raw):
    if "/" in raw or "\\" in raw:
        return True
    if re.search(r"\d{4}", raw):               # 含 4 位以上数字（年份/编号）
        return True
    if re.fullmatch(r"[A-Z0-9][A-Z0-9\-_]{4,}", raw):  # SYNTH-EXAMPLE-001 这类编号
        return True
    return False


def extract_terms(obj, terms):
    """递归提取工单字符串中的维度词：整串(<=4词)作为短语 + 单词(>=3字符)。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in SKIP_KEYS:
                continue
            extract_terms(v, terms)
    elif isinstance(obj, list):
        for v in obj:
            extract_terms(v, terms)
    elif isinstance(obj, str):
        raw = obj.strip()
        if len(raw) < 3 or looks_like_id_or_path(raw):
            return
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", raw)
        if 1 <= len(words) <= 4:
            phrase = norm_term(raw)
            if phrase and len(phrase) >= 3:
                terms.add(phrase)
        for w in words:
            wl = w.lower()
            if len(wl) >= 3 and wl not in STOPWORDS and not wl.isdigit():
                terms.add(norm_term(wl))


def term_in_text(term, norm_text):
    if not term:
        return False
    return re.search(r"(?<![0-9a-z])" + re.escape(term) + r"(?![0-9a-z])", norm_text) is not None


def load_doc_text(registry_dir, doc):
    pf = os.path.join(registry_dir, doc.get("paragraphs_file", ""))
    if pf and os.path.isfile(pf):
        parts = []
        with open(pf, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        parts.append(json.loads(line).get("text", ""))
                    except json.JSONDecodeError:
                        pass
        return "\n\n".join(parts)
    # 退化：直接读原文
    ap = doc.get("abs_path")
    if ap and os.path.isfile(ap) and not ap.lower().endswith(".pdf"):
        with open(ap, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="相关性门控：对注册文档打 in_scope / out_of_scope")
    ap.add_argument("--registry", required=True, help="registry.json 或其所在目录")
    ap.add_argument("--workorder", default=None, help="comparison-workorder.json（可选）")
    ap.add_argument("--out", required=True, help="输出 relevance.json 路径")
    ap.add_argument("--threshold", type=int, default=SCORE_THRESHOLD,
                    help="in_scope 所需 distinct 命中词数（默认 2）")
    args = ap.parse_args(argv)

    reg_path = args.registry
    if os.path.isdir(reg_path):
        reg_path = os.path.join(reg_path, "registry.json")
    with open(reg_path, "r", encoding="utf-8") as f:
        registry = json.load(f)
    registry_dir = os.path.dirname(os.path.abspath(reg_path))

    terms = set(norm_term(t) for t in BUILTIN_TERMS)
    workorder_note = "no_workorder"
    if args.workorder:
        if not os.path.isfile(args.workorder):
            print("error: workorder not found: %s" % args.workorder, file=sys.stderr)
            return 1
        with open(args.workorder, "r", encoding="utf-8") as f:
            workorder = json.load(f)
        extract_terms(workorder, terms)
        workorder_note = "loaded:%s" % os.path.basename(args.workorder)
    terms.discard("")

    results = []
    for doc in registry.get("documents", []):
        text = load_doc_text(registry_dir, doc)
        norm_text = normalize_text(text)
        hits = sorted(t for t in terms if term_in_text(t, norm_text))
        score = len(hits)
        verdict = "in_scope" if score >= args.threshold else "out_of_scope"
        if not args.workorder:
            verdict = "in_scope"
        results.append({
            "doc_id": doc["doc_id"],
            "verdict": verdict,
            "score": score,
            "threshold": args.threshold,
            "hits": hits,
            "evidence": ("%d distinct dimension terms matched" % score) if hits
                        else "no dimension terms matched",
        })
        print("[relevance] %-12s %-12s score=%-3d hits=%s"
              % (doc["doc_id"], verdict, score, ",".join(hits[:6])), file=sys.stderr)

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "workorder": workorder_note,
        "n_terms": len(terms),
        "score_threshold": args.threshold,
        "documents": results,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("relevance written to %s" % args.out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
