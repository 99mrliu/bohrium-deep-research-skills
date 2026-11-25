#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""snapshot_align.py — 对齐同一来源的两份快照（t_prev 增量导入状态 与 t_now 当前快照）。

匹配键规范化规则（详见 references/metrics_definitions.md）：
  1. DOI 优先（小写、去 https://doi.org/ 等前缀）；
  2. 其次 arXiv 号（去 arXiv: 前缀与 vN 版本号）；
  3. 最后标题（小写、去标点、压缩空白）。

输出 aligned.json：
  - records_prev / records_now：两侧全量记录（含规范化键与 locator）；
  - added   ：在 t_now 出现、在 t_prev 不存在的记录（机械新增候选）；
  - removed ：在 t_prev 存在、在 t_now 消失的记录（仅记录，不参与真值）；
  - warnings：键缺失、快照内重复主键等数据质量问题。

仅使用 Python3 标准库，完全离线。
"""
import argparse
import json
import re
import sys

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "doi:")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def norm_doi(v):
    if not v:
        return None
    s = str(v).strip().lower()
    for p in _DOI_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    return s or None


def norm_arxiv(v):
    if not v:
        return None
    s = str(v).strip().lower()
    if s.startswith("arxiv:"):
        s = s[6:]
    s = re.sub(r"v\d+$", "", s)
    return s or None


def norm_title(v):
    if not v:
        return None
    s = str(v).strip().lower()
    s = re.sub(r"[^a-z0-9一-鿿]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def record_keys(rec):
    """返回 {'doi': 'doi:...', 'arxiv': 'arxiv:...', 'title': 'title:...'} 中可用的部分。"""
    keys = {}
    d = norm_doi(rec.get("doi"))
    a = norm_arxiv(rec.get("arxiv_id"))
    t = norm_title(rec.get("title"))
    if d:
        keys["doi"] = "doi:" + d
    if a:
        keys["arxiv"] = "arxiv:" + a
    if t:
        keys["title"] = "title:" + t
    return keys


def primary_key_of(keys):
    return keys.get("doi") or keys.get("arxiv") or keys.get("title")


def extract_records(doc, path):
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for k in ("records", "items", "results", "entries"):
            if isinstance(doc.get(k), list):
                return doc[k]
    raise SystemExit("ERROR: 无法在 %s 中定位记录列表（期望顶层数组或 records/items/results/entries 字段）" % path)


def build_side(records, name):
    side = []
    warnings = []
    seen = {}
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            warnings.append("%s[%d] 不是对象，跳过匹配" % (name, i))
            rec = {"_raw": rec}
        keys = record_keys(rec)
        pk = primary_key_of(keys)
        loc = {
            "snapshot": name,
            "index": i,
            "source": rec.get("source"),
            "doi": rec.get("doi"),
            "arxiv_id": rec.get("arxiv_id"),
            "title": rec.get("title"),
        }
        if pk is None:
            pk = "unkeyed:%s:%d" % (name, i)
            warnings.append("%s[%d] 缺少 doi/arxiv_id/title，无法参与跨快照匹配" % (name, i))
        elif pk in seen:
            warnings.append("%s 内主键 %s 重复：index %d 与 %d" % (name, pk, i, seen[pk]))
        else:
            seen[pk] = i
        side.append({"primary_key": pk, "keys": keys, "record": rec, "locator": loc})
    return side, warnings


def brief(item):
    rec = item["record"]
    return {
        "canonical_key": item["primary_key"],
        "doi": rec.get("doi"),
        "arxiv_id": rec.get("arxiv_id"),
        "title": rec.get("title"),
        "published": rec.get("published"),
        "ingested_at": rec.get("ingested_at"),
        "source": rec.get("source"),
        "locator": item["locator"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="对齐 t_prev / t_now 两份快照")
    ap.add_argument("--prev", required=True, help="t_prev 增量导入状态快照 JSON")
    ap.add_argument("--now", required=True, help="t_now 当前快照 JSON")
    ap.add_argument("--out", required=True, help="输出 aligned.json 路径")
    args = ap.parse_args(argv)

    prev_records = extract_records(load_json(args.prev), args.prev)
    now_records = extract_records(load_json(args.now), args.now)

    prev_side, w1 = build_side(prev_records, "prev")
    now_side, w2 = build_side(now_records, "now")

    prev_pks = {it["primary_key"] for it in prev_side}
    now_pks = {it["primary_key"] for it in now_side}

    added = [brief(it) for it in now_side if it["primary_key"] not in prev_pks]
    removed = [brief(it) for it in prev_side if it["primary_key"] not in now_pks]
    common = len(prev_pks & now_pks)

    out = {
        "prev_path": args.prev,
        "now_path": args.now,
        "counts": {
            "prev_records": len(prev_side),
            "now_records": len(now_side),
            "common": common,
            "added": len(added),
            "removed": len(removed),
        },
        "records_prev": prev_side,
        "records_now": now_side,
        "added": added,
        "removed": removed,
        "warnings": w1 + w2,
    }
    dump_json(args.out, out)
    print("aligned: prev=%d now=%d common=%d added=%d removed=%d warnings=%d"
          % (len(prev_side), len(now_side), common, len(added), len(removed), len(out["warnings"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
