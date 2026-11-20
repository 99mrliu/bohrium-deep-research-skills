#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""import_diff.py — 增量导入 diff：组织方本地导入状态 vs 本次检索 canonical 记录。

匹配规则：只按 DOI 精确（小写归一）或归一题名精确两级匹配；模糊对不进本脚本
（交模型仲裁）。四个分类：
  new                检索到但导入状态无此标识符；
  already_imported   标识符一致且比对字段值全部一致；
  updated            标识符一致但字段值不同（给出字段级 diff）；
  conflicting        导入状态内同一标识符存在多个互相矛盾的版本/值。

比对字段：title / year / journal / volume / issue / pages / authors
（归一化后比较：小写、去标点、折叠空白；year 取数字串）。

退出码：0=成功；2=无导入状态材料（诚实降级，绝不臆造状态）；3=输入非法。
顶层未捕获异常汇总并以 exit 2 降级，绝不 crash。

用法：
  python3 import_diff.py [--summary /app/work/case_summary.json]
      [--work /app/work] [--state /path/import_state.json] [--out import_diff.json]
"""
import argparse
import json
import os
import re
import sys

COMPARE_FIELDS = ["title", "year", "journal", "volume", "issue", "pages",
                  "authors"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def norm_doi(v):
    if not isinstance(v, str):
        return None
    s = v.strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s).rstrip(".")
    return s or None


def norm_s(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    s = re.sub(r"[^a-z0-9一-鿿]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def ident_key(rec):
    """标识符优先级：DOI > PMID > PMCID > 归一题名。"""
    d = norm_doi(rec.get("doi"))
    if d:
        return "doi:" + d
    for k in ("pmid", "pmcid"):
        v = rec.get(k)
        if v:
            s = re.sub(r"\D", "", str(v))
            if s:
                return "%s:%s" % (k, s)
    t = norm_s(rec.get("title"))
    if t and len(t) >= 8:
        return "title:" + t
    return None


def state_records(state_obj):
    if isinstance(state_obj, dict):
        for k in ("records", "imported", "items", "entries"):
            if isinstance(state_obj.get(k), list):
                return [r for r in state_obj[k] if isinstance(r, dict)]
    if isinstance(state_obj, list):
        return [r for r in state_obj if isinstance(r, dict)]
    return []


def find_import_state(summary, override):
    if override:
        return override
    p = summary.get("import_state")
    return p if p and os.path.isfile(p) else None


def main_inner(args):
    if not os.path.isfile(args.summary):
        print("ERROR: case_summary 不存在（材料不足）: %s" % args.summary,
              file=sys.stderr)
        return 2
    try:
        summary = load_json(args.summary)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: case_summary 非法（校验失败）: %s" % e, file=sys.stderr)
        return 3

    can_path = os.path.join(args.work, "canonical_records.json")
    if not os.path.isfile(can_path):
        print("ERROR: canonical_records.json 缺失，请先运行 build_lineage.py。"
              , file=sys.stderr)
        return 2
    canon = load_json(can_path)

    state_path = find_import_state(summary, args.state)
    if not state_path:
        print("ERROR: 材料中无组织方增量导入状态（import_state 未嗅探到，"
              "--state 亦未提供），诚实降级 exit 2；不臆造导入状态。",
              file=sys.stderr)
        return 2
    try:
        state_obj = load_json(state_path)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: import_state 非法（校验失败）: %s" % e, file=sys.stderr)
        return 3
    srecs = state_records(state_obj)

    # 导入状态内部冲突：同一标识符多个版本
    by_key = {}
    for i, r in enumerate(srecs):
        k = ident_key(r)
        if k:
            by_key.setdefault(k, []).append(i)
    conflicting_keys = set()
    for k, idxs in by_key.items():
        if len(idxs) < 2:
            continue
        variants = set()
        for i in idxs:
            variants.add(tuple(sorted(
                (f, norm_s(srecs[i].get(f))) for f in COMPARE_FIELDS
                if srecs[i].get(f) not in (None, ""))))
        if len(variants) > 1:
            conflicting_keys.add(k)

    classes = {"new": [], "already_imported": [], "updated": [], "conflicting": []}
    used_state = set()
    for c in canon.get("canonicals") or []:
        cf = c.get("fields") or {}
        flat = {f: (cf.get(f) or {}).get("value") for f in cf}
        ident = (cf.get("doi") or {}).get("value") or \
            (cf.get("pmid") or {}).get("value") or \
            (cf.get("title") or {}).get("value") or "-"
        key = ident_key(flat)
        entry = {"canonical_id": c.get("canonical_id"), "identifier": ident}
        if key is None:
            entry["note"] = "canonical 无可比对标识符，归入 new"
            classes["new"].append(entry)
            continue
        idxs = by_key.get(key, [])
        if not idxs:
            classes["new"].append(entry)
            continue
        used_state.update(idxs)
        if key in conflicting_keys:
            entry["conflicting_state_versions"] = len(idxs)
            classes["conflicting"].append(entry)
            continue
        sr = srecs[idxs[0]]
        diffs = []
        for f in COMPARE_FIELDS:
            sv, cv = norm_s(sr.get(f)), norm_s(flat.get(f))
            if sv is None or cv is None:
                continue  # 字段缺失不参与比对（不臆断）
            if sv != cv:
                diffs.append({"field": f, "imported": sr.get(f),
                              "retrieved": flat.get(f)})
        if diffs:
            entry["field_diffs"] = diffs
            classes["updated"].append(entry)
        else:
            classes["already_imported"].append(entry)

    # 导入状态中本次未检索到的记录（留痕，不分类为 new）
    stale = []
    canon_keys = set()
    for c in canon.get("canonicals") or []:
        cf = c.get("fields") or {}
        flat = {f: (cf.get(f) or {}).get("value") for f in cf}
        k = ident_key(flat)
        if k:
            canon_keys.add(k)
    for k, idxs in sorted(by_key.items()):
        if k not in canon_keys:
            for i in idxs:
                stale.append({"state_record_index": i,
                              "identifier": ident_key(srecs[i])})

    out = {
        "import_state_file": os.path.basename(state_path),
        "match_rule": "DOI 小写归一精确 / PMID / PMCID / 归一题名精确；"
                      "模糊匹配不在本脚本",
        "classes": classes,
        "stale_in_state": stale,
        "summary": {k: len(v) for k, v in classes.items()},
    }
    out_path = args.out or os.path.join(args.work, "import_diff.json")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("OK: import_diff -> %s (new=%d, already=%d, updated=%d, conflicting=%d,"
          " stale=%d)" % (out_path, len(classes["new"]),
                          len(classes["already_imported"]),
                          len(classes["updated"]),
                          len(classes["conflicting"]), len(stale)))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="增量导入 diff（四类，exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--state", default=None, help="import_state 文件路径覆盖")
    ap.add_argument("--out", default=None, help="输出路径（默认 <work>/import_diff.json）")
    args = ap.parse_args()
    try:
        return main_inner(args)
    except Exception as e:
        print("ERROR: 未捕获异常，诚实降级 exit 2: %r" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
