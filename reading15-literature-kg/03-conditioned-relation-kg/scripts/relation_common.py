#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conditioned-relation-kg 共享库（仅 Python3 标准库）。

提供：受控关系词表、作者声音枚举、JSON 读写、鲁棒引文精确匹配、
语料（material.json 索引 + primary/secondary-material.json）加载。
所有脚本共享本模块，保证判定规则一致、可复算。
"""
import json
import os
import re
import unicodedata

# ---- 受控词汇（允许案例任务通过 relations.json 的 "extensions" 扩展）----
BASE_VOCAB = {
    "uses",            # 使用（样本/方法/数据集/工具）
    "evaluates",       # 评估（在某任务/数据集上评估对象）
    "reports",         # 报告（报告某事实或测量，非比较）
    "derives_from",    # 派生自（蒸馏/微调/改造自某对象）
    "compares_with",   # 与……比较（未给方向性结论）
    "outperforms",     # 优于（有方向、必须带指标/依据与比较对象）
    "supports",        # 支持（证据支持某说法/结论）
    "contradicts",     # 矛盾（证据与某说法冲突）
    "measured_on",     # 在……上测得（数值测量，须带单位与条件）
    "cites_background",  # 背景转述（引用他人结果，非本文一手证据）
}
COMPARATIVE = {"outperforms", "compares_with"}          # 比较型关系
MEASURING = {"measured_on", "reports", "outperforms"}   # 可携带 measurement
VOICES = {"primary-results", "cited-background", "interpretation", "hypothesis"}
POLARITY = {"positive", "negative", "neutral"}
SCOPE_KEYS = ("sample", "model_config", "dataset", "metric", "condition", "task")

EDGE_REQUIRED = ["edge_id", "relation", "subject", "object", "voice", "evidence"]
EVIDENCE_REQUIRED = ["source_id", "paragraph_id", "quote"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


def normalize_text(s):
    """引文匹配前的鲁棒归一化：NFKC、弯引号/破折号直化、折叠空白。"""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
                 ("–", "-"), ("—", "-"), ("−", "-"), (" ", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def quote_matches(paragraph_text, quote):
    """引文必须在归一化后的段落原文中逐字出现（子串匹配）。"""
    pt = normalize_text(paragraph_text)
    q = normalize_text(quote)
    return bool(q) and q in pt


def load_corpus(input_dir):
    """按 material.json 索引加载各 source 的 {paragraph_id: text}。

    返回 (corpus, manifest_index)。corpus[source_id][paragraph_id] = 段落原文。
    根元数据（doi/title/authors）只属于第一篇，语料加载不传播根元数据。
    """
    corpus = {}
    index = {"materials": []}
    mat_path = os.path.join(input_dir, "material.json")
    if os.path.exists(mat_path):
        index = load_json(mat_path)
        entries = index.get("materials", [])
    else:  # 兜底：约定文件名
        entries = []
        for fname, role in (("primary-material.json", "primary"),
                            ("secondary-material.json", "secondary")):
            if os.path.exists(os.path.join(input_dir, fname)):
                entries.append({"source_id": None, "role": role, "file": fname})
    for ent in entries:
        fpath = os.path.join(input_dir, ent.get("file", ""))
        if not os.path.exists(fpath):
            continue
        doc = load_json(fpath)
        sid = ent.get("source_id") or doc.get("source_id") or ent.get("file")
        corpus.setdefault(sid, {})
        for para in doc.get("paragraphs", []):
            pid = para.get("paragraph_id")
            if pid:
                corpus[sid][pid] = para.get("text", "")
    return corpus, index


def condition_signature(conditions):
    """条件作用域的稳定签名，用于冲突检测分组。"""
    if not conditions:
        return ""
    items = sorted((k, str(v)) for k, v in conditions.items() if v not in (None, ""))
    return "|".join("%s=%s" % kv for kv in items)


def vocab_with_extensions(relations_doc):
    ext = set(relations_doc.get("extensions", []) or [])
    return BASE_VOCAB | ext
