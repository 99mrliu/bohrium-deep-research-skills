#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgcommon.py — 共享工具函数（仅 Python 3 标准库）。

本模块被 bundle 内其他脚本 import，提供：
- 确定性 JSON 读写（UTF-8、排序键、缩进 2、末尾换行）；
- 语料段落索引；
- SHA-256 摘要（用于溯源台账）。

所有输出必须确定性：同一输入产生逐字节相同的输出。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FORMAT_NORMALIZED_CORPUS = "normalized-corpus/1"
FORMAT_GRAPH = "provenance-kg/1"
FORMAT_QUERIES = "provenance-kg-queries/1"

# 引文长度上限（字符）。规则要求“短引文”，超长视为违规。
MAX_QUOTE_CHARS = 300


def read_json(path):
    """读取 UTF-8 JSON 文件，返回 Python 对象。"""
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj):
    """确定性写出 JSON：UTF-8、ensure_ascii=False、sort_keys=True、indent=2。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    p.write_text(text, encoding="utf-8")


def write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_paragraph_index(corpus):
    """从归一化语料构造索引。

    返回 (sources, para_index)：
    - sources: {source_id: source 对象}
    - para_index: {(source_id, paragraph_id): paragraph 对象}
    """
    sources = {}
    para_index = {}
    for src in corpus.get("sources", []):
        sid = src.get("source_id")
        sources[sid] = src
        for para in src.get("paragraphs", []):
            para_index[(sid, para.get("id"))] = para
    return sources, para_index


def duplicate_id_set(corpus):
    """返回 {source_id: set(重复 paragraph_id)}。"""
    dup = {}
    for sid, ids in (corpus.get("duplicate_paragraph_ids") or {}).items():
        dup[sid] = set(ids)
    return dup


def evidence_source_ids(evidence_list):
    """返回证据列表中排序去重后的 source_id 列表。"""
    return sorted({ev.get("source_id") for ev in evidence_list or [] if ev.get("source_id")})


def norm_label(label):
    """标签归一化（用于同名节点机械检测）：去首尾空白、折叠内部空白、小写。"""
    return " ".join(str(label or "").split()).casefold()
