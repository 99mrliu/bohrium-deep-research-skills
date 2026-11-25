#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""channel_merge.py — 关键词快照候选读取 + 图谱/关键词双渠道并集合并。

对齐只做最低限度精确匹配（明确不做去重键归一化工程）：
  1. DOI：小写、去首尾空白、去 "https://doi.org/"、"http://doi.org/"、"doi:" 前缀后精确相等；
  2. 标题：casefold + 空白压缩后精确相等（仅当两边都没有可匹配 DOI 时）。
匹配不上即认为不同条目，绝不模糊合并。

合并产出渠道三分：both / graph_only / keyword_only。
context（窗口外）与 dangling reference 不参与合并，由调用方单独成列。
"""
import json
import re
import sys

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:")


def norm_doi(d):
    if not isinstance(d, str):
        return None
    d = d.strip().lower()
    for p in _DOI_PREFIXES:
        if d.startswith(p):
            d = d[len(p):]
    return d or None


def norm_title(t):
    if isinstance(t, list):
        t = t[0] if t else None
    if not isinstance(t, str):
        return None
    t = re.sub(r"\s+", " ", t).strip().casefold()
    return t or None


def _year_of_item(it):
    if not isinstance(it, dict):
        return None
    for key in ("issued", "published", "published-print", "published-online", "created"):
        v = it.get(key)
        if isinstance(v, dict):
            dp = v.get("date-parts")
            if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
                if isinstance(dp[0][0], int):
                    return dp[0][0]
    for key in ("year", "published_year"):
        v = it.get(key)
        if isinstance(v, int):
            return v
    return None


def load_keyword_candidates(path):
    """读取关键词检索 API 快照（Crossref 风格 message.items，或顶层数组/{"items": [...]}）。

    返回 (candidates, locator_base)。每个候选带 locator（快照内 JSON 指针）。
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("message"), dict) \
            and isinstance(data["message"].get("items"), list):
        items, base = data["message"]["items"], "/message/items"
    elif isinstance(data, list):
        items, base = data, ""
    elif isinstance(data, dict) and isinstance(data.get("items"), list):
        items, base = data["items"], "/items"
    else:
        raise ValueError("无法识别的快照布局（既不是 message.items 也不是 items/数组）: %s" % path)
    cands = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        doi = it.get("DOI") or it.get("doi")
        title = it.get("title")
        if isinstance(title, list):
            title = title[0] if title else None
        cands.append({
            "id": (norm_doi(doi) and ("doi:" + norm_doi(doi))) or ("kw-%d" % i),
            "doi": doi,
            "title": title,
            "abstract": it.get("abstract"),
            "year": _year_of_item(it),
            "locator": "%s/%d" % (base, i),
        })
    return cands, base


def merge(graph_new_records, keyword_candidates):
    """graph_new_records: snowball.expand 结果中 role == 'new' 的记录。"""
    kw_by_doi, kw_by_title = {}, {}
    for kc in keyword_candidates:
        dk, tk = norm_doi(kc.get("doi")), norm_title(kc.get("title"))
        if dk:
            kw_by_doi.setdefault(dk, kc)
        if tk:
            kw_by_title.setdefault(tk, kc)

    both, graph_only = [], []
    matched_kw_ids = set()
    for rec in graph_new_records:
        dk, tk = norm_doi(rec.get("doi")), norm_title(rec.get("title"))
        hit = kw_by_doi.get(dk) if dk else None
        match_via = "doi" if hit else None
        if hit is None and tk:
            hit = kw_by_title.get(tk)
            match_via = "title" if hit else None
        if hit is not None:
            matched_kw_ids.add(hit["id"])
            both.append({
                "id": rec["node_id"],
                "doi": rec.get("doi") or hit.get("doi"),
                "title": rec.get("title") or hit.get("title"),
                "year": rec.get("year") if rec.get("year") is not None else hit.get("year"),
                "channel": "both",
                "matched_via": match_via,
                "locators": {"graph": rec.get("node_locator"), "keyword": hit.get("locator")},
                "distance": rec.get("distance"),
                "co_citation": rec.get("co_citation"),
                "directions": rec.get("directions"),
            })
        else:
            graph_only.append({
                "id": rec["node_id"],
                "doi": rec.get("doi"),
                "title": rec.get("title"),
                "abstract": rec.get("abstract"),
                "year": rec.get("year"),
                "channel": "graph_only",
                "locators": {"graph": rec.get("node_locator"), "keyword": None},
                "distance": rec.get("distance"),
                "co_citation": rec.get("co_citation"),
                "directions": rec.get("directions"),
            })
    keyword_only = [{
        "id": kc["id"], "doi": kc.get("doi"), "title": kc.get("title"),
        "abstract": kc.get("abstract"), "year": kc.get("year"),
        "channel": "keyword_only",
        "locators": {"graph": None, "keyword": kc.get("locator")},
    } for kc in keyword_candidates if kc["id"] not in matched_kw_ids]

    return {"both": both, "graph_only": graph_only, "keyword_only": keyword_only}


def main(argv):
    if len(argv) != 3:
        print("用法: channel_merge.py <expansion.json(snowball 输出)> <snapshot.json>",
              file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        expansion = json.load(f)
    kws, _ = load_keyword_candidates(argv[2])
    new_records = [r for r in expansion.get("records", []) if r.get("role") == "new"]
    json.dump(merge(new_records, kws), sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
