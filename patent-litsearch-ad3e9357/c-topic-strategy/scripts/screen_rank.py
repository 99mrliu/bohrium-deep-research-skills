#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
screen_rank.py — PRISMA 式筛选 + 文档化特征排序 + 遗漏说明

两阶段：
  查全阶段：search_corpus.py 宽式召回（任意概念块/分类号命中即入池），记录召回数；
  查准阶段：逐条纳入/排除——排除必须给理由代码（E1-E7），纳入必须给相关性依据（I1-I4）。
PRISMA 计数（识别/去重/初筛/排除/纳入）由脚本从数据重算；
若提供 --expect 自报数且与重算不一致 → exit 3。
排序特征（满分 100，定义见 rules/screening_protocol.md）：
  block_coverage(≤40) + field_strength(≤30) + class_overlap(≤15) + year_proximity(≤15)。

用法：
  python3 screen_rank.py --query query.json --hits hits.json --out screening.json
                         [--min-blocks N] [--expect expect.json] [--decisions override.json]
退出码：0 成功；2 人工决定文件非法；3 PRISMA 自报不一致；1 其他错误。
"""
import argparse
import json
import sys

REASON_EXCLUDE = {
    "E1": "主题不相关（命中为偶然共现）",
    "E2": "文献类型不符（非目标轨道/非技术文献）",
    "E3": "重复或同族冗余",
    "E4": "时间范围外",
    "E5": "语言或全文不可读",
    "E6": "信息不足无法判断",
    "E7": "概念块覆盖不足（查准阶段未达阈值）",
}
REASON_INCLUDE = {
    "I1": "覆盖阈值以上概念块",
    "I2": "分类号与检索式分面重合",
    "I3": "关键字段命中（权利要求/标题）",
    "I4": "号码精确匹配",
}
FIELD_WEIGHTS = {"claims": 30, "claim": 30, "title": 25, "abstract": 20,
                 "description": 15, "ipc": 15, "cpc": 15, "classification": 15,
                 "classifications": 15, "applicant": 10, "assignee": 10, "_text": 10}


def ref_of(hit):
    return "%s#%s" % (hit["file"], hit["loc"])


def matched_fields(hit):
    fs = set()
    for flds in hit.get("blocks_matched", {}).values():
        fs.update(flds.keys())
    if hit.get("classification_matched"):
        fs.add("classification")
    return fs


def decide(hits, query, min_blocks=None, overrides=None):
    blocks = query.get("blocks", [])
    total = len(blocks)
    mode = query.get("mode", "topic")
    hit_blocks_all = set()
    for h in hits:
        hit_blocks_all.update(h.get("blocks_matched", {}).keys())
    if min_blocks is None:
        # 默认阈值：语料中至少命中过一次的块数（避免零结果概念块误杀全部候选）
        threshold = max(1, len(hit_blocks_all))
    else:
        threshold = max(1, min_blocks)
    decisions = []
    for h in hits:
        n = len(h.get("blocks_matched", {}))
        ref = ref_of(h)
        ov = (overrides or {}).get(ref)
        if ov:
            decisions.append(ov)
            continue
        if mode == "number_lookup":
            decisions.append({"ref": ref, "title": h.get("title", ""), "track": h["track"],
                              "decision": "include", "reason_codes": ["I4"],
                              "rationale": "号码精确匹配：%s" % h.get("identifier", "")})
            continue
        cls_m = h.get("classification_matched") or []
        include = (n >= threshold) or (cls_m and n >= 1)
        if include:
            codes = ["I1" if n >= threshold else "I2"]
            if cls_m and "I2" not in codes:
                codes.append("I2")
            if matched_fields(h) & {"claims", "claim", "title"}:
                codes.append("I3")
            rationale = "覆盖 %d/%d 概念块（阈值 %d）" % (n, total, threshold)
            if cls_m:
                rationale += "；分类号重合: %s" % ", ".join(cls_m)
            decisions.append({"ref": ref, "title": h.get("title", ""), "track": h["track"],
                              "decision": "include", "reason_codes": codes,
                              "rationale": rationale})
        else:
            missing = [b.get("name", "?") for b in blocks
                       if b.get("name", "?") not in h.get("blocks_matched", {})]
            decisions.append({"ref": ref, "title": h.get("title", ""), "track": h["track"],
                              "decision": "exclude", "reason_codes": ["E7"],
                              "rationale": "查准阶段未达阈值：命中 %d/%d 块（阈值 %d），缺少块 %s"
                              % (n, total, threshold, missing)})
    return decisions, threshold


def score_hit(hit, query):
    blocks = query.get("blocks", [])
    total = max(1, len(blocks))
    n = len(hit.get("blocks_matched", {}))
    block_coverage = round(40.0 * n / total, 1)
    fs = matched_fields(hit)
    field_strength = max([FIELD_WEIGHTS.get(f, 5) for f in fs], default=0)
    if hit.get("classification_matched"):
        field_strength = min(30, field_strength + 5)
    class_overlap = 15 if hit.get("classification_matched") else 0
    facets = query.get("facets") or {}
    yr = facets.get("year_range")
    year = hit.get("year")
    if not yr:
        year_proximity = 5  # 无年份分面：中性分
    elif year is None:
        year_proximity = 5  # 年份未知：中性分，如实不奖惩
    elif int(str(yr[0])) <= year <= int(str(yr[1])):
        year_proximity = 15
    elif abs(year - int(str(yr[0]))) <= 2 or abs(year - int(str(yr[1]))) <= 2:
        year_proximity = 8
    else:
        year_proximity = 0
    total_score = round(min(100.0, block_coverage + field_strength + class_overlap + year_proximity), 1)
    return {"score": total_score,
            "breakdown": {"block_coverage": block_coverage,
                          "field_strength": field_strength,
                          "class_overlap": class_overlap,
                          "year_proximity": year_proximity}}


def validate_overrides(ov_list):
    """人工决定文件：排除必须给理由代码，纳入必须给相关性依据。非法返回错误列表。"""
    errors = []
    table = {}
    for i, d in enumerate(ov_list):
        ref = d.get("ref")
        if not ref:
            errors.append("decisions[%d]: 缺 ref（file#loc）" % i)
            continue
        dec = d.get("decision")
        codes = d.get("reason_codes") or []
        if dec == "exclude":
            bad = [c for c in codes if c not in REASON_EXCLUDE]
            if not codes or bad:
                errors.append("%s: 排除必须给 E1-E7 理由代码，实际 %s" % (ref, codes))
        elif dec == "include":
            bad = [c for c in codes if c not in REASON_INCLUDE]
            if not codes or bad:
                errors.append("%s: 纳入必须给 I1-I4 依据代码，实际 %s" % (ref, codes))
            if not (d.get("rationale") or "").strip():
                errors.append("%s: 纳入必须给相关性依据 rationale" % ref)
        else:
            errors.append("%s: decision 必须是 include/exclude" % ref)
        table[ref] = d
    return table, errors


def run(query, hits_doc, min_blocks=None, expect=None, overrides_list=None):
    overrides, ov_errors = ({}, [])
    if overrides_list is not None:
        overrides, ov_errors = validate_overrides(overrides_list)
        if ov_errors:
            return None, ov_errors, 2
    hits = hits_doc.get("hits", [])
    decisions, threshold = decide(hits, query, min_blocks, overrides)
    included = [d for d in decisions if d["decision"] == "include"]
    excluded = [d for d in decisions if d["decision"] == "exclude"]

    hit_by_ref = {ref_of(h): h for h in hits}
    ranking = []
    for d in decisions:
        h = hit_by_ref[d["ref"]]
        sc = score_hit(h, query)
        ranking.append({"ref": d["ref"], "title": d.get("title", ""), "track": d["track"],
                        "decision": d["decision"], "score": sc["score"],
                        "breakdown": sc["breakdown"]})
    ranking.sort(key=lambda x: -x["score"])

    prisma = {"identified": hits_doc.get("corpus", {}).get("records_total", 0),
              "duplicates_removed": hits_doc.get("dedup", {}).get("duplicates_removed", 0),
              "screened": len(hits),
              "excluded": len(excluded),
              "included": len(included)}
    # 脚本重算与自报数比对
    if expect:
        mism = {k: {"expect": v, "actual": prisma.get(k)}
                for k, v in expect.items() if prisma.get(k) != v}
        if mism:
            return None, ["PRISMA 自报数与重算不一致: %s" % json.dumps(mism, ensure_ascii=False)], 3

    omissions = {
        "zero_hit_blocks": hits_doc.get("zero_hit_blocks", []),
        "unclassified_records": hits_doc.get("unclassified", []),
        "skipped_files": hits_doc.get("corpus", {}).get("skipped", []),
        "notes": [
            "仅覆盖本地提供语料，未访问外部数据库（Derwent/Orbit/CNKI 等），存在来源遗漏风险。",
            "观察到的链接/引用不构成完整同族，同族合并以语料内字段为准。",
            "当前官方法律状态未核验，法律状态结论不得写入确定字段。",
        ],
    }
    return {"threshold_blocks": threshold,
            "recall_stage": {"broad_recall": len(hits) + prisma["duplicates_removed"],
                             "after_dedup": len(hits)},
            "precision_stage": {"threshold_blocks": threshold},
            "decisions": decisions,
            "prisma": prisma,
            "ranking": ranking,
            "omissions": omissions,
            "reason_code_tables": {"exclude": REASON_EXCLUDE, "include": REASON_INCLUDE}}, [], 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="PRISMA 式筛选与排序")
    ap.add_argument("--query", required=True)
    ap.add_argument("--hits", required=True)
    ap.add_argument("--out", help="筛选结果 JSON 输出路径（缺省打印到 stdout）")
    ap.add_argument("--min-blocks", type=int, default=None, help="查准阈值（覆盖块数）")
    ap.add_argument("--expect", help="自报 PRISMA 计数 JSON（不一致则 exit 3）")
    ap.add_argument("--decisions", help="人工决定覆写 JSON（排除须理由代码/纳入须依据）")
    args = ap.parse_args(argv)

    try:
        with open(args.query, encoding="utf-8") as f:
            query = json.load(f)
        with open(args.hits, encoding="utf-8") as f:
            hits_doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write("无法读取输入: %s\n" % e)
        return 1
    expect = None
    if args.expect:
        try:
            with open(args.expect, encoding="utf-8") as f:
                expect = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            sys.stderr.write("无法读取 expect: %s\n" % e)
            return 1
    overrides = None
    if args.decisions:
        try:
            with open(args.decisions, encoding="utf-8") as f:
                overrides = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            sys.stderr.write("无法读取 decisions: %s\n" % e)
            return 1

    result, errors, code = run(query, hits_doc, args.min_blocks, expect, overrides)
    if errors:
        for e in errors:
            sys.stderr.write(e + "\n")
        return code
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        p = result["prisma"]
        sys.stderr.write("PRISMA: 识别 %d / 去重 %d / 初筛 %d / 排除 %d / 纳入 %d；结果已写入 %s\n"
                         % (p["identified"], p["duplicates_removed"], p["screened"],
                            p["excluded"], p["included"], args.out))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
