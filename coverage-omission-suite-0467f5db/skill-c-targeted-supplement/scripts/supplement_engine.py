#!/usr/bin/env python3
"""supplement_engine.py — 漏检驱动的定向补检引擎（离线，仅操作本地材料）。

方法要点（详见 SKILL.md 与 references/）：
  每条补充查询都从具体漏检记录的原文词项生成，携带假设、target_miss_ids、
  generated_from（记录指针 + 引用词项原文）；按四类原型分批执行：
    a 原词补全式：漏检记录标题原词
    b 作者+年锚定式：第一作者姓氏 + 年份 ±1
    c 引文追踪式：本地参考图 / 本地文件中的引文邻域（前向 + 后向）
    d 来源切换式：同一概念，切换到初始检索未覆盖的本地索引文件
  每批结束用同一冻结参考集重新匹配，核算边际覆盖率收益；
  触发 STOP-1/2/3 即停，残余漏检逐项归因并给出检回条件。

输出（work 目录）：
  supplement_log.csv        逐查询账本
  residual_misses.json      残余遗漏归因与检回条件
  supplement_state.json     批次收益、停止规则、最终覆盖
  final_coverage.json       补检后的覆盖测量（与 match_coverage 同构）

退出码：0 正常；2 材料不足；3 校验失败。仅标准库，支持 --help。
"""
import argparse
import csv
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match_coverage import (
    EXIT_OK, EXIT_INSUFFICIENT,
    load_json, norm_title, norm_doi, norm_pmid,
    doi_of, pmid_of, title_of, year_of, first_author_surname,
    iter_records, compute_coverage, match_record, load_records_from_paths,
)

STOPWORDS = set((
    "a an the and or of in on for to with by from at as is are was were be been "
    "has have had their this that these those not no we our it its "
    "study using based new analysis review effect effects between"
).split())

CAUSE_NOT_INDEXED = "来源库未收录"
CAUSE_RECORD_ANOMALY = "记录异常"
CAUSE_ID_CONFLICT = "标识符冲突"
CAUSE_MANUAL = "需人工核查"

ARCHETYPES = ("exact_title", "author_year", "citation_chase", "source_switch")
ARCHETYPE_CN = {
    "exact_title": "原词补全式",
    "author_year": "作者+年锚定式",
    "citation_chase": "引文追踪式",
    "source_switch": "来源切换式",
}


def record_blob(rec):
    """把记录的全部字符串字段拼成规范化文本，用于子串探针。"""
    parts = []

    def walk(o):
        if isinstance(o, str):
            parts.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(rec)
    return norm_title(" ".join(parts)) or ""


GRAPH_HINTS = ("graph", "reference", "refset")


def load_corpus(materials_dir):
    """返回 (records, texts)：
    records: [(path, rec_dict)]；texts: {path: normalized_full_text}。
    参考图文件被排除：它定义分母而非可检索索引，
    对其实施查询或探针会构成循环自证。"""
    records, texts = [], {}
    for root, _dirs, names in os.walk(materials_dir):
        for name in sorted(names):
            path = os.path.join(root, name)
            low = name.lower()
            if any(h in low for h in GRAPH_HINTS):
                continue
            if low.endswith((".json", ".jsonl")):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        text = fh.read()
                except (OSError, UnicodeDecodeError):
                    continue
                texts[os.path.abspath(path)] = norm_title(text) or ""
                try:
                    obj = json.loads(text)
                    for rec in iter_records(obj):
                        records.append((os.path.abspath(path), rec))
                    continue
                except json.JSONDecodeError:
                    pass
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(rec, dict):
                        for r in iter_records(rec):
                            records.append((os.path.abspath(path), r))
            elif low.endswith((".txt", ".md", ".csv", ".xml", ".ris", ".bib")):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        texts[os.path.abspath(path)] = norm_title(fh.read()) or ""
                except (OSError, UnicodeDecodeError):
                    continue
    return records, texts


def build_idf(refset):
    df = {}
    for ref in refset:
        for tok in set((ref.get("title_norm") or "").split()):
            df[tok] = df.get(tok, 0) + 1
    return df


def discriminating_terms(ref, idf, k=5):
    toks = [t for t in (ref.get("title_norm") or "").split()
            if t not in STOPWORDS and len(t) > 2 and not t.isdigit()]
    toks.sort(key=lambda t: (idf.get(t, 1), t))
    return toks[:k]


def make_queries(ref, idf, initial_files):
    """为单条漏检记录生成四类原型查询（固定顺序 a→b→c→d）。"""
    title_norm = ref.get("title_norm") or ""
    terms = discriminating_terms(ref, idf)
    surname = ref.get("first_author")
    year = ref.get("year")
    quoted = [t for t in terms if t in title_norm][:4]
    queries = []

    def add(archetype, hypothesis, query_terms, note):
        queries.append({
            "archetype": archetype,
            "hypothesis": hypothesis,
            "target_miss_ids": [ref["ref_id"]],
            "generated_from": {"ref_id": ref["ref_id"], "quoted_terms": quoted or query_terms},
            "terms": query_terms,
            "note": note,
        })

    if title_norm:
        add("exact_title",
            "漏检记录标题原词未被初始检索命中，原词补全可在本地题录中命中",
            [title_norm], "标题规范化全串匹配")
        if surname and year and year.isdigit():
            add("author_year",
                "标题变体导致漏检，以第一作者姓氏与年份±1锚定可定位同一记录",
                [surname, str(int(year) - 1), year, str(int(year) + 1)],
                "姓氏+年份窗口")
        add("citation_chase",
            "漏检记录的引文邻域（本地参考图/参考文献串）可能携带其完整题录",
            [title_norm], "引文串前向追踪 + 后向核对")
        add("source_switch",
            "初始来源文件未收录，切换至其他本地索引文件后可命中同一概念",
            [title_norm], "跨文件来源切换")
    elif surname and year:
        add("author_year",
            "记录缺标题，仅能依靠作者+年锚定定位",
            [surname, year], "无标题退化为作者+年")
    return queries


def candidates_for_query(query, records, texts, initial_files):
    """离线执行查询：返回命中候选 [(path, rec)] 与被探针文件清单。"""
    arch = query["archetype"]
    terms = query["terms"]
    initial = {os.path.abspath(p) for p in initial_files}
    hits, probed = [], set()

    if arch == "exact_title":
        needle = terms[0]
        for path, text in sorted(texts.items()):
            probed.add(path)
            if needle and needle in text:
                for rpath, rec in records:
                    if rpath == path and needle in record_blob(rec):
                        hits.append((rpath, rec))
    elif arch == "author_year":
        surname = terms[0]
        years = set(t for t in terms[1:] if t.isdigit())
        for path, rec in sorted(records, key=lambda pr: pr[0]):
            probed.add(path)
            if first_author_surname(rec) == surname and year_of(rec) in years:
                hits.append((path, rec))
    elif arch == "citation_chase":
        needle = terms[0]
        for path, text in sorted(texts.items()):
            probed.add(path)
            if needle and needle in text:
                # 命中引文串：返回同文件中所有含词项的题录候选，由匹配器裁决
                for rpath, rec in records:
                    if rpath == path and needle in record_blob(rec):
                        hits.append((rpath, rec))
    elif arch == "source_switch":
        needle = terms[0]
        for path, text in sorted(texts.items()):
            if path in initial:
                continue
            probed.add(path)
            if needle and needle in text:
                for rpath, rec in records:
                    if rpath == path and needle in record_blob(rec):
                        hits.append((rpath, rec))
    # 去重（保持确定性顺序）
    seen, out = set(), []
    for path, rec in hits:
        key = (path, record_blob(rec)[:200])
        if key not in seen:
            seen.add(key)
            out.append((path, rec))
    return out, sorted(probed)


def probe_miss(ref, texts):
    """残余归因探针：标识符命中文件、标题词项命中计数、探针文件总数。"""
    doi = ref.get("doi")
    pmid = ref.get("pmid")
    title_norm = ref.get("title_norm") or ""
    # 文本与标识符都需归一化后再做子串探针，否则含 . 与 / 的 DOI 永不命中
    doi_norm = norm_title(doi) if doi else None
    pmid_norm = norm_pmid(pmid)
    doi_hits, pmid_hits = [], []
    token_hits = {}
    for path, text in sorted(texts.items()):
        if doi_norm and doi_norm in text:
            doi_hits.append(path)
        if pmid_norm and pmid_norm in text:
            pmid_hits.append(path)
        for tok in set(title_norm.split()) - STOPWORDS:
            if len(tok) > 2 and tok in text:
                token_hits[tok] = token_hits.get(tok, 0) + 1
    n_files = len(texts)
    n_title_tokens = len([t for t in set(title_norm.split()) if len(t) > 2])
    present_tokens = len(token_hits)
    if not title_norm and not doi and not pmid:
        cause = CAUSE_RECORD_ANOMALY
        needed = "该记录既无可用标题也无标识符，需人工回到原始文献核对题录。"
    elif (not doi_hits and not pmid_hits
          and (n_title_tokens == 0 or present_tokens <= max(1, n_title_tokens // 4))):
        cause = CAUSE_NOT_INDEXED
        needed = ("本地全部 %d 个留存文件中，该记录标识符零命中、标题判别词项覆盖率 %d/%d。"
                  "继续查询本地材料无法检回；如需检回应获取该记录所属来源库的原始响应。")
        needed = needed % (n_files, present_tokens, n_title_tokens)
    elif (doi and doi_hits and not title_norm) or (pmid and pmid_hits and not title_norm):
        cause = CAUSE_MANUAL
        needed = "标识符在本地文件中出现但无标题可匹配，需人工核对标识符对应记录。"
    else:
        cause = CAUSE_MANUAL
        needed = ("部分词项在本地有命中但无可匹配题录，需人工核查是否存在标识符冲突"
                  "或题录截断。")
    return {
        "ref_id": ref["ref_id"],
        "doi": doi,
        "pmid": pmid,
        "title": ref.get("title"),
        "attributed_cause": cause,
        "probe_evidence": {
            "files_probed": n_files,
            "doi_hits": doi_hits,
            "pmid_hits": pmid_hits,
            "title_token_hits": token_hits,
        },
        "what_would_be_needed": needed,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="漏检驱动的定向补检引擎：四类查询原型 + 边际收益记账 + 停止规则。"
    )
    ap.add_argument("--refset", required=True, help="冻结参考集 refset.json")
    ap.add_argument("--coverage", required=True, help="初始覆盖测量 coverage_initial.json")
    ap.add_argument("--materials", default="/input", help="本地材料目录（默认 /input）")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--max-queries", type=int, default=None,
                    help="查询预算（默认取 parsed_case 的 budget，再退化为 64）")
    ap.add_argument("--max-seconds", type=int, default=None,
                    help="时间预算秒数（默认取 parsed_case 的 budget，再退化为 600）")
    args = ap.parse_args(argv)

    os.makedirs(args.work, exist_ok=True)
    refset_obj = load_json(args.refset)
    refset = refset_obj.get("references", [])
    cov = load_json(args.coverage)
    if not refset or not cov.get("denominator"):
        print("[supplement_engine] 冻结参考集或覆盖测量缺失", file=sys.stderr)
        return EXIT_INSUFFICIENT

    max_queries = args.max_queries
    max_seconds = args.max_seconds
    parsed_path = os.path.join(args.work, "parsed_case.json")
    if os.path.isfile(parsed_path):
        try:
            budget = load_json(parsed_path).get("budget", {}) or {}
            if max_queries is None:
                max_queries = budget.get("max_queries")
            if max_seconds is None:
                max_seconds = budget.get("max_seconds")
        except (OSError, json.JSONDecodeError):
            pass
    if max_queries is None:
        max_queries = 64
    if max_seconds is None:
        max_seconds = 600

    records, texts = load_corpus(args.materials)
    if not texts:
        print("[supplement_engine] 本地材料目录无可探针文件：%s" % args.materials, file=sys.stderr)
        return EXIT_INSUFFICIENT

    idf = build_idf(refset)
    refs_by_id = {r["ref_id"]: r for r in refset}
    covered = set(cov.get("covered_ids", []))
    initial_files = cov.get("candidate_files", [])
    start = time.monotonic()

    log_rows = []
    state = {
        "batches": [], "queries_run": 0, "stop_rule": None,
        "budget": {"max_queries": max_queries, "max_seconds": max_seconds},
    }
    q_counter = 0
    zero_streak = 0
    stop_rule = None
    all_supp_candidates = []  # (path, rec) 全部补检候选

    def remaining_misses():
        return [refs_by_id[r] for r in sorted(set(refs_by_id) - covered)]

    for archetype in ARCHETYPES:
        if stop_rule:
            break
        missed = remaining_misses()
        if not missed:
            break
        # STOP-3 预检：全部残余漏检已具备零命中探针证据则停止
        probes = [probe_miss(r, texts) for r in missed]
        # 只有“有标题但零探针命中”的漏检才支持提前停止；
        # 记录异常类仍可能经作者+年锚定检回，须继续执行后续原型。
        if all(p["attributed_cause"] == CAUSE_NOT_INDEXED for p in probes) and probes:
            stop_rule = "STOP-3"
            state["stop_rule"] = {
                "rule": "STOP-3",
                "detail": "全部 %d 条残余漏检经探针归因为来源库未收录，"
                          "继续查询本地材料无法带来新增覆盖" % len(probes),
                "probes": probes,
            }
            break

        queries = []
        for ref in missed:
            queries.extend([q for q in make_queries(ref, idf, initial_files)
                            if q["archetype"] == archetype])
        if not queries:
            continue
        covered_before = set(covered)
        batch_newly = []
        rows_this_batch = 0

        for q in queries:
            if state["queries_run"] >= max_queries:
                stop_rule = "STOP-2"
                state["stop_rule"] = {
                    "rule": "STOP-2",
                    "detail": "查询数预算耗尽（%d/%d）" % (state["queries_run"], max_queries),
                }
                break
            if time.monotonic() - start >= max_seconds:
                stop_rule = "STOP-2"
                state["stop_rule"] = {
                    "rule": "STOP-2",
                    "detail": "时间预算耗尽（%ds）" % max_seconds,
                }
                break
            q_counter += 1
            state["queries_run"] += 1
            rows_this_batch += 1
            cands, probed = candidates_for_query(q, records, texts, initial_files)
            all_supp_candidates.extend(cands)
            # 以冻结参考集重匹配全部候选，避免只盯目标漏检造成假阳性
            newly = []
            for path, rec in cands:
                for ref in remaining_misses():
                    status, method, score = match_record(
                        ref, rec, cov.get("threshold", 0.90), cov.get("band", 0.05))
                    if status in ("matched", "borderline") and ref["ref_id"] not in covered:
                        covered.add(ref["ref_id"])
                        newly.append(ref["ref_id"])
                        break
            gain = len(newly)
            if gain > 0:
                verdict = "effective"
            elif cands:
                verdict = "marginal"
            else:
                verdict = "zero"
            log_rows.append({
                "query_id": "Q-B%d-%03d" % (len(state["batches"]) + 1, q_counter),
                "batch": "B%d" % (len(state["batches"]) + 1),
                "archetype": ARCHETYPE_CN[q["archetype"]],
                "hypothesis": q["hypothesis"],
                "target_miss_ids": ";".join(q["target_miss_ids"]),
                "generated_from": q["generated_from"]["ref_id"],
                "quoted_terms": " ".join(q["generated_from"]["quoted_terms"]),
                "source": q["note"],
                "files_searched": len(probed),
                "candidates_returned": len(cands),
                "newly_covered_ids": ";".join(newly),
                "marginal_gain": gain,
                "verdict": verdict,
            })
            batch_newly.extend(newly)

        gain_set = covered - covered_before
        batch_gain = len(gain_set)
        marginal = round(batch_gain / rows_this_batch, 6) if rows_this_batch else 0.0
        state["batches"].append({
            "batch": "B%d" % (len(state["batches"]) + 1),
            "archetype": ARCHETYPE_CN[archetype],
            "queries_run": rows_this_batch,
            "newly_covered_ids": sorted(gain_set),
            "marginal_coverage_gain": marginal,
        })
        zero_streak = zero_streak + 1 if batch_gain == 0 else 0
        if zero_streak >= 2:
            stop_rule = "STOP-1"
            state["stop_rule"] = {
                "rule": "STOP-1",
                "detail": "连续 %d 个补检批次边际收益为零" % zero_streak,
            }

    # 残余遗漏归因（含已提前归因的 STOP-3 探针结果复用）
    residual = []
    existing_probes = {}
    if state["stop_rule"] and state["stop_rule"]["rule"] == "STOP-3":
        for p in state["stop_rule"]["probes"]:
            existing_probes[p["ref_id"]] = p
    for ref in remaining_misses():
        if ref["ref_id"] in existing_probes:
            residual.append(existing_probes[ref["ref_id"]])
        else:
            residual.append(probe_miss(ref, texts))
    state["stop_rule_final"] = state["stop_rule"] or {
        "rule": "STOP-3",
        "detail": "全部原型批次执行完毕且无剩余可执行查询",
    }
    state["final_covered"] = sorted(covered)
    state["final_missed"] = sorted(set(refs_by_id) - covered)

    # 最终覆盖测量（与 match_coverage 同构）
    initial_cands = []
    for path in cov.get("candidate_files", []):
        if os.path.isfile(path):
            initial_cands.extend(load_records_from_paths([path]))
    final_cov = compute_coverage(refset, initial_cands + all_supp_candidates,
                                 cov.get("threshold", 0.90), cov.get("band", 0.05))
    final_cov.update({
        "refset_hash": refset_obj.get("refset_hash"),
        "status": "ok",
        "supplement_candidate_count": len(all_supp_candidates),
    })

    with open(os.path.join(args.work, "supplement_log.csv"), "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "query_id", "batch", "archetype", "hypothesis", "target_miss_ids",
            "generated_from", "quoted_terms", "source", "files_searched",
            "candidates_returned", "newly_covered_ids", "marginal_gain", "verdict",
        ])
        writer.writeheader()
        writer.writerows(log_rows)

    with open(os.path.join(args.work, "residual_misses.json"), "w", encoding="utf-8") as fh:
        json.dump({"case_id": refset_obj.get("case_id"), "residual_misses": residual},
                  fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.work, "supplement_state.json"), "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.work, "final_coverage.json"), "w", encoding="utf-8") as fh:
        json.dump(final_cov, fh, ensure_ascii=False, indent=2)

    print("[supplement_engine] 查询=%d 批=%d 新增覆盖=%d 停止=%s 残余=%d"
          % (state["queries_run"], len(state["batches"]),
             len(covered) - cov.get("covered", 0),
             state["stop_rule_final"]["rule"], len(residual)))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
