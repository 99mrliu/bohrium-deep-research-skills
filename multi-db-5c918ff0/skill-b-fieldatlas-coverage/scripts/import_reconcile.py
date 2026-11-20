#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""import_reconcile.py — 增量导入对账（轻量）。

若 case 材料含 organizer-local 增量导入状态（import_state），将新材料与本地
已导入记录按 标识符（DOI）或 归一题名+年份 精确匹配（不做模糊匹配——模糊
归 identitymerge-dedup-engine 方向），输出三类清单：
  already_imported    已导入且无冲突
  new_candidates      新材料中本地没有的候选
  conflicting_updates   标识符相同但卷/期/年份/页/刊名不一致（需人工裁决）

输出 /app/work/import_reconcile.json：
  {already_imported, new_candidates, conflicting_updates, unmatched_local,
   match_stats}

新材料侧每条论文取各来源合并后的“最优值”：字段冲突时按来源优先级
crossref > europepmc > publisher > 其余，取第一个 present 值（确定性）。

退出码：0=对账完成；2=无导入状态文件（材料不含该状态，诚实降级）或卡片为空；
        3=导入状态文件非法 JSON。
"""
import argparse
import json
import os
import re
import sys

SOURCE_PRIORITY = ["crossref", "europepmc", "publisher", "recordlist",
                   "jsonl", "csv", "unknown"]
DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
NONALNUM_RE = re.compile(r"[^0-9a-z]+")
YEAR_RE = re.compile(r"(19|20)\d{2}")

COMPARE_FIELDS = ("title", "container", "year", "volume", "issue", "pages")


def clean_doi(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return DOI_PREFIX.sub("", s).lower() or None


def norm_title(s):
    if s is None:
        return None
    return NONALNUM_RE.sub(" ", str(s).lower()).strip() or None


def norm_val(v):
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return str(v)
    return re.sub(r"\s+", " ", str(v).strip().lower()).rstrip(".")


def match_key(doi, title, year):
    if doi:
        return "doi:" + doi
    t = norm_title(title)
    if t:
        return "ty:%s::%s" % (t, year if year else "?")
    return None


def load_import_state(path):
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if isinstance(obj, dict):
        for k in ("imported_records", "records", "items", "state"):
            if isinstance(obj.get(k), list):
                return [r for r in obj[k] if isinstance(r, dict)]
        return [obj] if "doi" in obj or "title" in obj else []
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict)]
    return []


def merged_papers(cards):
    """按 cluster_key 合并卡片为论文级最优值（来源优先级确定性取值）。"""
    papers = {}
    prio = {s: i for i, s in enumerate(SOURCE_PRIORITY)}
    for c in cards:
        ck = c.get("cluster_key")
        p = papers.setdefault(ck, {"cluster_key": ck, "sources": set(),
                                   "retracted": False, "values": {}})
        p["sources"].add(c.get("source"))
        p["retracted"] = p["retracted"] or bool(c.get("retracted"))
        cs = prio.get(c.get("source"), len(SOURCE_PRIORITY))
        for fld in COMPARE_FIELDS:
            ent = (c.get("fields", {}).get(fld) or {})
            if ent.get("status") != "present":
                continue
            cur = p["values"].get(fld)
            if cur is None or cs < cur[1]:
                p["values"][fld] = (ent.get("value"), cs)
    for p in papers.values():
        p["best"] = {fld: p["values"].get(fld, (None, None))[0]
                     for fld in COMPARE_FIELDS}
        p["doi"] = None
        for c in [c for c in cards if c.get("cluster_key") == p["cluster_key"]]:
            e = (c.get("fields", {}).get("identifiers.doi") or {})
            if e.get("status") == "present" and e.get("value"):
                p["doi"] = e["value"]
                break
        p["match_key"] = match_key(p["doi"], p["best"].get("title"),
                                   p["best"].get("year"))
    return sorted(papers.values(), key=lambda p: p["cluster_key"])


def local_key(rec):
    y = rec.get("year")
    if y is None:
        m = YEAR_RE.search(str(rec.get("pub_date") or ""))
        y = int(m.group(0)) if m else None
    return match_key(clean_doi(rec.get("doi")), rec.get("title"), y), y


def main():
    ap = argparse.ArgumentParser(
        description="增量导入对账：already/new/conflicting 三类清单（exit 0/2/3）。")
    ap.add_argument("--summary", default="/app/work/case_summary.json",
                    help="case_summary.json（自动定位 import_state）")
    ap.add_argument("--state", default=None, help="直接指定导入状态文件路径")
    ap.add_argument("--cards", default="/app/work/field_cards.jsonl")
    ap.add_argument("--out", default="/app/work/import_reconcile.json")
    args = ap.parse_args()

    state_path = args.state
    if not state_path:
        if os.path.isfile(args.summary):
            try:
                with open(args.summary, "r", encoding="utf-8") as f:
                    state_path = json.load(f).get("import_state")
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                state_path = None
        else:
            print("ERROR: case_summary.json 不存在（材料不足，exit 2）: %s"
                  % args.summary, file=sys.stderr)
            return 2
    if not state_path or not os.path.isfile(state_path):
        print("ERROR: 材料不含 organizer-local 增量导入状态（诚实降级，exit 2）。"
              "请用 --state 显式指定或确认 case 材料是否提供 import_state 文件。",
              file=sys.stderr)
        return 2
    try:
        local_records = load_import_state(state_path)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print("ERROR: 导入状态文件非法 JSON（校验失败，exit 3）: %s" % e,
              file=sys.stderr)
        return 3
    if not os.path.isfile(args.cards):
        print("ERROR: field_cards.jsonl 不存在（材料不足，exit 2）: %s"
              % args.cards, file=sys.stderr)
        return 2
    cards = []
    with open(args.cards, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                cards.append(json.loads(ln))
    if not cards:
        print("ERROR: field_cards 为空（材料不足，诚实降级，exit 2）", file=sys.stderr)
        return 2

    local_index = {}
    unmatched_local = []
    for i, rec in enumerate(local_records):
        k, y = local_key(rec)
        if k is None:
            unmatched_local.append({
                "local_id": rec.get("local_id") or rec.get("id") or "local[%d]" % i,
                "reason": "本地记录无 DOI 且题名不可归一化，无法精确匹配"})
            continue
        local_index[k] = rec

    already, new_candidates, conflicting = [], [], []
    matched_local_keys = set()
    for p in merged_papers(cards):
        lk = p["match_key"]
        rec = local_index.get(lk)
        if rec is None:
            new_candidates.append({
                "cluster_key": p["cluster_key"], "doi": p["doi"],
                "title": p["best"].get("title"), "year": p["best"].get("year"),
                "sources": sorted(p["sources"]), "retracted": p["retracted"]})
            continue
        matched_local_keys.add(lk)
        diffs = []
        for fld in COMPARE_FIELDS:
            lv = rec.get(fld)
            nv = p["best"].get(fld)
            if lv is None or nv is None or lv == "":
                continue  # 单边空值视为补充而非冲突
            if norm_val(lv) != norm_val(nv):
                diffs.append({"field": fld, "local_value": lv, "new_value": nv})
        entry = {"local_id": rec.get("local_id") or rec.get("id"),
                 "cluster_key": p["cluster_key"], "doi": p["doi"],
                 "title": p["best"].get("title"), "year": p["best"].get("year"),
                 "sources": sorted(p["sources"])}
        if diffs:
            entry["diffs"] = diffs
            entry["disposition"] = ("manual_review：本地记录与新检索在"
                                    + ",".join(d["field"] for d in diffs)
                                    + " 不一致，需人工裁决以何者为准")
            conflicting.append(entry)
        else:
            already.append(entry)

    for k, rec in local_index.items():
        if k not in matched_local_keys:
            unmatched_local.append({
                "local_id": rec.get("local_id") or rec.get("id"),
                "key": k, "title": rec.get("title"),
                "reason": "本地已导入但新材料无对应记录（可能已下线或检索口径不同）"})

    result = {
        "state_file": state_path,
        "already_imported": already,
        "new_candidates": new_candidates,
        "conflicting_updates": conflicting,
        "unmatched_local": unmatched_local,
        "match_stats": {
            "local_total": len(local_records),
            "already_imported": len(already),
            "new_candidates": len(new_candidates),
            "conflicting_updates": len(conflicting),
            "unmatched_local": len(unmatched_local),
        },
        "match_rule": "仅标识符(DOI)/归一题名+年份精确匹配；不做模糊匹配",
    }
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("OK: 导入对账 -> %s (already=%d, new=%d, conflict=%d, "
          "unmatched_local=%d)" % (
              args.out, len(already), len(new_candidates), len(conflicting),
              len(unmatched_local)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR: import_reconcile 未捕获异常（诚实降级，exit 2）: %r" % e,
              file=sys.stderr)
        sys.exit(2)
