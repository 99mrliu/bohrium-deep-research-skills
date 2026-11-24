#!/usr/bin/env python3
"""date_normalize.py — 源日期归一化。

把材料文件中每条题录的 published 类与 indexed 类日期字段归一化为
UTC 区间 [earliest, latest]，并记录 precision（year/month/day/second）、
原始值与 locator（文件 + JSON 路径）。

字段优先级（命中第一个非空字段即停，选择记录在产物的 field 中）：
- published 类：published, published-print, published-online, issued,
  firstPublicationDate, electronicPublicationDate, date
- indexed 类：indexed, indexed_at, firstIndexDate, indexDate, created, created_at

用法：
  python3 date_normalize.py --case-dir <dir> [--materials f1.json f2.json ...] \
      [--out normalized_items.json]
缺省 --materials 时取 case.json 的 materials 列表（相对 case-dir）。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from window_common import dump_json, load_json, normalize_date_value  # noqa: E402

PUBLISHED_FIELDS = [
    "published", "published-print", "published-online", "issued",
    "firstPublicationDate", "electronicPublicationDate", "date",
]
INDEXED_FIELDS = [
    "indexed", "indexed_at", "firstIndexDate", "indexDate", "created", "created_at",
]
ID_FIELDS = ["DOI", "doi", "id", "pmid", "pmcid"]


def pick_field(item, fields):
    for f in fields:
        if f in item and item[f] not in (None, "", [], {}):
            return f, item[f]
    return None, None


def pick_id(item):
    for f in ID_FIELDS:
        v = item.get(f)
        if v:
            return str(v)
    return None


def pick_title(item):
    t = item.get("title")
    if isinstance(t, list):
        t = t[0] if t else None
    if t is None:
        t = item.get("article-title") or item.get("book-title")
    return str(t) if t else None


def normalize_items(case_dir, material_paths):
    entries = []
    for rel in material_paths:
        path = rel if os.path.isabs(rel) else os.path.join(case_dir, rel)
        data = load_json(path)
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        source = data.get("source") if isinstance(data, dict) else None
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            base = "%s#/items/%d" % (rel, i)
            pf, pv = pick_field(item, PUBLISHED_FIELDS)
            xf, xv = pick_field(item, INDEXED_FIELDS)
            pub = normalize_date_value(pv)
            idx = normalize_date_value(xv)
            if pub is not None:
                pub["field"] = pf
                pub["locator"] = "%s/%s" % (base, pf)
            if idx is not None:
                idx["field"] = xf
                idx["locator"] = "%s/%s" % (base, xf)
            if pv is not None and pub is None:
                unparseable_pub = {"field": pf, "raw": pv, "locator": "%s/%s" % (base, pf)}
            else:
                unparseable_pub = None
            entries.append({
                "doi": pick_id(item),
                "title": pick_title(item),
                "source": source or os.path.basename(rel),
                "source_file": rel,
                "item_locator": base,
                "published": pub,
                "indexed": idx,
                "unparseable_published": unparseable_pub,
            })
    return entries


def main(argv=None):
    ap = argparse.ArgumentParser(description="源日期归一化为 UTC 区间")
    ap.add_argument("--case-dir", required=True)
    ap.add_argument("--case-file", default="case.json")
    ap.add_argument("--materials", nargs="*", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    case = load_json(os.path.join(args.case_dir, args.case_file))
    materials = args.materials or case.get("materials") or []
    if not materials:
        raise SystemExit("未找到材料文件列表（case.materials 为空且未传 --materials）")
    entries = normalize_items(args.case_dir, materials)
    out = {
        "materials": materials,
        "item_count": len(entries),
        "items": entries,
    }
    dump_json(out, args.out)
    n_pub = sum(1 for e in entries if e["published"])
    n_idx = sum(1 for e in entries if e["indexed"])
    print("normalized -> %s | items=%d with_published=%d with_indexed=%d"
          % (args.out, len(entries), n_pub, n_idx))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
