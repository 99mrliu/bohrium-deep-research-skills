#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudication_engine.py -- 命中判定仪器标定与覆盖闭环（skill-b-adjudication-calibrator）。

重心：判定规则是一台"测量仪器"，先标定再使用。
  1. 规则版本化：L1 标识符精确匹配 / L2 标题+年份近似匹配 / L3 人工裁决队列，
     全部参数集中在 RULE_SPEC（与 references/match_rule_spec.md 同步）；
  2. 标定：若材料中含带标签的标定片段（calibration fragment），仪器先在片段上
     跑混淆矩阵（TP/FP/FN/TN）、Wilson 95% 置信区间与阈值扫描，产出
     calibration_report.json；无标定片段则诚实声明"未标定"，使用默认阈值并
     把该事实写入 uncertainty；
  3. 主判定：参考集 × 检索结果逐条裁决，L2 判定附带相似度分值与判定置信度，
     落入灰区的记录进入 L3 队列而不是强行判定；
  4. 闭环：漏检归因、补检建议、result.json 组装。

仅 Python 标准库。退出码：0 完成；2 材料不足（partial）；3 契约字段缺失。
"""
import argparse
import datetime
import json
import math
import os
import re
import sys

VERSION = "1.0.0"

RULE_SPEC = {
    "spec_version": "2026.11",
    "L1": {"kind": "identifier_exact", "fields": ["doi", "pmid"], "decision": "hit"},
    "L2": {"kind": "title_year_fuzzy", "jaccard_threshold": 0.80,
           "gray_zone": [0.65, 0.80], "year_must_match": True,
           "decision": "hit if >= threshold; L3 queue if in gray zone"},
    "L3": {"kind": "manual_queue", "decision": "defer; never auto-judge"},
}

# ---------------------------------------------------------------- 工具

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_doi(doi):
    if not doi:
        return ""
    d = str(doi).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip().rstrip(".")


def norm_title(t):
    t = re.sub(r"[^a-z0-9 ]+", " ", str(t or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def tokens(t):
    stop = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "by"}
    return [x for x in norm_title(t).split() if x not in stop]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def first_year(rec):
    for k in ("year", "published", "issued", "date"):
        v = rec.get(k)
        if v is None:
            continue
        m = re.search(r"(?:19|20)\d{2}", str(v))
        if m:
            return int(m.group(0))
    return None


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def wilson(k, n, z=1.96):
    """Wilson score interval for binomial proportion k/n."""
    if n == 0:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = (z / den) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)]


# ---------------------------------------------------------------- 裁决核心

def adjudicate_pair(ref, cand, threshold=None):
    """返回 (decision, level, score)。decision ∈ hit / miss / defer_L3。"""
    thr = threshold if threshold is not None else RULE_SPEC["L2"]["jaccard_threshold"]
    lo, hi = RULE_SPEC["L2"]["gray_zone"]
    rd, cd = norm_doi(ref.get("doi")), norm_doi(cand.get("doi"))
    if rd and cd:
        return ("hit", "L1_doi", 1.0) if rd == cd else ("miss", "L1_doi_conflict", 0.0)
    rp, cp = str(ref.get("pmid") or ""), str(cand.get("pmid") or "")
    if rp and cp:
        return ("hit", "L1_pmid", 1.0) if rp == cp else ("miss", "L1_pmid_conflict", 0.0)
    score = jaccard(tokens(ref.get("title")), tokens(cand.get("title")))
    ry, cy = first_year(ref), first_year(cand)
    year_ok = (not RULE_SPEC["L2"]["year_must_match"]) or (not ry or not cy or ry == cy)
    if score >= thr and year_ok:
        return ("hit", "L2_title_year", round(score, 4))
    if lo <= score < hi and year_ok:
        return ("defer_L3", "L2_gray_zone", round(score, 4))
    return ("miss", "L2_below", round(score, 4))


def best_candidate(ref, cands, threshold=None):
    best, best_s, best_d = None, -1.0, ("miss", None, 0.0)
    for c in cands:
        d = adjudicate_pair(ref, c, threshold)
        if d[2] > best_s:
            best, best_s, best_d = c, d[2], d
        if d[0] == "hit" and d[1].startswith("L1"):
            return c, d
    return best, best_d


# ---------------------------------------------------------------- 标定

def calibrate(fragment_path, work_dir):
    """在带标签片段上标定仪器。fragment: [{"ref": {...}, "candidate": {...}, "label": "hit"|"miss"}]"""
    frag = load_json(fragment_path)
    if not isinstance(frag, list) or not frag:
        return None
    pairs = [p for p in frag if isinstance(p, dict) and p.get("label") in ("hit", "miss")]
    if not pairs:
        return None
    thr_default = RULE_SPEC["L2"]["jaccard_threshold"]
    report = {"fragment": fragment_path, "n_labeled": len(pairs), "spec_version": RULE_SPEC["spec_version"],
              "default_threshold": thr_default, "confusion_at_default": None, "threshold_sweep": []}
    for thr in [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
        tp = fp = fn = tn = defer = 0
        for p in pairs:
            decision, level, _s = adjudicate_pair(p["ref"], p["candidate"], threshold=thr)
            lab = p["label"]
            if decision == "defer_L3":
                defer += 1
                continue
            pred = "hit" if decision == "hit" else "miss"
            if pred == "hit" and lab == "hit":
                tp += 1
            elif pred == "hit" and lab == "miss":
                fp += 1
            elif pred == "miss" and lab == "hit":
                fn += 1
            else:
                tn += 1
        row = {"threshold": thr, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "deferred": defer,
               "precision": round(tp / (tp + fp), 4) if tp + fp else None,
               "recall": round(tp / (tp + fn), 4) if tp + fn else None,
               "precision_wilson95": wilson(tp, tp + fp),
               "recall_wilson95": wilson(tp, tp + fn)}
        report["threshold_sweep"].append(row)
        if abs(thr - thr_default) < 1e-9:
            report["confusion_at_default"] = row
    # 标定结论：仅当某阈值在片段上严格优于默认（F1 更高且样本足够）才建议调整，否则保持默认
    def f1(r):
        if not r["precision"] or not r["recall"]:
            return 0.0
        return 2 * r["precision"] * r["recall"] / (r["precision"] + r["recall"])
    best = max(report["threshold_sweep"], key=f1)
    f1_def = f1(report["confusion_at_default"])
    strictly_better = f1(best) > f1_def and best["threshold"] != thr_default and len(pairs) >= 30
    report["recommended_threshold"] = best["threshold"] if strictly_better else thr_default
    report["recommendation_note"] = (
        "fragment suggests threshold %.2f (F1 %.3f vs default %.3f); recommendation only, "
        "main adjudication keeps frozen spec unless operator approves" % (best["threshold"], f1(best), f1_def)
        if strictly_better else
        "keep default %.2f: no threshold strictly dominates (or fragment < 30 pairs)" % thr_default)
    dump_json(os.path.join(work_dir, "calibration_report.json"), report)
    return report


# ---------------------------------------------------------------- 材料解析（最小充分）

def parse_bib_csv(path):
    import csv as _csv
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for i, row in enumerate(_csv.DictReader(fh)):
            r = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if r:
                out.append({"record": r, "origin": "%s:row%d" % (path, i + 2)})
    return out


def collect_inputs(input_dir):
    refs, hits, queries, frag = [], [], [], None
    for root, _d, names in os.walk(input_dir):
        for name in sorted(names):
            p = os.path.join(root, name)
            if not os.path.isfile(p) or os.path.islink(p):
                continue
            low = name.lower()
            if low in ("case.json", "task.md"):
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(8192)
            except Exception:
                continue
            if "calibration" in low and low.endswith(".json"):
                frag = p
            elif re.search(r'"(queries|searches)"\s*:', head) and re.search(r'"(hits|results|records)"\s*:', head):
                data = load_json(p) or {}
                for q in data.get("queries") or data.get("searches") or []:
                    queries.append(q)
                    for h in q.get("hits") or q.get("results") or q.get("records") or []:
                        if isinstance(h, dict):
                            hh = dict(h)
                            hh["_query_id"] = q.get("query_id") or q.get("id")
                            hh["_source"] = q.get("source") or q.get("database") or ""
                            hits.append(hh)
            elif low.endswith(".csv"):
                refs.extend(parse_bib_csv(p))
            elif low.endswith((".json", ".jsonl")) and re.search(r'"(reference|bibliography|known)', low + head[:200], re.I):
                data = load_json(p)
                items = data if isinstance(data, list) else (data or {}).get("references") or []
                for i, it in enumerate(items):
                    if isinstance(it, dict):
                        refs.append({"record": it, "origin": "%s:item%d" % (p, i)})
    return refs, hits, queries, frag


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="命中判定仪器：标定 -> 裁决 -> 覆盖闭环")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)

    case = load_json(os.path.join(args.input, "case.json"), {}) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown-case"
    oc = case.get("output_contract") or {}
    if isinstance(oc, dict):
        contract = list(oc.get("required_fields") or oc.get("fields") or oc.keys())
    elif isinstance(oc, list):
        contract = [str(x) for x in oc]
    else:
        contract = []
    if not contract:
        contract = ["rule_spec", "calibration", "coverage", "miss_list", "supplement_log", "coverage_report"]

    status, uncertainty, change_log = "complete", [], []

    refs_raw, hits, queries, frag = collect_inputs(args.input)
    # 冻结参考集（基础治理：去重 + 撤稿线索标记；深度取证非本技能重心）
    refset, seen = [], {}
    for c in refs_raw:
        r = c["record"]
        key = norm_doi(r.get("doi")) or norm_title(r.get("title"))[:80]
        if key and key in seen:
            change_log.append({"ts": now_iso(), "event": "dedup_merge", "merged": c["origin"]})
            continue
        if key:
            seen[key] = 1
        refset.append({"ref_id": "R%03d" % (len(refset) + 1), "doi": r.get("doi"),
                       "pmid": r.get("pmid"), "title": r.get("title", ""),
                       "year": first_year(r), "container": r.get("container", ""),
                       "origin": c["origin"],
                       "usable": not r.get("retracted")})
    if not refset:
        status = "partial"
        change_log.append({"ts": now_iso(), "event": "no_reference_records"})

    # 1) 标定
    calib = calibrate(frag, args.work) if frag else None
    if calib is None:
        uncertainty.append("no labeled calibration fragment in materials; instrument used at default "
                           "threshold %.2f WITHOUT empirical calibration" % RULE_SPEC["L2"]["jaccard_threshold"])

    # 2) 主裁决
    per_record, l3_queue = [], []
    for rec in refset:
        if not rec["usable"]:
            per_record.append({"ref_id": rec["ref_id"], "status": "excluded", "reason": "retracted/unusable"})
            continue
        cand, (decision, level, score) = best_candidate(rec, hits)
        row = {"ref_id": rec["ref_id"], "doi": rec.get("doi"), "title": rec["title"][:140],
               "status": decision, "match_level": level, "score": score,
               "evidence": ({"query_id": cand.get("_query_id"), "source": cand.get("_source"),
                             "matched_title": str(cand.get("title", ""))[:140]} if cand and decision != "miss" else None)}
        if decision == "defer_L3":
            l3_queue.append({"ref_id": rec["ref_id"], "best_candidate_title": str((cand or {}).get("title", ""))[:140],
                             "score": score, "note": "gray-zone similarity; requires human adjudication"})
            row["status"] = "miss"  # 灰区保守计为 miss，避免高估覆盖率
            row["conservative_note"] = "deferred to L3; counted as miss pending adjudication"
        per_record.append(row)
    usable = [r for r in per_record if r["status"] != "excluded"]
    hit_n = sum(1 for r in usable if r["status"] == "hit")
    coverage = {"denominator": len(usable), "hit": hit_n, "miss": len(usable) - hit_n,
                "coverage_ratio": round(hit_n / len(usable), 4) if usable else None,
                "coverage_ratio_wilson95": wilson(hit_n, len(usable)),
                "instrument": {"spec_version": RULE_SPEC["spec_version"],
                               "threshold": RULE_SPEC["L2"]["jaccard_threshold"],
                               "calibrated": calib is not None},
                "per_record": per_record, "l3_queue": l3_queue}
    dump_json(os.path.join(args.work, "adjudication_ledger.json"), coverage)

    # 3) 漏检归因（基于查询要素的轻量探针）
    qstr = " | ".join(str(q.get("query_string") or q.get("query") or "") for q in queries).lower()
    windows = [str(q.get("time_window") or q.get("years") or "") for q in queries]
    miss_list = []
    for r in per_record:
        if r["status"] != "miss":
            continue
        rec = next((x for x in refset if x["ref_id"] == r["ref_id"]), {})
        causes = []
        toks = [t for t in tokens(rec.get("title")) if len(t) > 5]
        missing = [t for t in toks if t not in qstr]
        if missing and qstr:
            causes.append({"category": "query_term_missing", "evidence": "tokens absent from queries: %s" % ", ".join(missing[:5])})
        for w in windows:
            yrs = [int(y) for y in re.findall(r"(?:19|20)\d{2}", w)]
            if rec.get("year") and len(yrs) >= 2 and not (min(yrs) <= rec["year"] <= max(yrs)):
                causes.append({"category": "time_window_cutoff", "evidence": "year %s outside %s" % (rec["year"], w)})
        if not rec.get("doi") and not rec.get("pmid"):
            causes.append({"category": "identifier_anomaly", "evidence": "no resolvable identifier"})
        if r.get("conservative_note"):
            causes.append({"category": "adjudication_uncertain", "evidence": r["conservative_note"]})
        if not causes:
            causes.append({"category": "unresolved", "evidence": "needs manual review"})
        dedup = {c["category"]: c for c in causes}
        miss_list.append({"ref_id": r["ref_id"], "title": r["title"], "causes": list(dedup.values())})

    # 4) 补检建议
    supp = [{"target_ref": m["ref_id"],
             "action": {"query_term_missing": "new_query", "time_window_cutoff": "extend_window",
                        "identifier_anomaly": "manual_identifier_repair"}.get(m["causes"][0]["category"], "manual_review"),
             "rationale": m["causes"][0]["evidence"]} for m in miss_list]
    supplement = {"executed": False, "suggestions": supp,
                  "note": "suggestions only; rerun with supplemental results to verify omission reduction"}

    # 5) 报告
    lines = ["# 覆盖率报告（判定仪器标定版）", "",
             "- case_id: `%s`" % case_id,
             "- 仪器：规则规范 %s，L2 阈值 %.2f，标定状态：%s" % (
                 RULE_SPEC["spec_version"], RULE_SPEC["L2"]["jaccard_threshold"],
                 "已标定" if calib else "未标定（无标定片段）"),
             "- 分母 %d / 命中 %d / 漏检 %d，覆盖率 %.4f，Wilson95 %s" % (
                 coverage["denominator"], coverage["hit"], coverage["miss"],
                 coverage["coverage_ratio"] or 0.0, coverage["coverage_ratio_wilson95"]),
             "- L3 人工裁决队列：%d 条（保守计入 miss）" % len(l3_queue), ""]
    if calib:
        cd0 = calib["confusion_at_default"] or {}
        lines += ["## 标定摘要", "",
                  "- 标定片段 %d 对；默认阈值下 precision=%s recall=%s" % (
                      calib["n_labeled"], cd0.get("precision"), cd0.get("recall")),
                  "- %s" % calib["recommendation_note"], ""]
    lines.append("## 逐条裁决")
    lines += ["", "| ref_id | status | level | score |", "|---|---|---|---|"]
    for r in per_record:
        lines.append("| %s | %s | %s | %s |" % (r["ref_id"], r["status"], r.get("match_level") or "-", r.get("score")))
    report_path = os.path.join(args.output, "coverage_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    artifacts = {"rule_spec": RULE_SPEC, "calibration": calib or {"calibrated": False},
                 "coverage": {k: coverage[k] for k in ("denominator", "hit", "miss", "coverage_ratio",
                                                       "coverage_ratio_wilson95", "instrument")},
                 "miss_list": miss_list, "supplement_log": supplement, "coverage_report": report_path,
                 "l3_queue": l3_queue}
    sources = []
    for root, _d, names in os.walk(args.input):
        for n in sorted(names):
            p = os.path.join(root, n)
            if os.path.isfile(p):
                sources.append({"path": p})
    result = {"case_id": case_id, "status": status, "sources": sources,
              "uncertainty": uncertainty, "change_log": change_log,
              "skill": "adjudication-instrument-calibrator", "skill_version": VERSION}
    for f in contract:
        result[f] = artifacts.get(f)
    dump_json(os.path.join(args.output, "result.json"), result)
    missing = [f for f in contract if result.get(f) is None]
    if missing:
        print("contract fields unresolved: %s" % missing, file=sys.stderr)
        return 3
    return 2 if status == "partial" else 0


if __name__ == "__main__":
    sys.exit(main())
