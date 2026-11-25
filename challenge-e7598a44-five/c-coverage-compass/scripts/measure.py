#!/usr/bin/env python3
"""measure.py — 证据充分性测量：回答"每个子问题证据够不够、什么时候可以停"。

用法:
  python3 measure.py --case /input/case.json --input-dir /input --work /app/work

输入:
  --case        case.json（case_id / research_question / output_contract）
  --input-dir   有限快照目录（JSON/JSONL/CSV/TSV/RIS 检索导出）
  --work        工作目录；若其中存在 decomposition.json（Agent 按
                references/subquestion-template.md 写的子问题清单）则使用之，
                否则从 research_question 自动派生 2–5 个子问题并如实标注。

产出（--work 下）:
  coverage_report.json   SQ×证据覆盖矩阵 + 逐 SQ 充分性分级（sufficient/thin/starved）
                         + 边际收益估计（模拟第 2 轮放宽年份窗后的新增命中）
                         + 全局停止决定（evidence_sufficient / marginal_gain_low /
                         handoff_to_human，带一句可复核理由）+ 缺口分类
                         （no_records / only_conflicted / metadata_missing / out_of_window）
  decomposition.used.json  实际使用的子问题清单（含来源标注，供复核）

退出码: 0=正常测量；2=case.json 缺失/损坏或快照零记录（仍写出诚实报告）。
"""
import argparse, csv, json, os, re, sys

RECORD_LIST_HINTS = ("records", "results", "items", "hits", "export", "entries", "data")
REFLIST_KEYS = ("attributed_papers", "reference_list", "references", "refs",
                "paper_list", "subquestions")
FIXTURE_FLAG_KEYS = ("synthetic_duplicate", "duplicate_of", "conflict_opinion",
                     "fixture", "is_fixture", "synthetic")
LATIN_STOP = set("""the a an and or of in on for to with by from at as is are was were
be been we our this that these those it its their between among within without into
over under study studies using based approach results show via new et al""".split())

# 仅用于自动派生子问题时的跨语扩展：RQ 中真实出现左侧概念才补右侧检索词。
# 刻意保持小词表：派生是兜底路径，宁可少扩张也不臆造术语。
CROSS_LINGUAL = {
    "钙钛矿": ["perovskite"], "晶界": ["grain boundary"], "钝化": ["passivation"],
    "稳定性": ["stability"], "湿热": ["damp heat", "humidity"], "效率": ["efficiency"],
    "毒性": ["toxicity"], "铅": ["lead"], "太阳能": ["solar"], "电池": ["cell"],
}

SUFFICIENT_MIN = 3   # 可用证据 ≥3 条记 sufficient；1–2 条 thin；0 条 starved


# ---------- 快照解析（轻量自写实现：统一为 标题/摘要/年份/DOI/夹具标记） ----------
def norm_record(raw, rid):
    r = raw if isinstance(raw, dict) else {"value": raw}
    year_raw = r.get("year") or r.get("publication_year") or r.get("date") or r.get("py") or ""
    m = re.search(r"(19|20)\d{2}", str(year_raw))
    flags = {k: r[k] for k in FIXTURE_FLAG_KEYS if k in r}
    return {
        "rid": rid,
        "title": str(r.get("title") or r.get("TI") or ""),
        "abstract": str(r.get("abstract") or r.get("AB") or ""),
        "venue": str(r.get("venue") or r.get("journal") or r.get("JO") or ""),
        "year": int(m.group(0)) if m else None,
        "doi": (str(r.get("doi") or r.get("DO") or "").strip().lower() or None),
        "conflict_flag": bool(flags.get("conflict_opinion")),
        "fixture_flags": flags,
    }


def harvest_lists(obj, path="$", out=None):
    """在 JSON 树中找记录列表；命中提示键即收，不再下钻；排除署名清单/子问题键。"""
    out = out if out is not None else []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in RECORD_LIST_HINTS and isinstance(v, list) and v and isinstance(v[0], dict):
                out.append(("%s.%s" % (path, k), v))
            elif isinstance(v, (dict, list)):
                harvest_lists(v, "%s.%s" % (path, k), out)
    elif isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        last = path.rsplit(".", 1)[-1]
        if last not in REFLIST_KEYS and any("title" in x or "doi" in x for x in obj[:5]):
            out.append((path, obj))
    return out


def read_snapshot(input_dir):
    records, files, failures = [], [], []
    if not os.path.isdir(input_dir):
        return records, files, [{"path": input_dir, "error": "输入目录不存在"}]
    for root, _dirs, names in os.walk(input_dir):
        for name in sorted(names):
            p = os.path.join(root, name)
            rel = os.path.relpath(p, input_dir)
            ext = os.path.splitext(name)[1].lower()
            try:
                if ext == ".json":
                    obj = json.load(open(p, encoding="utf-8"))
                    lists = harvest_lists(obj)
                    for lpath, rows in lists:
                        for i, row in enumerate(rows):
                            records.append(norm_record(row, "%s!%s#%d" % (rel, lpath, i + 1)))
                    files.append({"path": rel, "kind": "json", "record_lists": len(lists)})
                elif ext == ".jsonl":
                    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
                    for i, row in enumerate(rows):
                        records.append(norm_record(row, "%s!#%d" % (rel, i + 1)))
                    files.append({"path": rel, "kind": "jsonl", "record_lists": 1 if rows else 0})
                elif ext in (".csv", ".tsv"):
                    with open(p, encoding="utf-8", newline="") as fh:
                        rows = list(csv.DictReader(fh, delimiter="\t" if ext == ".tsv" else ","))
                    for i, row in enumerate(rows):
                        records.append(norm_record(row, "%s!row#%d" % (rel, i + 1)))
                    files.append({"path": rel, "kind": ext[1:], "record_lists": 1 if rows else 0})
                elif ext == ".ris":
                    recs, cur = [], {}
                    for line in open(p, encoding="utf-8"):
                        m = re.match(r"^([A-Z][A-Z0-9])  - (.*)$", line.rstrip("\n"))
                        if not m:
                            continue
                        tag, val = m.group(1), m.group(2).strip()
                        if tag == "TY":
                            cur = {}
                        elif tag == "ER":
                            recs.append(cur); cur = {}
                        elif tag in ("TI", "T1"):
                            cur["title"] = val
                        elif tag == "AB":
                            cur["abstract"] = val
                        elif tag in ("PY", "Y1"):
                            cur["year"] = val
                        elif tag == "DO":
                            cur["doi"] = val
                        elif tag in ("JO", "JF"):
                            cur["venue"] = val
                    for i, row in enumerate(recs):
                        records.append(norm_record(row, "%s!ris#%d" % (rel, i + 1)))
                    files.append({"path": rel, "kind": "ris", "record_lists": 1 if recs else 0})
                else:
                    files.append({"path": rel, "kind": ext.lstrip(".") or "none",
                                  "record_lists": 0})
            except Exception as e:
                failures.append({"path": rel, "error": str(e)})
    return records, files, failures


# ---------- 子问题：读取 Agent 清单或自动派生 ----------
def load_decomposition(work_dir, rq):
    path = os.path.join(work_dir, "decomposition.json")
    if os.path.isfile(path):
        try:
            obj = json.load(open(path, encoding="utf-8"))
            sqs = obj.get("subquestions") if isinstance(obj, dict) else obj
            if isinstance(sqs, list) and sqs:
                clean = []
                for i, sq in enumerate(sqs):
                    if not isinstance(sq, dict):
                        continue
                    clean.append({
                        "sq_id": str(sq.get("sq_id") or "SQ-%d" % (i + 1)),
                        "question": str(sq.get("question") or ""),
                        "must_terms": [str(t) for t in (sq.get("must_terms") or [])],
                        "any_terms": [str(t) for t in (sq.get("any_terms") or [])],
                        "year_window": sq.get("year_window"),
                        "rationale": str(sq.get("rationale") or ""),
                    })
                if clean:
                    return clean, "agent_file", None
                return None, None, "decomposition.json 存在但 subquestions 为空，改用自动派生"
        except Exception as e:
            return None, None, "decomposition.json 解析失败（%s），改用自动派生" % e
    return None, None, None


CJK_GENERIC = {"影响", "研究", "评估", "方面", "证据", "充分性", "综述", "分析", "探讨"}


def derive_subquestions(rq):
    """元素抽取派生 2–5 个子问题：CJK 语义段（按连词切开、剔除泛用词）+ 拉丁相邻实词
    二元组。CJK 段若命中内置小词表则用英文扩展词作检索词（适配英文快照）；
    无扩展时 CJK 段本身作 must_term（适配中文快照）。"""
    rq = rq or ""
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", rq)]
    window = [min(years), max(years)] if years else None
    elements = []
    for run in re.findall(r"[一-鿿]+", rq):
        for seg in re.split(r"[的和与及或在对中其]", run):
            if len(seg) >= 2 and seg not in CJK_GENERIC and seg not in elements:
                elements.append(seg)
    words = [w.lower() for w in re.findall(r"[a-zA-Z][a-z0-9-]+", rq)
             if w.lower() not in LATIN_STOP and len(w) > 2]
    for a, b in zip(words, words[1:]):
        if (a + " " + b) not in elements:
            elements.append(a + " " + b)
    elements = elements[:5]
    if len(elements) < 2 and rq.strip():
        elements = [rq.strip()[:60]]
    sqs = []
    for i, el in enumerate(elements):
        # 每个被命中概念取其第一个英文扩展词作 AND 条件（概念间 AND、概念内不展开 OR，
        # 保持兜底路径语义简单可预测）；无扩展时 CJK 段本身作 must_term（适配中文快照）。
        exp = [en[0] for cjk, en in CROSS_LINGUAL.items() if cjk in el]
        if exp:
            must, anyt = exp, []
        else:
            must, anyt = [el], []
        sqs.append({
            "sq_id": "SQ-%d" % (i + 1),
            "question": "快照中关于「%s」的证据有哪些？" % el,
            "must_terms": must, "any_terms": anyt,
            "year_window": window,
            "rationale": "自动派生：来自 RQ 元素抽取（兜底路径，建议 Agent 按 "
                         "references/subquestion-template.md 手写 decomposition.json）",
        })
    return sqs, "auto_derived"


# ---------- 覆盖测量 ----------
def sq_evidence(rec, sq):
    """返回 (term_hit, in_window, matched_terms)。年份缺失的记录按在窗处理但另记 metadata。"""
    text = " ".join([rec["title"], rec["abstract"], rec["venue"]]).lower()
    must = [t.lower() for t in sq["must_terms"]]
    anyt = [t.lower() for t in sq["any_terms"]]
    hit_must = [t for t in must if t in text]
    hit_any = [t for t in anyt if t in text]
    term_hit = (len(hit_must) == len(must)) and (not anyt or bool(hit_any))
    in_window = True
    win = sq.get("year_window")
    if term_hit and win and rec["year"] is not None:
        in_window = int(win[0]) <= rec["year"] <= int(win[1])
    return term_hit, in_window, hit_must + hit_any


def grade(usable):
    if usable >= SUFFICIENT_MIN:
        return "sufficient"
    return "thin" if usable >= 1 else "starved"


def classify_gap(row):
    if row["sufficiency"] == "sufficient":
        return None
    if row["raw_term_hits"] == 0:
        return "no_records"
    if row["usable_hits"] == 0 and row["conflicted_hits"] == 0 and row["out_of_window_hits"] > 0:
        return "out_of_window"
    if row["usable_hits"] == 0 and row["conflicted_hits"] > 0:
        return "only_conflicted"
    if row["usable_hits"] > 0 and row["usable_hits"] == row["metadata_missing_hits"]:
        return "metadata_missing"
    return None


def measure(records, sqs):
    matrix = []
    for sq in sqs:
        usable, conflicted, outwin, meta_missing, relaxed_new = [], [], [], [], []
        evidence = []
        for rec in records:
            term_hit, in_window, matched = sq_evidence(rec, sq)
            if not term_hit:
                continue
            evidence.append({"rid": rec["rid"], "title": rec["title"],
                             "year": rec["year"], "doi": rec["doi"],
                             "matched_terms": matched})
            if rec["conflict_flag"]:
                (conflicted if in_window else outwin).append(rec["rid"])
            elif not in_window:
                outwin.append(rec["rid"])
                relaxed_new.append(rec["rid"])   # 第 2 轮放宽年份窗可新增
            else:
                usable.append(rec["rid"])
                if rec["year"] is None or not rec["doi"]:
                    meta_missing.append(rec["rid"])
        row = {
            "sq_id": sq["sq_id"], "question": sq["question"],
            "usable_hits": len(usable), "conflicted_hits": len(conflicted),
            "out_of_window_hits": len(outwin),
            "metadata_missing_hits": len(meta_missing),
            "raw_term_hits": len(usable) + len(conflicted) + len(outwin),
            "usable_rids": usable, "conflicted_rids": conflicted,
            "out_of_window_rids": outwin, "metadata_missing_rids": meta_missing,
            "evidence": evidence,
            "marginal_gain_round2": len(relaxed_new),
        }
        row["sufficiency"] = grade(row["usable_hits"])
        row["gap"] = classify_gap(row)
        matrix.append(row)
    return matrix


def stop_decision(matrix, records_total):
    starved = [r for r in matrix if r["sufficiency"] == "starved"]
    thin = [r for r in matrix if r["sufficiency"] == "thin"]
    per_sq = {r["sq_id"]: ("accept" if r["sufficiency"] == "sufficient"
                           else "needs_human" if r["sufficiency"] == "starved"
                           else "accept_with_caveat") for r in matrix}
    if records_total == 0:
        return {"decision": "handoff_to_human",
                "reason": "快照零记录：无任何证据可测量，不能臆造覆盖结论",
                "per_sq_recommendation": per_sq}
    if starved:
        desc = "、".join("%s（%s）" % (r["sq_id"], r["gap"] or "no_records") for r in starved)
        return {"decision": "handoff_to_human",
                "reason": "存在零可用证据子问题 %s：有限快照内无法补足，"
                          "需人工扩展检索源或书面确认接受该缺口" % desc,
                "per_sq_recommendation": per_sq}
    if not thin:
        return {"decision": "evidence_sufficient",
                "reason": "全部 %d 个子问题可用证据 ≥%d 条，满足充分性阈值"
                          % (len(matrix), SUFFICIENT_MIN),
                "per_sq_recommendation": per_sq}
    gain = sum(r["marginal_gain_round2"] for r in thin)
    if gain <= len(thin):
        return {"decision": "marginal_gain_low",
                "reason": "%d 个 thin 子问题放宽第 2 轮（去年份窗）预计仅新增 %d 条，"
                          "边际收益低于每子问题 2 条，继续检索不改变分级，可以停"
                          % (len(thin), gain),
                "per_sq_recommendation": per_sq}
    return {"decision": "handoff_to_human",
            "reason": "%d 个 thin 子问题放宽第 2 轮预计新增 %d 条（超过每子问题 1 条），"
                      "可能改变分级；快照有限无法自取，交人工决定是否追加检索轮次"
                      % (len(thin), gain),
            "per_sq_recommendation": per_sq}


def main():
    ap = argparse.ArgumentParser(description="逐子问题证据覆盖测量与停止决定")
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)

    problems, case = [], {}
    if not os.path.isfile(args.case):
        problems.append("case.json 不存在: %s" % args.case)
    else:
        try:
            case = json.load(open(args.case, encoding="utf-8"))
            if not isinstance(case, dict):
                problems.append("case.json 顶层不是对象")
                case = {}
        except Exception as e:
            problems.append("case.json 解析失败: %s" % e)
            case = {}
    rq = case.get("research_question") or ""
    if not rq:
        problems.append("research_question 缺失：无法建立子问题")

    records, files, failures = read_snapshot(args.input_dir)
    problems.extend("文件 %s 解析失败: %s" % (f["path"], f["error"]) for f in failures)
    if not records:
        problems.append("快照零记录：/input 中未解析出任何文献记录")

    sqs, source, fallback_note = load_decomposition(args.work, rq)
    if fallback_note:
        problems.append(fallback_note)
    if sqs is None:
        sqs, source = derive_subquestions(rq)
    if source == "auto_derived":
        problems.append("未发现 /app/work/decomposition.json，子问题由 RQ 元素抽取自动派生"
                        "（%d 个），口径粗于人工分解，结论按降级置信对待" % len(sqs))

    matrix = measure(records, sqs)
    decision = stop_decision(matrix, len(records))

    with open(os.path.join(args.work, "decomposition.used.json"), "w", encoding="utf-8") as fh:
        json.dump({"source": source, "subquestions": sqs}, fh, ensure_ascii=False, indent=2)
    report = {
        "case_id": case.get("case_id"),
        "research_question": rq,
        "decomposition_source": source,
        "thresholds": {"sufficient_min_usable": SUFFICIENT_MIN,
                       "thin_range": [1, SUFFICIENT_MIN - 1],
                       "round2_relaxation": "drop_year_window"},
        "records_total": len(records),
        "input_files": files,
        "matrix": matrix,
        "stop_decision": decision,
        "problems": problems,
    }
    with open(os.path.join(args.work, "coverage_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(json.dumps({
        "ok": not problems, "records": len(records), "subquestions": len(sqs),
        "decomposition_source": source,
        "sufficiency": {r["sq_id"]: r["sufficiency"] for r in matrix},
        "stop_decision": decision["decision"], "problems": problems,
    }, ensure_ascii=False))
    sys.exit(2 if (not records or not case) else 0)


if __name__ == "__main__":
    main()
