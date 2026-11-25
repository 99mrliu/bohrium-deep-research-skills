#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""relevance-evidence-triage / common.py

公共工具（仅 Python3 标准库，完全离线）：
- 定位并加载 case.json 与材料快照目录（含 find 兜底）；
- 将 Crossref / Europe PMC / arXiv 三种快照布局归一化为统一题录；
- JSON / JSONL IO、日期解析、标题规范化、句子边界切分等基础函数。

统一题录结构（canonical record）：
{
  "record_id": "crossref:10.0000/...",   # 来源前缀 + 原生标识
  "source": "crossref|europepmc|arxiv",
  "native_id": "...",
  "title": "...",                        # 原文，逐字
  "abstract": "..." 或 None,             # 原文，逐字；缺失为 None
  "language": "en" | "unknown" | ...,
  "pub_date": "YYYY-MM-DD" 或 None,
  "doc_type": "journal-article" | ...,
  "authors": [...], "doi": ..., "url": ...,
  "snapshot_file": "crossref_works.json" # 可追溯：出自哪个快照
}
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# JSON / JSONL IO
# ---------------------------------------------------------------------------

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")


# ---------------------------------------------------------------------------
# case.json 与目录定位（find 兜底）
# ---------------------------------------------------------------------------

def load_case(case_path):
    case = read_json(case_path)
    case["_case_dir"] = os.path.dirname(os.path.abspath(case_path))
    return case


def resolve_dir(case, key, default_rel):
    """把 case.json 里的相对目录解析为绝对路径（相对 case.json 所在目录）。"""
    val = case.get(key) or default_rel
    if os.path.isabs(val):
        return val
    return os.path.normpath(os.path.join(case["_case_dir"], val))


def _dir_has_snapshots(d):
    try:
        names = os.listdir(d)
    except OSError:
        return False
    return any(n.lower().endswith(".json") for n in names)


def find_materials_dir(case):
    """材料目录定位：1) case.materials_dir；2) case 同级 materials/；
    3) 自 case 目录向上两层、以及 /input、/app/input 下 walk 查找含 .json 的目录。
    找不到时抛异常并说明搜索过的路径。"""
    searched = []
    cand = resolve_dir(case, "materials_dir", "materials")
    searched.append(cand)
    if os.path.isdir(cand) and _dir_has_snapshots(cand):
        return cand

    roots = [case["_case_dir"], os.path.dirname(case["_case_dir"]),
             "/input", "/app/input", "/app"]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if not x.startswith(".")]
            depth = dirpath[len(root):].count(os.sep)
            if depth > 4:
                dirnames[:] = []
                continue
            base = os.path.basename(dirpath).lower()
            if base in ("materials", "snapshots", "data") and \
                    any(fn.lower().endswith(".json") for fn in filenames):
                searched.append(dirpath)
                return dirpath
    raise FileNotFoundError(
        "未找到材料目录，已搜索: " + "; ".join(searched))


# ---------------------------------------------------------------------------
# 多源快照布局归一化
# ---------------------------------------------------------------------------

_JATS_RE = re.compile(r"<[^>]+>")


def _strip_markup(text):
    """去掉简单标记（如 JATS 标签）。注意：若快照含标记，偏移以归一化文本为准，
    需在 result 的 evidence_policy.normalization 中如实说明。"""
    if text is None:
        return None
    if "<" in text and ">" in text:
        return _JATS_RE.sub("", text).strip()
    return text


def _crossref_date(item):
    for key in ("published", "published-print", "published-online", "issued"):
        dp = (item.get(key) or {}).get("date-parts")
        if dp and dp[0]:
            parts = dp[0] + [1, 1]
            try:
                return "%04d-%02d-%02d" % (parts[0], parts[1], parts[2])
            except (TypeError, ValueError):
                return None
    return None


def _norm_crossref(item, snap):
    doi = item.get("DOI") or item.get("DOI".lower()) or "unknown"
    titles = item.get("title") or []
    title = " ".join(titles).strip() if titles else ""
    authors = []
    for a in item.get("author") or []:
        name = " ".join(x for x in [a.get("given"), a.get("family")] if x)
        if name:
            authors.append(name)
    return {
        "record_id": "crossref:" + str(doi),
        "source": "crossref",
        "native_id": str(doi),
        "title": title,
        "abstract": _strip_markup(item.get("abstract")),
        "language": item.get("language") or "unknown",
        "pub_date": _crossref_date(item),
        "doc_type": item.get("type") or "unknown",
        "authors": authors,
        "doi": str(doi),
        "url": item.get("URL"),
        "snapshot_file": snap,
    }


def _norm_europepmc(r, snap):
    rid = r.get("id") or r.get("pmid") or "unknown"
    pub_types = ((r.get("pubTypeList") or {}).get("pubType")) or []
    doc_type = pub_types[0] if pub_types else (r.get("pubType") or "journal-article")
    pub_date = r.get("firstPublicationDate") or (
        (r.get("pubYear") or "") + "-01-01" if r.get("pubYear") else None)
    if pub_date and len(pub_date) == 4:
        pub_date += "-01-01"
    journal = ((r.get("journalInfo") or {}).get("journal") or {}).get("title")
    authors = [a.strip() for a in (r.get("authorString") or "").split(",") if a.strip()]
    return {
        "record_id": "europepmc:" + str(rid),
        "source": "europepmc",
        "native_id": str(rid),
        "title": (r.get("title") or "").strip(),
        "abstract": _strip_markup(r.get("abstractText")),
        "language": r.get("language") or "unknown",
        "pub_date": pub_date or None,
        "doc_type": doc_type,
        "authors": authors,
        "doi": r.get("doi"),
        "url": ("https://europepmc.org/article/" + str(r.get("source", "MED")) + "/"
                + str(rid)) if rid != "unknown" else None,
        "journal": journal,
        "snapshot_file": snap,
    }


def _norm_arxiv(e, snap):
    rid = e.get("id") or "unknown"
    published = e.get("published") or ""
    pub_date = published[:10] if len(published) >= 10 else (published or None)
    authors = e.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    return {
        "record_id": "arxiv:" + str(rid),
        "source": "arxiv",
        "native_id": str(rid),
        "title": re.sub(r"\s+", " ", (e.get("title") or "")).strip(),
        "abstract": _strip_markup(e.get("summary")),
        "language": e.get("language") or "unknown",
        "pub_date": pub_date,
        "doc_type": e.get("doc_type") or "preprint",
        "authors": authors,
        "doi": e.get("doi"),
        "url": e.get("url") or ("https://arxiv.org/abs/" + str(rid)
                                if rid != "unknown" else None),
        "snapshot_file": snap,
    }


def sniff_and_normalize(path):
    """按文件名 / 内容嗅探快照来源，返回归一化题录列表。"""
    obj = read_json(path)
    fname = os.path.basename(path).lower()
    records = []
    if "crossref" in fname or (isinstance(obj, dict)
                               and obj.get("message-type") == "work-list"):
        items = (obj.get("message") or {}).get("items") or []
        records = [_norm_crossref(it, os.path.basename(path)) for it in items]
    elif "europepmc" in fname or (isinstance(obj, dict) and "resultList" in obj):
        items = (obj.get("resultList") or {}).get("result") or []
        records = [_norm_europepmc(it, os.path.basename(path)) for it in items]
    elif "arxiv" in fname or (isinstance(obj, dict) and "entries" in obj):
        items = obj.get("entries") or []
        records = [_norm_arxiv(it, os.path.basename(path)) for it in items]
    else:
        raise ValueError("无法识别的快照布局: " + path)
    return records


def load_materials(materials_dir):
    """加载目录下全部快照，返回 (records, index_by_id, files)。"""
    records, files = [], []
    for name in sorted(os.listdir(materials_dir)):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(materials_dir, name)
        try:
            recs = sniff_and_normalize(path)
        except ValueError:
            continue  # 非快照文件（如说明文件）跳过
        records.extend(recs)
        files.append(name)
    index = {r["record_id"]: r for r in records}
    return records, index, files


# ---------------------------------------------------------------------------
# 文本工具：日期、标题规范化、句子边界
# ---------------------------------------------------------------------------

def date_in_window(pub_date, start, end):
    """pub_date 'YYYY-MM-DD' 是否落在 [start, end]（含端点）。
    日期缺失返回 None（由调用方决定诚实处理）。"""
    if not pub_date:
        return None
    return (start or "0000-00-00") <= pub_date <= (end or "9999-99-99")


def norm_title(title):
    """标题规范化（仅用于同标题重复检测）：小写、去变音、去非字母数字。"""
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9]+", " ", t.lower())
    return t.strip()


_SENT_END = re.compile(r"[.!?](?=\s|$)")


def sentence_span(text, mstart, mend):
    """给定匹配区间 [mstart, mend)，向外扩展到所在句子的边界。
    返回 (start, end)，保证 text[start:end] 为原文逐字子串。"""
    n = len(text)
    start = 0
    for m in _SENT_END.finditer(text, 0, mstart):
        start = m.end()
        while start < n and text[start] in " \t\n":
            start += 1
    end = n
    m2 = _SENT_END.search(text, mend)
    if m2:
        end = m2.start() + 1
    return start, end


def die(msg, code=2):
    sys.stderr.write("ERROR: %s\n" % msg)
    sys.exit(code)
