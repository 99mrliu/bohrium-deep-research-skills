#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""metrics.py — 候选新增清单 vs 机械构造真值的增量质量指标。

指标（精确定义见 references/metrics_definitions.md）：
  precision                 = TP / (TP + FP)            （按去重后的唯一声明计）
  recall                    = TP / |truth_new|
  duplicate_rate            = 重复声明条数 / 候选条目总数
  false_alert_rate          = FP / 唯一声明数            （唯一声明约定下 = 1 - precision）
  backfill_misclassification= 真值 backfill 被报为 new 的条数（FP 的子类），并给出其占 truth_backfill 的比例

计数约定：
  - 候选条目先经 DOI/arXiv/标题规范化，并借助快照记录索引做跨标识符归一
    （同一条文献一次用 DOI 声明、一次用标题声明，仍解析为同一身份，第二次及以后计为重复）。
  - TP/FP/FN 以"唯一声明"为单位；重复条目只进 duplicate 统计，不重复进 TP/FP。
  - TP/FP/FN 逐条列出并带 locator（快照名 + 记录下标 + 标识符），保证可回放、可复算。

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


def entry_keys(e):
    keys = {}
    d = norm_doi(e.get("doi"))
    a = norm_arxiv(e.get("arxiv_id"))
    t = norm_title(e.get("title"))
    if d:
        keys["doi"] = "doi:" + d
    if a:
        keys["arxiv"] = "arxiv:" + a
    if t:
        keys["title"] = "title:" + t
    return keys


def safe_div(a, b):
    return round(a / b, 6) if b else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="候选新增清单的增量质量指标")
    ap.add_argument("--truth", required=True, help="truth_build.py 输出的 truth.json")
    ap.add_argument("--candidates", required=True, help="候选新增清单 JSON（数组或含 items 字段）")
    ap.add_argument("--aligned", default=None, help="可选：aligned.json，用于跨标识符归一与 FP 原因细分")
    ap.add_argument("--out", required=True, help="输出 metrics.json 路径")
    args = ap.parse_args(argv)

    truth = load_json(args.truth)
    cdoc = load_json(args.candidates)
    entries = cdoc if isinstance(cdoc, list) else cdoc.get("items") or cdoc.get("records") or []

    # 真值映射：canonical_key -> 真值条目
    new_map = {it["canonical_key"]: it for it in truth.get("truth_new", [])}
    bf_map = {it["canonical_key"]: it for it in truth.get("truth_backfill", [])}
    ow_map = {it["canonical_key"]: it for it in truth.get("truth_out_of_window", [])}
    uc_map = {it["canonical_key"]: it for it in truth.get("unclassifiable", [])}

    # 快照记录索引：任一可用键 -> 主键；主键 -> 所属侧
    key2pk = {}
    prev_pks, now_pks = set(), set()
    if args.aligned:
        aligned = load_json(args.aligned)
        for side_name, pks in (("records_prev", prev_pks), ("records_now", now_pks)):
            for it in aligned.get(side_name, []):
                pks.add(it["primary_key"])
                for k in it.get("keys", {}).values():
                    key2pk.setdefault(k, it["primary_key"])
    else:
        # 无 aligned 时退化为仅用真值条目建索引（无法识别"已在 t_prev 中"类 FP）
        for m in (new_map, bf_map, ow_map, uc_map):
            for pk, it in m.items():
                now_pks.add(pk)
                for k in entry_keys(it).values():
                    key2pk.setdefault(k, pk)

    tp_items, fp_items, duplicates = [], [], []
    seen = {}
    unique_claims = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            e = {"_raw": e}
        eks = entry_keys(e)
        ident = None
        for k in ("doi", "arxiv", "title"):
            if eks.get(k) and eks[k] in key2pk:
                ident = key2pk[eks[k]]
                break
        resolved = ident is not None
        if not resolved:
            ident = eks.get("doi") or eks.get("arxiv") or eks.get("title") or ("unresolvable:%d" % i)
        claim_info = {"candidate_index": i, "claimed": {k: e.get(k) for k in ("doi", "arxiv_id", "title") if e.get(k)}}
        if ident in seen:
            duplicates.append({
                "identity": ident,
                "candidate_index": i,
                "first_candidate_index": seen[ident],
                **claim_info,
            })
            continue
        seen[ident] = i
        unique_claims.append(ident)
        if ident in new_map:
            tp_items.append({"canonical_key": ident, "locator": new_map[ident]["locator"], **claim_info})
        else:
            if ident in bf_map:
                reason = "backfill_misreported_as_new"
                loc = bf_map[ident]["locator"]
            elif ident in ow_map:
                reason = "out_of_window"
                loc = ow_map[ident]["locator"]
            elif ident in uc_map:
                reason = "truth_unclassifiable_date"
                loc = uc_map[ident]["locator"]
            elif resolved and ident in prev_pks:
                reason = "already_in_prev_snapshot"
                loc = None
            elif resolved:
                reason = "in_snapshot_but_not_truth_new"
                loc = None
            else:
                reason = "not_in_snapshot"
                loc = None
            fp_items.append({"canonical_key": ident, "fp_reason": reason, "locator": loc, **claim_info})

    claimed = set(unique_claims)
    fn_items = [{"canonical_key": pk, "locator": it["locator"],
                 "doi": it.get("doi"), "arxiv_id": it.get("arxiv_id"), "title": it.get("title")}
                for pk, it in new_map.items() if pk not in claimed]

    tp, fp, fn = len(tp_items), len(fp_items), len(fn_items)
    n_entries = len(entries)
    n_unique = len(unique_claims)
    bf_mis = sum(1 for x in fp_items if x["fp_reason"] == "backfill_misreported_as_new")

    out = {
        "definitions_version": "1.0",
        "counts": {
            "candidate_entries": n_entries,
            "unique_claims": n_unique,
            "duplicates": len(duplicates),
            "tp": tp, "fp": fp, "fn": fn,
            "truth_new": len(new_map),
            "truth_backfill": len(bf_map),
            "truth_out_of_window": len(ow_map),
            "truth_unclassifiable": len(uc_map),
            "backfill_misreported_as_new": bf_mis,
        },
        "metrics": {
            "precision": safe_div(tp, tp + fp),
            "recall": safe_div(tp, len(new_map)),
            "duplicate_rate": safe_div(len(duplicates), n_entries),
            "false_alert_rate": safe_div(fp, n_unique),
            "backfill_misclassification_count": bf_mis,
            "backfill_misclassification_rate": safe_div(bf_mis, len(bf_map)),
        },
        "tp_items": tp_items,
        "fp_items": fp_items,
        "fn_items": fn_items,
        "duplicate_items": duplicates,
        "tp_keys": [x["canonical_key"] for x in tp_items],
        "fp_keys": [x["canonical_key"] for x in fp_items],
        "fn_keys": [x["canonical_key"] for x in fn_items],
        "window": truth.get("window"),
    }
    dump_json(args.out, out)
    print("metrics: TP=%d FP=%d FN=%d dup=%d | P=%s R=%s dupR=%s FAR=%s bfMis=%d"
          % (tp, fp, fn, len(duplicates),
             out["metrics"]["precision"], out["metrics"]["recall"],
             out["metrics"]["duplicate_rate"], out["metrics"]["false_alert_rate"], bf_mis))
    return 0


if __name__ == "__main__":
    sys.exit(main())
