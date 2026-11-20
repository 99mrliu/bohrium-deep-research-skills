#!/usr/bin/env python3
"""hit_matrix.py — 命中矩阵落盘与覆盖率复算。

读取 work/adjudication.json 与 work/case_normalized.json，生成：
  out/hit_matrix.csv    行＝参考集条目，列＝(query_id × source × executed_at)，
                        单元＝status:level:score:rank
  out/hit_matrix.json   同内容的结构化版本（单元含 evidence 指针）
  work/coverage.json    覆盖率复算结果：overall / per_source / per_query / Wilson CI /
                        分母与剔除清单

覆盖率仅从命中矩阵复算，不读取任何其他来源；ambiguous 一律不计入命中。

用法:
  python3 hit_matrix.py --work /app/work --out /app/output

退出码: 0 成功; 2 材料不足; 3 校验失败。
仅使用 Python 3 标准库。
"""
import argparse
import csv
import json
import math
import os
import sys


def wilson_interval(k, n, z=1.96):
    """Wilson 得分区间。返回 (lower, upper)。n=0 时返回 (None, None)。

    中心 = (p̂ + z²/2n) / (1 + z²/n)
    半径 = z·√(p̂(1−p̂)/n + z²/4n²) / (1 + z²/n)
    """
    if n <= 0:
        return (None, None)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    margin = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def build_matrix(cells, usable_ref_ids, queries):
    """从判定单元构建矩阵。返回 (ref_ids, col_keys, matrix)。"""
    col_keys = []
    for q in queries:
        key = "%s|%s|%s" % (q.get("query_id"), q.get("source"), q.get("executed_at"))
        if key not in col_keys:
            col_keys.append(key)
    matrix = {rid: {ck: {"status": "miss", "match_level": None, "score": 0.0,
                         "rank_in_results": None, "evidence": None}
                    for ck in col_keys} for rid in usable_ref_ids}
    for c in cells:
        rid = c.get("ref_id")
        ck = c.get("cell_key")
        if rid in matrix and ck in matrix[rid]:
            matrix[rid][ck] = {
                "status": c.get("status"),
                "match_level": c.get("match_level"),
                "score": c.get("score"),
                "rank_in_results": c.get("rank_in_results"),
                "evidence": c.get("evidence"),
            }
    return usable_ref_ids, col_keys, matrix


def compute_coverage(matrix, col_keys, queries):
    """仅从矩阵复算覆盖率。返回 coverage 字典。"""
    ref_ids = list(matrix.keys())
    n = len(ref_ids)

    def ref_hit(rid, keys=None):
        keys = keys if keys is not None else col_keys
        return any(matrix[rid][ck]["status"] == "hit" for ck in keys)

    hit_ids = [rid for rid in ref_ids if ref_hit(rid)]
    k = len(hit_ids)
    lo, hi = wilson_interval(k, n)

    # 分来源：该来源任一列命中
    sources = sorted({ck.split("|")[1] for ck in col_keys})
    per_source = {}
    for s in sources:
        skeys = [ck for ck in col_keys if ck.split("|")[1] == s]
        sk = sum(1 for rid in ref_ids if ref_hit(rid, skeys))
        slo, shi = wilson_interval(sk, n)
        per_source[s] = {"hits": sk, "total": n, "recall": round(sk / n, 6) if n else None,
                         "wilson95": [round(slo, 6), round(hi, 6)] if slo is not None else None}

    # 分查询：按 query_id 聚合
    qmeta = {}
    for q in queries:
        qmeta.setdefault(q.get("query_id"), {"source": q.get("source"),
                                             "query_string": q.get("query_string")})
    per_query = {}
    for qid in sorted(qmeta):
        qkeys = [ck for ck in col_keys if ck.split("|")[0] == qid]
        qk_ = sum(1 for rid in ref_ids if ref_hit(rid, qkeys))
        qlo, qhi = wilson_interval(qk_, n)
        per_query[qid] = {"source": qmeta[qid]["source"],
                          "query_string": qmeta[qid]["query_string"],
                          "hits": qk_, "total": n,
                          "recall": round(qk_ / n, 6) if n else None,
                          "wilson95": [round(qlo, 6), round(qhi, 6)] if qlo is not None else None}

    return {
        "overall": {"hits": k, "total": n,
                    "recall": round(k / n, 6) if n else None,
                    "wilson95": [round(lo, 6), round(hi, 6)] if lo is not None else None},
        "per_source": per_source,
        "per_query": per_query,
        "hit_ref_ids": hit_ids,
        "missed_ref_ids": [rid for rid in ref_ids if rid not in hit_ids],
        "ambiguous_cells": sum(1 for rid in ref_ids for ck in col_keys
                               if matrix[rid][ck]["status"] == "ambiguous"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="命中矩阵落盘（CSV/JSON）与覆盖率复算（含 Wilson 95% 区间）。")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--out", default="/app/output", help="产物目录（默认 /app/output）")
    ap.add_argument("--adjudication", default=None,
                    help="判定文件路径（默认 work/adjudication.json；补检复算时传补检判定文件）")
    ap.add_argument("--suffix", default="",
                    help="输出文件名后缀（补检复算时传 '_after' 等）")
    args = ap.parse_args(argv)

    adj_path = args.adjudication or os.path.join(args.work, "adjudication.json")
    case_path = os.path.join(args.work, "case_normalized.json")
    for p in (adj_path, case_path):
        if not os.path.isfile(p):
            print("ERROR: 缺少输入文件: %s（先运行 parse_case.py 与 adjudicate.py）" % p,
                  file=sys.stderr)
            return 2
    try:
        with open(adj_path, "r", encoding="utf-8") as f:
            adj = json.load(f)
        with open(case_path, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (OSError, ValueError) as e:
        print("ERROR: 输入文件不可解析: %s" % e, file=sys.stderr)
        return 3

    usable = [r for r in case.get("reference_set", []) if r.get("usable", True)]
    usable_ref_ids = [r["ref_id"] for r in usable]
    queries = case.get("search_log", [])
    if not usable_ref_ids or not queries:
        print("ERROR: 可用参考集或检索记录为空", file=sys.stderr)
        return 2

    ref_ids, col_keys, matrix = build_matrix(adj.get("cells", []), usable_ref_ids, queries)
    coverage = compute_coverage(matrix, col_keys, queries)
    coverage["denominator"] = {
        "usable_references": len(usable_ref_ids),
        "excluded": case.get("excluded_references", []),
        "rule": "分母＝冻结参考集中 usable=true 的条目数；撤稿/重复/题录缺失已剔除并公布",
    }

    os.makedirs(args.out, exist_ok=True)
    sfx = args.suffix
    csv_path = os.path.join(args.out, "hit_matrix%s.csv" % sfx)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ref_id", "ref_title"] + col_keys + ["any_hit"])
        title_by_id = {r["ref_id"]: r.get("title", "") for r in usable}
        for rid in ref_ids:
            row = [rid, title_by_id.get(rid, "")]
            for ck in col_keys:
                c = matrix[rid][ck]
                row.append("%s:%s:%.4f:%s" % (
                    c["status"], c["match_level"] or "-", c["score"] or 0.0,
                    c["rank_in_results"] if c["rank_in_results"] else "-"))
            row.append("hit" if rid in coverage["hit_ref_ids"] else "miss")
            w.writerow(row)

    json_path = os.path.join(args.out, "hit_matrix%s.json" % sfx)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"case_id": case.get("case_id"),
                   "columns": col_keys,
                   "rows": ref_ids,
                   "matrix": matrix,
                   "coverage": coverage}, f, ensure_ascii=False, indent=2)

    cov_path = os.path.join(args.work, "coverage%s.json" % sfx)
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)

    ov = coverage["overall"]
    print("hit_matrix: %d 行 × %d 列；覆盖率 %d/%d = %.4f, Wilson95=[%.4f, %.4f]；漏检 %d 条"
          % (len(ref_ids), len(col_keys), ov["hits"], ov["total"],
             ov["recall"] or 0.0, ov["wilson95"][0] or 0.0, ov["wilson95"][1] or 0.0,
             len(coverage["missed_ref_ids"])))
    print("输出: %s ; %s ; %s" % (csv_path, json_path, cov_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
