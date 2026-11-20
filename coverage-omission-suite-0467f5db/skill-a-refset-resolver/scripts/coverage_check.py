#!/usr/bin/env python3
"""coverage_check.py — 步骤⑦⑧：覆盖测量与漏检清单。

以冻结的 reference_set.json 为分母，将检索结果记录按规范化 DOI/PMID 精确
匹配，再按标题相似度回退匹配，逐条输出 hit/miss、match_level 与证据指针，
产出 coverage.json 与 miss_list.csv。

分母一经冻结不得改动；匹配不上即为 miss，不因"找不到"而丢弃。

退出码：0 正常；2 检索结果缺失（诚实降级）；3 参考集缺失。仅标准库。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

SCRIPT_NAME = "coverage_check.py"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from refset_build import norm_doi, norm_pmid, norm_title_key, jaccard  # noqa: E402

TITLE_SIM_THRESHOLD = 0.85


def load_results(path):
    """兼容多种检索结果容器格式。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "records", "items", "hits", "papers"):
            if isinstance(data.get(key), list):
                return data[key]
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="以冻结参考集为分母测量检索覆盖，输出漏检清单。")
    ap.add_argument("--workdir", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--results", required=True,
                    help="检索结果 JSON 文件（list 或含 results/records/items 键）")
    ap.add_argument("--sim", type=float, default=TITLE_SIM_THRESHOLD,
                    help="标题相似度回退匹配阈值（默认 0.85）")
    args = ap.parse_args(argv)

    refset_path = os.path.join(args.outdir, "reference_set.json")
    if not os.path.isfile(refset_path):
        print(f"[{SCRIPT_NAME}] 缺少冻结参考集 {refset_path}，请先运行 refset_build.py",
              file=sys.stderr)
        return 3
    with open(refset_path, "r", encoding="utf-8") as fh:
        refset = json.load(fh)
    case_id = refset.get("case_id", "unknown_case")
    records = refset.get("records", [])
    denominator = len(records)
    limitations = []
    status = "complete"

    results_usable = True
    if not os.path.isfile(args.results):
        limitations.append(f"检索结果文件缺失：{args.results}；覆盖率无法计算。")
        status = "partial"
        results = []
        results_usable = False
    else:
        results = load_results(args.results)
        if results is None:
            limitations.append(f"检索结果文件无法解析：{args.results}")
            status = "partial"
            results = []
            results_usable = False
        elif not results:
            limitations.append("检索结果为空（0 条），覆盖率按 0 计，请确认非解析故障。")

    # 结果记录索引：标识符→记录指针
    res_by_doi, res_by_pmid = {}, {}
    for i, r in enumerate(results):
        if not isinstance(r, dict):
            continue
        doi = norm_doi(r.get("doi") or r.get("DOI"))
        pmid = norm_pmid(r.get("pmid") or r.get("PMID"))
        if doi:
            res_by_doi.setdefault(doi, i)
        if pmid:
            res_by_pmid.setdefault(pmid, i)

    coverage = []
    miss_rows = []
    for e in records:
        ref_id = e.get("ref_id")
        hit, level, evidence = None, None, None
        if e.get("doi") and e["doi"] in res_by_doi:
            i = res_by_doi[e["doi"]]
            hit, level = i, "identifier_doi"
            evidence = {"matched_result_index": i, "matched_doi": e["doi"],
                        "result_title": str(results[i].get("title", ""))[:160]}
        elif e.get("pmid") and e["pmid"] in res_by_pmid:
            i = res_by_pmid[e["pmid"]]
            hit, level = i, "identifier_pmid"
            evidence = {"matched_result_index": i, "matched_pmid": e["pmid"],
                        "result_title": str(results[i].get("title", ""))[:160]}
        else:
            # 标题相似度回退
            tk = norm_title_key(e.get("title", ""))
            best_i, best_sim = None, 0.0
            for i, r in enumerate(results):
                if not isinstance(r, dict):
                    continue
                sim = jaccard(tk, norm_title_key(str(r.get("title", ""))))
                if sim > best_sim:
                    best_i, best_sim = i, sim
            if best_i is not None and best_sim >= args.sim:
                hit, level = best_i, "title_similarity"
                evidence = {"matched_result_index": best_i,
                            "similarity": round(best_sim, 3),
                            "result_title": str(results[best_i].get("title", ""))[:160],
                            "caveat": "回退匹配，建议人工复核"}
        row = {
            "ref_id": ref_id,
            "title": e.get("title", "")[:160],
            "usable": e.get("usable", True),
            "status": "hit" if hit is not None else "miss",
            "match_level": level,
            "evidence": evidence,
        }
        coverage.append(row)
        if hit is None:
            miss_rows.append({
                "ref_id": ref_id, "title": e.get("title", ""),
                "doi": e.get("doi") or "", "pmid": e.get("pmid") or "",
                "year": e.get("year") or "", "journal": e.get("journal") or "",
                "source": ";".join(e.get("source", [])),
                "flags": ";".join(e.get("flags", [])),
            })

    hits = sum(1 for c in coverage if c["status"] == "hit")
    misses = denominator - hits
    ratio = round(hits / denominator, 4) if denominator else None
    if not results_usable:
        hits = None
        misses = None
        ratio = None

    payload = {
        "case_id": case_id,
        "generated_by": SCRIPT_NAME,
        "denominator": denominator,
        "hit": hits,
        "miss": misses,
        "coverage_ratio": ratio,
        "denominator_policy": refset.get("denominator_policy"),
        "title_sim_threshold": args.sim,
        "records": coverage,
        "status": status,
        "limitations": limitations,
    }
    with open(os.path.join(args.outdir, "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    miss_path = os.path.join(args.outdir, "miss_list.csv")
    with open(miss_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ref_id", "title", "doi", "pmid",
                                           "year", "journal", "source", "flags"])
        w.writeheader()
        for r in miss_rows:
            w.writerow(r)

    print(f"[{SCRIPT_NAME}] denominator={denominator} hit={hits} miss={misses} "
          f"ratio={ratio} status={status}")
    for lim in limitations:
        print(f"  limitation: {lim}", file=sys.stderr)
    return 0 if status != "failed" else 2


if __name__ == "__main__":
    sys.exit(main())
