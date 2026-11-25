#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""identity_merge.py — 跨库语料解析 + 论文身份合并（Identity Reconciliation Court 第一步）。

功能：
  1. 递归扫描候选根，解析 Crossref / EuropePMC / OpenAlex / 通用 JSON / JSONL /
     CSV / TSV / 简易 BibTeX 语料，每条记录带 locator {file, pointer}；
  2. blocking（DOI 精确块 / 标题规范化前 40 字符块 / 第一作者姓+年份块）；
  3. 块内成对打分（标题 token、作者重叠、年份差、venue、DOI 前缀类型）；
  4. 阈值裁决：>=0.85 合并；0.6-0.85 存疑写入 review_queue；<0.6 不合并；
  5. 版本谱系分类（preprint/conference/journal/supplement）；
  6. 识别 distinct_same_title（同名不同文）与 same_work_different_title（同文不同名）；
  7. 合并组选代表记录，冲突字段保留在 merge_evidence；
  8. 输出 <workdir>/entities.jsonl 与 <workdir>/merge_ledger.json。

仅使用 Python 标准库；默认离线；脚本位置无关（pathlib）。
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

MERGE_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.60

STOPWORDS = {
    "a", "an", "the", "of", "for", "on", "in", "and", "or", "to", "with",
    "by", "via", "from", "at", "as", "is", "are", "using", "use", "its",
}

RECORD_EXTS = {".json", ".jsonl", ".csv", ".tsv", ".bib"}
SKIP_EXTS = {".edgelist"}  # 边表由 run_case.py 处理；此处登记来源但不产出记录

PREPRINT_DOI_PREFIXES = ("10.48550", "10.1101", "10.2139", "10.31234", "10.26434")
PREPRINT_VENUE_HINTS = ("arxiv", "biorxiv", "medrxiv", "ssrn", "preprint", "chemrxiv", "osf")
CONFERENCE_HINTS = ("proceedings", "proc.", "conference", "workshop", "symposium", "conf.")
SUPPLEMENT_HINTS = ("supplement", "supplementary", "appendix", "supporting information")


# ---------------------------------------------------------------- 规范化

def norm_doi(raw):
    """DOI 规范化：小写、去 URL/doi: 前缀、去首尾空白与尾部标点。"""
    if not raw:
        return None
    s = str(raw).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                   "http://dx.doi.org/", "doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    s = s.strip().rstrip(".;,)")
    return s or None


def norm_title(raw):
    """标题规范化：NFKC、小写、去标点、坍缩空白。"""
    if not raw:
        return None
    s = unicodedata.normalize("NFKC", str(raw)).lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def title_tokens(norm):
    if not norm:
        return frozenset()
    return frozenset(t for t in norm.split() if t not in STOPWORDS)


def surname_of(author):
    """从多种作者表示中提取姓（小写）。"""
    if isinstance(author, dict):
        fam = author.get("family") or author.get("family_name") or author.get("surname")
        if fam:
            return str(fam).strip().lower()
        name = author.get("name") or author.get("display_name") or ""
    else:
        name = str(author or "")
    name = name.strip()
    if not name:
        return None
    if "," in name:  # "Last, First"
        return name.split(",", 1)[0].strip().lower()
    return name.split()[-1].strip().lower() if name.split() else None


def uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x is None or x == "" or x == []:
            continue
        key = json.dumps(x, sort_keys=True, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x)
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


# ---------------------------------------------------------------- 语料解析

def _as_list(x):
    return x if isinstance(x, list) else ([x] if x else [])


def _mk_record(rec_id, doi, title, authors, year, venue, pub_type,
               references, citations, relations, fmt, file, pointer):
    return {
        "rec_id": rec_id,
        "doi": norm_doi(doi),
        "title": (str(title).strip() if title else None),
        "title_norm": norm_title(title),
        "authors": [str(a).strip() if not isinstance(a, dict)
                    else (a.get("name") or " ".join(filter(None, [a.get("given"), a.get("family")]))
                          or a.get("display_name") or "").strip()
                    for a in _as_list(authors)],
        "author_surnames": sorted({s for s in (surname_of(a) for a in _as_list(authors)) if s}),
        "year": int(year) if str(year or "").strip().isdigit() else None,
        "venue": (str(venue).strip() if venue else None),
        "pub_type": (str(pub_type).strip().lower() if pub_type else None),
        "references": _as_list(references),
        "citations": _as_list(citations),
        "relations": relations or {},
        "format": fmt,
        "source": {"file": str(file), "pointer": pointer},
    }


def parse_crossref_message(msg, fmt, file, base_pointer, counter):
    """Crossref：message.items 或单条 message。"""
    records = []
    items = msg.get("items") if isinstance(msg.get("items"), list) else [msg]
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        pointer = f"{base_pointer}.items[{i}]" if "items" in msg else base_pointer
        container = it.get("container-title")
        venue = container[0] if isinstance(container, list) and container else it.get("publisher")
        year = None
        for key in ("issued", "published-print", "published-online", "published"):
            parts = (it.get(key) or {}).get("date-parts")
            if parts and parts[0] and parts[0][0]:
                year = parts[0][0]
                break
        refs = []
        for r in _as_list(it.get("reference")):
            if isinstance(r, dict):
                refs.append(norm_doi(r.get("DOI")) or r.get("unstructured") or r.get("article-title"))
            else:
                refs.append(r)
        records.append(_mk_record(
            counter(), it.get("DOI"), (it.get("title") or [None])[0] if isinstance(it.get("title"), list) else it.get("title"),
            it.get("author"), year, venue, it.get("type"), refs, [],
            it.get("relation"), fmt, file, pointer))
    return records


def parse_europepmc_result(res, fmt, file, base_pointer, counter):
    records = []
    for i, it in enumerate(res):
        if not isinstance(it, dict):
            continue
        pointer = f"{base_pointer}[{i}]"
        authors = it.get("authorList", {}).get("author") if isinstance(it.get("authorList"), dict) else None
        if authors is None and it.get("authorString"):
            authors = [a.strip() for a in str(it["authorString"]).rstrip(".").split(",")]
        refs = []
        for r in _as_list(it.get("referenceList", {}).get("reference") if isinstance(it.get("referenceList"), dict) else it.get("references")):
            if isinstance(r, dict):
                refs.append(norm_doi(r.get("doi")) or r.get("title") or r.get("citation"))
            else:
                refs.append(r)
        cited = []
        for c in _as_list(it.get("citedByList", {}).get("citedBy") if isinstance(it.get("citedByList"), dict) else []):
            if isinstance(c, dict):
                cited.append(norm_doi(c.get("doi")) or c.get("title"))
            else:
                cited.append(c)
        records.append(_mk_record(
            counter(), it.get("doi"), it.get("title"), authors, it.get("pubYear"),
            it.get("journalTitle") or (it.get("journalInfo", {}) or {}).get("journal", {}).get("title")
            if isinstance(it.get("journalInfo"), dict) else it.get("journalTitle"),
            it.get("pubType"), refs, cited, {}, fmt, file, pointer))
    return records


def parse_openalex_results(res, fmt, file, base_pointer, counter):
    records = []
    for i, it in enumerate(res):
        if not isinstance(it, dict):
            continue
        pointer = f"{base_pointer}[{i}]"
        authors = []
        for a in _as_list(it.get("authorships")):
            if isinstance(a, dict):
                nm = (a.get("author") or {}).get("display_name")
                if nm:
                    authors.append(nm)
        venue = None
        loc = it.get("primary_location") or {}
        if isinstance(loc, dict) and isinstance(loc.get("source"), dict):
            venue = loc["source"].get("display_name")
        refs = [norm_doi(r) or r for r in _as_list(it.get("referenced_works"))]
        records.append(_mk_record(
            counter(), it.get("doi") or it.get("id"), it.get("title") or it.get("display_name"),
            authors or it.get("authors"), it.get("publication_year"), venue,
            it.get("type"), refs, _as_list(it.get("cited_by")), {},
            fmt, file, pointer))
    return records


def parse_generic_record(it, fmt, file, pointer, counter):
    if not isinstance(it, dict):
        return None
    doi = it.get("doi") or it.get("DOI")
    title = it.get("title") or it.get("name")
    authors = it.get("authors") or it.get("author")
    year = it.get("year") or it.get("pubYear") or it.get("publication_year")
    venue = it.get("venue") or it.get("journal") or it.get("container")
    refs = []
    for r in _as_list(it.get("references")):
        if isinstance(r, dict):
            refs.append(norm_doi(r.get("doi")) or r.get("title") or r.get("id"))
        else:
            refs.append(norm_doi(r) or r)
    cits = [norm_doi(c) if isinstance(c, str) else (c.get("doi") or c.get("title")) if isinstance(c, dict) else c
            for c in _as_list(it.get("citations"))]
    if not (doi or title):
        return None
    return _mk_record(counter(), doi, title, authors, year, venue,
                      it.get("type") or it.get("pubType"), refs, cits,
                      it.get("relations"), fmt, file, pointer)


def parse_json_text(text, file, counter):
    """解析一个 JSON 文件文本，返回 (records, error)。"""
    try:
        obj = json.loads(text)
    except Exception as e:  # noqa: BLE001
        return [], f"JSON 解析失败: {e}"
    records = []
    if isinstance(obj, dict):
        if isinstance(obj.get("message"), dict):  # Crossref
            records = parse_crossref_message(obj["message"], "crossref", file, "$.message", counter)
        elif isinstance(obj.get("resultList"), dict):  # EuropePMC
            records = parse_europepmc_result(obj["resultList"].get("result") or [],
                                             "europepmc", file, "$.resultList.result", counter)
        elif isinstance(obj.get("results"), list):  # OpenAlex 风格
            records = parse_openalex_results(obj["results"], "openalex", file, "$.results", counter)
        else:
            for key in ("records", "nodes", "papers", "items", "data"):
                if isinstance(obj.get(key), list):
                    for i, it in enumerate(obj[key]):
                        r = parse_generic_record(it, "generic", file, f"$.{key}[{i}]", counter)
                        if r:
                            records.append(r)
                    break
            else:
                r = parse_generic_record(obj, "generic", file, "$", counter)
                if r:
                    records.append(r)
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            r = parse_generic_record(it, "generic", file, f"$[{i}]", counter)
            if r:
                records.append(r)
    return records, None


def parse_jsonl_text(text, file, counter):
    records = []
    errors = []
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception as e:  # noqa: BLE001
            errors.append(f"line {ln}: {e}")
            continue
        r = parse_generic_record(obj, "jsonl", file, f"$line:{ln}", counter)
        if r:
            records.append(r)
    return records, ("; ".join(errors) if errors else None)


def parse_csv_text(text, file, delimiter, counter):
    records = []
    try:
        reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
        for rn, row in enumerate(reader, 2):  # 第 1 行是表头
            authors = row.get("authors") or row.get("author") or ""
            refs = row.get("references") or ""
            r = _mk_record(
                counter(), row.get("doi") or row.get("DOI"), row.get("title"),
                [a.strip() for a in re.split(r"[;|]", authors) if a.strip()],
                row.get("year"), row.get("venue") or row.get("journal"),
                row.get("type"),
                [norm_doi(x.strip()) or x.strip() for x in re.split(r"[;|]", refs) if x.strip()],
                [], {}, "csv", file, f"row:{rn}")
            if r["doi"] or r["title"]:
                records.append(r)
    except Exception as e:  # noqa: BLE001
        return [], f"CSV 解析失败: {e}"
    return records, None


BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{([^,]*),(.*?)\n\}", re.DOTALL)
BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*[\{\"](.*?)[\}\"]\s*,?\s*$", re.MULTILINE)


def parse_bib_text(text, file, counter):
    """极简 BibTeX 解析（标准库、无第三方）。"""
    records = []
    try:
        for m in BIB_ENTRY_RE.finditer(text + "\n}"):
            entry_type, key, body = m.group(1), m.group(2), m.group(3)
            fields = {k.lower(): v for k, v in BIB_FIELD_RE.findall(body)}
            authors = [a.strip() for a in fields.get("author", "").split(" and ") if a.strip()]
            records.append(_mk_record(
                counter(), fields.get("doi"), fields.get("title"), authors,
                fields.get("year"), fields.get("journal") or fields.get("booktitle"),
                entry_type, [], [], {}, "bib", file, f"bibkey:{key}"))
    except Exception as e:  # noqa: BLE001
        return [], f"BibTeX 解析失败: {e}"
    return records, None


def parse_file(path, first_id=1):
    """按扩展名分派解析器；返回 (records, error)。rec_id 从 first_id 起编号。"""
    gen = (f"r{i:05d}" for i in range(first_id, 10 ** 9))
    counter = gen.__next__
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return [], f"读取失败: {e}"
    ext = path.suffix.lower()
    if ext == ".json":
        return parse_json_text(text, str(path), counter)
    if ext == ".jsonl":
        return parse_jsonl_text(text, str(path), counter)
    if ext == ".csv":
        return parse_csv_text(text, str(path), ",", counter)
    if ext == ".tsv":
        return parse_csv_text(text, str(path), "\t", counter)
    if ext == ".bib":
        return parse_bib_text(text, str(path), counter)
    return [], f"不支持的扩展名 {ext}"


def scan_roots(roots):
    """递归扫描候选根；返回 (records, sources_registry)。"""
    files, seen = [], set()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for p in candidates:
            if not p.is_file():
                continue
            rp = str(p.resolve())
            if rp in seen:
                continue
            ext = p.suffix.lower()
            if ext in RECORD_EXTS or ext in SKIP_EXTS:
                seen.add(rp)
                files.append(p)
    records, registry = [], []
    next_id = 1
    for p in files:
        if p.suffix.lower() in SKIP_EXTS:
            registry.append({"file": str(p), "format": p.suffix.lower().lstrip("."),
                             "records": 0, "status": "registered_only",
                             "note": "边表文件由 run_case.py 处理"})
            continue
        recs, err = parse_file(p, first_id=next_id)
        next_id += len(recs)
        if recs:
            records.extend(recs)
        registry.append({
            "file": str(p),
            "format": (recs[0]["format"] if recs else "unknown"),
            "records": len(recs),
            "status": "error" if (err and not recs) else ("ok_with_warnings" if err else "ok"),
            **({"error": err} if err else {}),
        })
    # 全局重排 rec_id，保证跨文件唯一且连续（与解析顺序一致，确定性）
    for i, rec in enumerate(records, 1):
        rec["rec_id"] = f"r{i:05d}"
    return records, registry


# ---------------------------------------------------------------- blocking

def block_keys(rec):
    keys = []
    if rec["doi"]:
        keys.append(("doi", rec["doi"]))
    if rec["title_norm"]:
        keys.append(("title40", rec["title_norm"][:40]))
    if rec["author_surnames"] and rec["year"]:
        keys.append(("surname_year", f"{rec['author_surnames'][0]}|{rec['year']}"))
    return keys


# ---------------------------------------------------------------- 打分与裁决

def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b) if (a | b) else 0.0


def containment(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def year_score(ya, yb):
    if ya is None or yb is None:
        return 0.5  # 缺年份：中性
    d = abs(int(ya) - int(yb))
    return {0: 1.0, 1: 0.7, 2: 0.3}.get(d, 0.0)


def venue_score(a, b):
    if not a or not b:
        return 0.5  # 缺 venue：中性
    ta = {t for t in norm_title(a).split() if t not in STOPWORDS}
    tb = {t for t in norm_title(b).split() if t not in STOPWORDS}
    return jaccard(ta, tb)


def doi_type_score(a, b):
    """DOI 前缀类型信号：同前缀（同注册机构）略增信；arXiv 前缀对期刊前缀略降。"""
    if not a["doi"] or not b["doi"]:
        return 0.5
    pa = a["doi"].split("/", 1)[0]
    pb = b["doi"].split("/", 1)[0]
    if pa == pb:
        return 1.0
    pre = {pa, pb}
    if any(p in PREPRINT_DOI_PREFIXES for p in pre):
        return 0.6  # 预印本 DOI 前缀 vs 其他：常见的版本对
    return 0.4


def pair_score(a, b):
    """返回 (score, components)。DOI 规范化精确一致 → 直接 1.0。"""
    ta, tb = title_tokens(a["title_norm"]), title_tokens(b["title_norm"])
    t_jac = jaccard(ta, tb)
    t_score = max(t_jac, containment(ta, tb))  # 副标题差异用包含度兜底
    a_score = jaccard(set(a["author_surnames"]), set(b["author_surnames"]))
    y_score = year_score(a["year"], b["year"])
    v_score = venue_score(a["venue"], b["venue"])
    d_score = doi_type_score(a, b)
    same_doi = bool(a["doi"]) and a["doi"] == b["doi"]
    if same_doi:
        score = 1.0
    else:
        score = 0.50 * t_score + 0.25 * a_score + 0.10 * y_score + 0.10 * v_score + 0.05 * d_score
        # 作者矛盾护栏：双方都有作者且姓完全不重叠时，压低到合并阈值以下
        if a["author_surnames"] and b["author_surnames"] and a_score == 0.0:
            score = min(score, 0.55)
    components = {
        "title_jaccard": round(t_jac, 4),
        "title_containment": round(containment(ta, tb), 4),
        "author_overlap": round(a_score, 4),
        "year_score": round(y_score, 4),
        "venue_score": round(v_score, 4),
        "doi_prefix_score": round(d_score, 4),
        "same_doi": same_doi,
    }
    return round(score, 4), components


def classify_version(rec):
    """版本谱系：preprint / conference / journal / supplement / unknown。"""
    doi = rec["doi"] or ""
    prefix = doi.split("/", 1)[0] if doi else ""
    venue = (rec["venue"] or "").lower()
    title = (rec["title"] or "").lower()
    ptype = (rec["pub_type"] or "").lower()
    rel = json.dumps(rec.get("relations") or {}, ensure_ascii=False).lower()
    if any(h in title for h in SUPPLEMENT_HINTS) or "supplement" in rel:
        return "supplement"
    if prefix in PREPRINT_DOI_PREFIXES or any(h in venue for h in PREPRINT_VENUE_HINTS) \
            or "preprint" in ptype:
        return "preprint"
    if any(h in venue for h in CONFERENCE_HINTS) or "proceedings" in ptype or "conf" in ptype:
        return "conference"
    if "journal" in ptype or venue:
        return "journal"
    return "unknown"


# ---------------------------------------------------------------- 合并（并查集）

def find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(parent, a, b):
    ra, rb = find(parent, a), find(parent, b)
    if ra != rb:
        parent[max(ra, rb)] = min(ra, rb)


def completeness(rec):
    score = 0
    for key in ("title", "doi", "year", "venue"):
        if rec.get(key):
            score += 1
    if rec.get("authors"):
        score += 1
    score += min(len(rec.get("references") or []), 5) / 10.0
    return score


def build_entities(records):
    """blocking → 打分 → 裁决 → 并查集合并 → 实体 + 台账。返回 (entities, ledger_parts)。"""
    blocks = {}
    for idx, rec in enumerate(records):
        for kind, key in block_keys(rec):
            blocks.setdefault((kind, key), []).append(idx)

    parent = list(range(len(records)))
    pair_records = {}   # frozenset({i,j}) -> (score, components, decision)
    seen_pairs = set()
    for (kind, key), members in sorted(blocks.items()):
        for x in range(len(members)):
            for y in range(x + 1, len(members)):
                i, j = sorted((members[x], members[y]))
                if (i, j) in seen_pairs:
                    continue
                seen_pairs.add((i, j))
                a, b = records[i], records[j]
                score, comp = pair_score(a, b)
                if score >= MERGE_THRESHOLD:
                    decision = "merge"
                    union(parent, i, j)
                elif score >= REVIEW_THRESHOLD:
                    decision = "review"
                else:
                    decision = "no_merge"
                pair_records[(i, j)] = (score, comp, decision)

    # 特殊情形标注
    distinct_same_title, same_work_diff_title = [], []
    for (i, j), (score, comp, decision) in sorted(pair_records.items()):
        a, b = records[i], records[j]
        if decision != "merge" and comp["title_jaccard"] >= 0.9 \
                and comp["author_overlap"] == 0.0 and not comp["same_doi"]:
            distinct_same_title.append({
                "rec_a": a["rec_id"], "rec_b": b["rec_id"],
                "title": a["title"] or b["title"],
                "score": score,
                "reason": "标题高度相似，但作者/DOI 完全不重叠，判定为同名不同文（distinct_same_title）",
                "locators": [a["source"], b["source"]],
            })
        if decision == "merge" and comp["same_doi"] and comp["title_jaccard"] < 0.5:
            same_work_diff_title.append({
                "rec_a": a["rec_id"], "rec_b": b["rec_id"],
                "doi": a["doi"],
                "titles": [a["title"], b["title"]],
                "reason": "DOI 相同但标题差异大，判定为同文不同名（same_work_different_title），双标题均保留为证据",
                "locators": [a["source"], b["source"]],
            })

    # 分组
    groups = {}
    for idx in range(len(records)):
        groups.setdefault(find(parent, idx), []).append(idx)

    entities, ledger_groups = [], []
    for e_no, (root, members) in enumerate(sorted(groups.items()), 1):
        members = sorted(members)
        recs = [records[i] for i in members]
        kinds = sorted({classify_version(r) for r in recs})
        # 代表记录：元数据最全；并列时优先期刊版，再按 rec_id 确定性
        kind_rank = {"journal": 0, "conference": 1, "preprint": 2, "supplement": 3, "unknown": 4}
        rep = sorted(recs, key=lambda r: (-completeness(r), kind_rank.get(classify_version(r), 9), r["rec_id"]))[0]
        # 组内成对评分与理由
        group_pairs = []
        for (i, j), (score, comp, decision) in sorted(pair_records.items()):
            if i in members and j in members:
                group_pairs.append({
                    "pair": [records[i]["rec_id"], records[j]["rec_id"]],
                    "score": score, "components": comp, "decision": decision,
                })
        # 冲突字段保留
        conflicts = {}
        for field in ("title", "year", "venue"):
            vals = {r["rec_id"]: r.get(field) for r in recs}
            if len({json.dumps(v, ensure_ascii=False) for v in vals.values()}) > 1:
                conflicts[field] = vals
        auth_sets = {r["rec_id"]: r["authors"] for r in recs}
        if len({json.dumps(v, ensure_ascii=False) for v in auth_sets.values()}) > 1:
            conflicts["authors"] = auth_sets
        flags = []
        if len(recs) == 1:
            r = recs[0]
            if not r["doi"] and (not r["year"] or not r["title"] or not r["authors"]):
                flags.append("incomplete_record")
        else:
            if len(kinds) > 1:
                flags.append("version_chain")
            if any(sw["rec_a"] in {r["rec_id"] for r in recs} or sw["rec_b"] in {r["rec_id"] for r in recs}
                   for sw in same_work_diff_title):
                flags.append("same_work_different_title")
        entity_id = f"E{e_no:04d}"
        dois = sorted({r["doi"] for r in recs if r["doi"]})
        entity = {
            "entity_id": entity_id,
            "title": rep["title"],
            "authors": rep["authors"],
            "year": rep["year"],
            "doi": rep["doi"] or (dois[0] if dois else None),
            "dois": dois,
            "venue": rep["venue"],
            "kind": classify_version(rep),
            "lineage": kinds,
            "member_count": len(recs),
            "representative": rep["rec_id"],
            "references": uniq([x for r in recs for x in r["references"]]),
            "citations": uniq([x for r in recs for x in r["citations"]]),
            "members": [{
                "rec_id": r["rec_id"], "doi": r["doi"], "title": r["title"],
                "authors": r["authors"], "year": r["year"], "venue": r["venue"],
                "version": classify_version(r), "format": r["format"],
                "references": r["references"], "citations": r["citations"],
                "locator": r["source"],
            } for r in recs],
            "merge_evidence": ({
                "singleton": True,
                "note": "无同块候选或同块候选得分均低于合并阈值，保持独立实体",
            } if len(recs) == 1 else {
                "pair_scores": group_pairs,
                "conflicts": conflicts,
                "reasons": [
                    f"pair {p['pair'][0]}~{p['pair'][1]} score={p['score']} "
                    f"(title={p['components']['title_containment']}, authors={p['components']['author_overlap']}, "
                    f"year={p['components']['year_score']}, venue={p['components']['venue_score']}, "
                    f"same_doi={p['components']['same_doi']}) → {p['decision']}"
                    for p in group_pairs
                ],
            }),
            "flags": flags,
        }
        entities.append(entity)
        ledger_groups.append({
            "entity_id": entity_id,
            "members": [r["rec_id"] for r in recs],
            "member_locators": {r["rec_id"]: r["source"] for r in recs},
            "representative": rep["rec_id"],
            "lineage": {r["rec_id"]: classify_version(r) for r in recs},
            "version_chain": len(kinds) > 1,
            "pair_scores": group_pairs,
            "conflicts": conflicts,
            "flags": flags,
        })

    review_queue = []
    for (i, j), (score, comp, decision) in sorted(pair_records.items()):
        if decision == "review":
            review_queue.append({
                "rec_a": records[i]["rec_id"], "rec_b": records[j]["rec_id"],
                "score": score, "components": comp,
                "reason": "得分落入存疑区间 [0.6, 0.85)，未自动合并，需人工复核",
                "locators": [records[i]["source"], records[j]["source"]],
            })

    return entities, {
        "groups": ledger_groups,
        "review_queue": review_queue,
        "distinct_same_title": distinct_same_title,
        "same_work_different_title": same_work_diff_title,
    }


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="跨库语料解析与论文身份合并（离线、标准库）")
    ap.add_argument("--roots", nargs="*", default=None,
                    help="候选语料根（可多个）；缺省依次使用 /input, /app/work, cwd")
    ap.add_argument("--workdir", default="/app/work", help="输出目录（entities.jsonl / merge_ledger.json）")
    args = ap.parse_args(argv)

    roots = args.roots if args.roots else [p for p in ("/input", "/app/work", str(Path.cwd()))
                                           if Path(p).exists()]
    records, registry = scan_roots(roots)
    entities, ledger_parts = build_entities(records)

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    entities_path = workdir / "entities.jsonl"
    with entities_path.open("w", encoding="utf-8") as f:
        for e in entities:
            f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")

    stats = {
        "roots_scanned": [str(r) for r in roots],
        "files_registered": len(registry),
        "files_error": sum(1 for s in registry if s["status"] == "error"),
        "records_parsed": len(records),
        "entities": len(entities),
        "merged_groups": sum(1 for e in entities if e["member_count"] > 1),
        "review_pairs": len(ledger_parts["review_queue"]),
        "distinct_same_title_pairs": len(ledger_parts["distinct_same_title"]),
        "same_work_different_title_pairs": len(ledger_parts["same_work_different_title"]),
        "incomplete_records": sum(1 for e in entities if "incomplete_record" in e["flags"]),
    }
    ledger = {
        "generated_by": "identity_merge.py (offline, stdlib)",
        "thresholds": {"merge": MERGE_THRESHOLD, "review": REVIEW_THRESHOLD},
        "stats": stats,
        "sources": registry,
        **ledger_parts,
    }
    ledger_path = workdir / "merge_ledger.json"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True),
                           encoding="utf-8")

    print(json.dumps({"ok": True, "entities": stats["entities"], "records": stats["records_parsed"],
                      "merged_groups": stats["merged_groups"], "review_pairs": stats["review_pairs"],
                      "distinct_same_title_pairs": stats["distinct_same_title_pairs"],
                      "files_error": stats["files_error"],
                      "entities_path": str(entities_path), "ledger_path": str(ledger_path)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
