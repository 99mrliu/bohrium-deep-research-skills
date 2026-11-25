#!/usr/bin/env python3
"""foundry.py — 查询族锻造炉：从 research_question 派生查询族，并在有限快照上逐查询执行。

本技能重心是**术语与查询工程**。全部规则内置、零网络、完全确定性；模型判断不参与。

用法:
  python3 foundry.py --case /input/case.json --input-dir /input \
      --work /app/work --out /app/output \
      [--max-variants-per-term 4] [--max-variant-total 80] [--max-queries 40]

七个阶段（每阶段落盘，可逐步复算）:
  1. load     读 case.json；损坏/缺失 → /app/output/result.json 写 blocked 骨架，exit=2
  2. ingest   解析快照（JSON/JSONL/CSV/TSV/RIS）→ 统一记录（rid=R%03d，origin 溯源到 文件::路径）
  3. terms    RQ → 术语基座：拉丁词 / CJK 整词与二元组 / 内置跨语词表 XLEX 扩展 /
              缩写表 ABBR 双向扩展（跨语扩展仅覆盖 RQ 中真实出现的概念，不臆造）
  4. variants 连字符·单复数·缩写变体，受 --max-variants-per-term 与 --max-variant-total
              双重预算上限；被砍掉的变体数如实记入 variants.json.truncated
  5. queries  三个查询族：phrase（短语）/ term（单词·二元组）/ and2（核心术语两两合取），
              受 --max-queries 上限，截断顺序与数量如实记录
  6. execute  在快照上执行查询族；逐 查询×记录 输出命中词与位置证据
              （field / offset / snippet，第三方可按原文复核）
  7. screen   轻量条款：年份窗 + 文献类型 + 命中强度 → include/uncertain/exclude 台账；
              夹具标记（synthetic_duplicate/conflict_opinion 等）原样登记，不做学术裁决

退出码: 0=执行完成；2=输入级故障（已写 blocked 骨架，uncertainty 指明缺什么）。
"""
import argparse, csv, json, os, re, sys, time

SNAPSHOT_EXTS = (".json", ".jsonl", ".csv", ".tsv", ".ris")
LIST_HINT_KEYS = ("records", "results", "items", "entries", "hits", "export", "data", "papers")
REFLIST_KEYS = ("attributed_papers", "reference_list", "references", "refs", "paper_list")
FIXTURE_KEYS = ("synthetic_duplicate", "duplicate_of", "is_fixture", "fixture",
                "conflict_opinion", "synthetic", "label")
EXCLUDED_DOCTYPES = ("review", "perspective", "editorial", "news")

EN_STOP = set("""the a an and or of in on for to with by from at as is are was were be been
we our this that these those it its their between among within without into over under
study studies using based approach results show via new about between literature search
review screening published from""".split())
CJK_STOP_CHARS = set("的了和与及或在对为以是及其间年至到从等中上对下与和")
CJK_STOP_WORDS = {"关于", "发表", "文献", "检索", "筛选", "研究", "综述", "实验"}

# 内置跨语词表：仅当左侧概念真实出现在 RQ 中才扩展右侧检索词；第一个英文词为
# 规范术语，其余直接作为变体。领域外 RQ 自动退化为拉丁词 + CJK 切词，不联网不臆造。
XLEX = [
    ("钠离子", ["sodium-ion", "sodium ion", "na-ion"]),
    ("钠电", ["sodium-ion", "sodium ion"]),
    ("硬碳", ["hard carbon", "hard-carbon"]),
    ("软碳", ["soft carbon"]),
    ("负极", ["anode", "negative electrode"]),
    ("正极", ["cathode", "positive electrode"]),
    ("库伦效率", ["coulombic efficiency"]),
    ("库仑效率", ["coulombic efficiency"]),
    ("首周", ["initial", "first-cycle", "first cycle"]),
    ("首圈", ["initial", "first-cycle"]),
    ("预钠化", ["pre-sodiation", "presodiation"]),
    ("预锂化", ["pre-lithiation", "prelithiation"]),
    ("电解液", ["electrolyte"]),
    ("固态电池", ["solid-state battery", "solid state battery"]),
    ("锂离子", ["lithium-ion", "lithium ion", "li-ion"]),
    ("钾离子", ["potassium-ion", "potassium ion"]),
    ("快充", ["fast charging", "fast-charging"]),
    ("循环寿命", ["cycle life", "cycling stability"]),
    ("倍率", ["rate capability"]),
    ("界面", ["interface", "interfacial"]),
    ("枝晶", ["dendrite"]),
    ("隔膜", ["separator"]),
    ("能量密度", ["energy density"]),
    ("容量保持", ["capacity retention"]),
    ("钙钛矿", ["perovskite"]),
    ("太阳能", ["solar", "photovoltaic"]),
    ("晶界", ["grain boundary", "grain-boundary"]),
    ("钝化", ["passivation", "passivate"]),
    ("机器学习", ["machine learning"]),
    ("神经网络", ["neural network"]),
    ("催化剂", ["catalyst"]),
]
# 缩写表：双向扩展。RQ 出现缩写 → 补展开式；出现展开式 → 补缩写。
ABBR = [
    ("ice", ["initial coulombic efficiency"]),
    ("pce", ["power conversion efficiency"]),
    ("sib", ["sodium-ion battery", "sodium ion battery"]),
    ("lib", ["lithium-ion battery"]),
    ("sei", ["solid electrolyte interphase"]),
    ("ml", ["machine learning"]),
    ("psc", ["perovskite solar cell"]),
    ("gb", ["grain boundary"]),
]


# ---------- 1. load ----------
def read_case(path):
    if not os.path.isfile(path):
        return {}, ["case.json 不存在: %s" % path]
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
        if not isinstance(obj, dict):
            return {}, ["case.json 顶层不是 JSON 对象"]
        return obj, []
    except Exception as e:
        return {}, ["case.json 解析失败: %s" % e]


def contract_fields(case):
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        for k in ("fields", "required"):
            if isinstance(c.get(k), list):
                return [str(x) for x in c[k]]
        return sorted(c.keys())
    return []


def write_blocked(args, case, reasons):
    """任何输入级故障都留下可交付的诚实骨架。"""
    os.makedirs(args.out, exist_ok=True)
    skeleton = {"case_id": case.get("case_id"), "status": "blocked",
                "sources": [], "uncertainty": list(reasons),
                "method": "d-query-foundry: foundry(blocked)",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    for f in contract_fields(case):
        if f not in skeleton:
            skeleton[f] = []
    skeleton["field_notes"] = {f: "输入级故障，本字段无法生成：%s" % "; ".join(reasons)
                               for f in contract_fields(case)}
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(skeleton, fh, ensure_ascii=False, indent=2)


# ---------- 2. ingest ----------
def walk_json_records(obj, path, out):
    """显式栈遍历 JSON，收集'记录列表'；署名清单键一律跳过（防止清单自匹配）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in REFLIST_KEYS:
                continue
            p = "%s/%s" % (path, k)
            if (isinstance(v, list) and v and all(isinstance(x, dict) for x in v)
                    and any(("title" in x or "doi" in x) for x in v[:5])):
                out.append((p, v))
            else:
                walk_json_records(v, p, out)
    elif isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj) and \
                any(("title" in x or "doi" in x) for x in obj[:5]):
            out.append((path or "$", obj))
        else:
            for i, v in enumerate(obj):
                walk_json_records(v, "%s[%d]" % (path, i), out)


def parse_ris(text):
    recs, cur = [], {}
    tag = {"TI": "title", "T1": "title", "AU": "authors", "DO": "doi",
           "PY": "year", "JO": "venue", "JF": "venue", "TY": "type", "AB": "abstract"}
    for line in text.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9])  - (.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if k == "TY":
            cur = {"type": v}
        elif k == "ER":
            if cur:
                recs.append(cur)
            cur = {}
        elif k in tag:
            if tag[k] == "authors":
                cur.setdefault("authors", []).append(v)
            else:
                cur[tag[k]] = v
    if cur:
        recs.append(cur)
    return recs


def unify(raw, seq, origin):
    r = raw if isinstance(raw, dict) else {"value": raw}
    authors = r.get("authors") or r.get("author") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r";| and ", authors) if a.strip()]
    ym = re.search(r"(19|20)\d{2}", str(r.get("year") or r.get("publication_year")
                                        or r.get("date") or r.get("py") or ""))
    title = r.get("title") or r.get("TI") or ""
    abstract = r.get("abstract") or r.get("AB") or ""
    venue = r.get("venue") or r.get("journal") or r.get("JO") or r.get("source") or ""
    return {
        "rid": "R%03d" % seq,
        "origin": origin,
        "title": title,
        "authors": authors,
        "year": int(ym.group(0)) if ym else None,
        "doi": (r.get("doi") or r.get("DO") or "").strip().lower() or None,
        "venue": venue,
        "type": (r.get("type") or r.get("TY") or r.get("doctype") or "").lower(),
        "abstract": abstract,
        "fixture": {k: r[k] for k in FIXTURE_KEYS if k in r},
        "text": {"title": title.lower(), "abstract": abstract.lower(),
                 "venue": venue.lower()},
    }


def ingest(input_dir):
    records, files, failures = [], [], []
    seq = 0
    for root, _dirs, names in os.walk(input_dir):
        for n in sorted(names):
            p = os.path.join(root, n)
            rel = os.path.relpath(p, input_dir)
            ext = os.path.splitext(n)[1].lower()
            if ext not in SNAPSHOT_EXTS:
                files.append({"path": rel, "kind": ext.lstrip(".") or "none",
                              "records": 0})
                continue
            try:
                before = len(records)
                if ext == ".jsonl":
                    with open(p, encoding="utf-8") as fh:
                        rows = [json.loads(l) for l in fh if l.strip()]
                    for i, r in enumerate(rows):
                        seq += 1
                        records.append(unify(r, seq, "%s::line[%d]" % (rel, i + 1)))
                elif ext == ".json":
                    with open(p, encoding="utf-8") as fh:
                        obj = json.load(fh)
                    found = []
                    walk_json_records(obj, "$", found)
                    for lpath, rows in found:
                        for i, r in enumerate(rows):
                            seq += 1
                            records.append(unify(r, seq, "%s::%s[%d]" % (rel, lpath, i)))
                elif ext in (".csv", ".tsv"):
                    with open(p, encoding="utf-8", newline="") as fh:
                        rows = list(csv.DictReader(
                            fh, delimiter="\t" if ext == ".tsv" else ","))
                    for i, r in enumerate(rows):
                        seq += 1
                        records.append(unify(r, seq, "%s::row[%d]" % (rel, i + 1)))
                elif ext == ".ris":
                    with open(p, encoding="utf-8") as fh:
                        rows = parse_ris(fh.read())
                    for i, r in enumerate(rows):
                        seq += 1
                        records.append(unify(r, seq, "%s::ris[%d]" % (rel, i + 1)))
                files.append({"path": rel, "kind": ext[1:],
                              "records": len(records) - before})
            except Exception as e:
                failures.append({"path": rel, "error": str(e)})
    return records, files, failures


# ---------- 3. terms ----------
def cjk_runs(text):
    return re.findall(r"[\u4e00-\u9fff]+", text or "")


def build_term_base(rq):
    """RQ → 术语基座。返回 (terms, report)；term = {term, kind, origin}。"""
    rq = rq or ""
    terms, report = [], {"latin_rq": 0, "cjk_word": 0, "cjk_bigram": 0,
                         "xlex_expansion": [], "abbr_expansion": []}
    seen = set()

    def add(term, kind, origin):
        key = (term.lower(), kind)
        if term and key not in seen:
            seen.add(key)
            terms.append({"term": term.lower() if kind != "cjk" else term,
                          "kind": kind, "origin": origin})

    # 拉丁词（≥3 字符，去停用词）
    for w in re.findall(r"[a-z][a-z0-9-]{2,}", rq.lower()):
        if w not in EN_STOP and not w.isdigit():
            add(w, "latin", "rq")
            report["latin_rq"] += 1
    # CJK 整词（词表概念）与二元组
    for run in cjk_runs(rq):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if any(ch in CJK_STOP_CHARS for ch in bg) or bg in CJK_STOP_WORDS:
                continue
            add(bg, "cjk", "rq-bigram")
            report["cjk_bigram"] += 1
    # 跨语词表扩展（仅 RQ 真实出现的概念；CJK 概念本身也立为整词术语）
    for cjk, en_list in XLEX:
        if cjk.lower() in rq.lower():
            add(cjk, "cjk", "xlex:%s" % cjk)
            report["cjk_word"] += 1
            canonical = en_list[0]
            kind = "phrase" if (" " in canonical or "-" in canonical) else "latin"
            add(canonical, kind, "xlex:%s" % cjk)
            report["xlex_expansion"].append({"concept": cjk, "terms": en_list})
    # 缩写双向扩展
    rq_low = rq.lower()
    for ab, expansions in ABBR:
        hit_abbr = re.search(r"(?<![a-z])%s(?![a-z])" % ab, rq_low)
        hit_exp = any(e in rq_low for e in expansions)
        if hit_abbr or hit_exp:
            add(ab, "latin", "abbr")
            for e in expansions:
                add(e, "phrase", "abbr:%s" % ab)
            report["abbr_expansion"].append({"abbr": ab, "expansions": expansions})
    return terms, report


def derive_window(rq):
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", rq or "")]
    if len(years) >= 2:
        return [min(years), max(years)]
    if years:
        return [years[0], years[0]]
    return None


# ---------- 4. variants（预算上限防发散） ----------
def raw_variants(term):
    """连字符 / 单复数 / 缩写三组规则（详见 references/variant-rules.md）。"""
    out = []
    if " " in term:                                   # R1 连字符化（短语 → 连字符/连写）
        out += [term.replace(" ", "-"), term.replace(" ", "")]
    if "-" in term:                                   # R1 反向（连字符 → 空格/连写）
        out += [term.replace("-", " "), term.replace("-", "")]
    words = term.split()
    last = words[-1] if words else ""
    if re.fullmatch(r"[a-z]+", last):                 # R2 单复数（仅末词、纯拉丁）
        if last.endswith("ies") and len(last) > 3:
            out.append(term[: -3] + "y")
        elif last.endswith("es") and len(last) > 2:
            out.append(term[:-2])
        elif last.endswith("s") and not last.endswith("ss") and len(last) > 1:
            out.append(term[:-1])
        elif last.endswith("y"):
            out.append(term[:-1] + "ies")
        else:
            out.append(term + "s")
    for ab, expansions in ABBR:                       # R3 缩写双向
        if term == ab:
            out += expansions
        elif term in expansions:
            out.append(ab)
    seen, uniq = set(), []
    for v in out:
        if v and v != term and v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def apply_variants(terms, per_term_cap, total_cap):
    budget = {"per_term_cap": per_term_cap, "total_cap": total_cap,
              "generated": 0, "truncated": 0, "term_count": len(terms)}
    for t in terms:
        variants = raw_variants(t["term"])
        # XLEX 的非规范英文词直接并进变体（同源扩展，不占规则推导）
        for cjk, en_list in XLEX:
            if t["origin"] == "xlex:%s" % cjk and t["term"] == en_list[0]:
                variants = en_list[1:] + variants
        keep = []
        for v in variants:
            if len(keep) >= per_term_cap or budget["generated"] >= total_cap:
                budget["truncated"] += 1
                continue
            keep.append(v)
            budget["generated"] += 1
        t["variants"] = keep
    return terms, budget


# ---------- 5. queries ----------
def build_queries(terms, max_queries):
    families, order = [], ["phrase", "and2", "term"]
    phrases = [t for t in terms if t["kind"] == "phrase"]
    singles = [t for t in terms if t["kind"] in ("latin", "cjk")]
    # and2 核心：短语优先、其次较长拉丁词，取前 6 个两两合取
    core = sorted([t for t in terms if t["kind"] in ("phrase", "latin")],
                  key=lambda t: (t["kind"] != "phrase", -len(t["term"])))[:6]
    for t in phrases:
        families.append({"family": "phrase", "op": "phrase", "terms": [t]})
    for i in range(len(core)):
        for j in range(i + 1, len(core)):
            families.append({"family": "and2", "op": "and",
                             "terms": [core[i], core[j]]})
    for t in singles:
        families.append({"family": "term", "op": "term", "terms": [t]})
    queries, truncated = [], 0
    counters = {"phrase": 0, "and2": 0, "term": 0}
    for fam in order:
        for q in [x for x in families if x["family"] == fam]:
            if len(queries) >= max_queries:
                truncated += 1
                continue
            counters[fam] += 1
            qid = {"phrase": "QP", "and2": "QA", "term": "QT"}[fam] + str(counters[fam])
            queries.append({"qid": qid, "family": fam, "op": q["op"],
                            "terms": [{"term": t["term"], "kind": t["kind"],
                                       "origin": t["origin"],
                                       "variants": t.get("variants", [])}
                                      for t in q["terms"]]})
    return queries, {"max_queries": max_queries, "built": len(queries),
                     "truncated": truncated, "core_terms": [t["term"] for t in core]}


# ---------- 6. execute ----------
def locate(text, needle, cjk):
    if not needle:
        return -1
    if cjk:
        return text.find(needle)
    m = re.search(r"(?<![0-9a-z])%s(?![0-9a-z])" % re.escape(needle), text)
    return m.start() if m else -1


def snippet(text, off, length):
    lo = max(0, off - 20)
    return text[lo: off + length + 20].strip()


def term_evidence(record, term):
    """某术语（含变体）在记录中的首个命中证据；无命中返回 None。"""
    cjk = term["kind"] == "cjk"
    for surface in [term["term"]] + term.get("variants", []):
        for field in ("title", "abstract", "venue"):
            text = record["text"][field]
            off = locate(text, surface, cjk)
            if off >= 0:
                return {"term": term["term"], "surface": surface, "field": field,
                        "offset": off, "snippet": snippet(text, off, len(surface))}
    return None


def execute(queries, records):
    hits, per_record = [], {r["rid"]: [] for r in records}
    for q in queries:
        for r in records:
            ev = [term_evidence(r, t) for t in q["terms"]]
            if q["op"] == "and":
                ok = all(ev)
            else:
                ok = any(ev)
            if ok:
                matched = [e for e in ev if e]
                hits.append({"qid": q["qid"], "family": q["family"],
                             "rid": r["rid"], "matched": matched})
                per_record[r["rid"]].append(q["qid"])
    return hits, per_record


# ---------- 7. screen ----------
def screen(records, per_record, qmap, window):
    ledger, counts = [], {"include": 0, "uncertain": 0, "exclude": 0}
    for r in records:
        qids = per_record.get(r["rid"], [])
        fams = {qmap[q]["family"] for q in qids}
        codes = []
        dup_flag = any(k in r["fixture"] for k in ("synthetic_duplicate", "duplicate_of",
                                                   "is_fixture", "fixture"))
        if dup_flag:
            disp, codes = "exclude", ["fixture_duplicate_registered"]
        elif window and r["year"] and not (window[0] <= r["year"] <= window[1]):
            disp, codes = "exclude", ["year_out_of_window:%d!in:%s" % (r["year"], window)]
        elif r["type"] in EXCLUDED_DOCTYPES:
            disp, codes = "exclude", ["doctype_excluded:%s" % r["type"]]
        elif "phrase" in fams or "and2" in fams or len(qids) >= 2:
            disp, codes = "include", ["query_hits:%d" % len(qids)]
        elif qids:
            disp, codes = "uncertain", ["weak_single_term_hit"]
        else:
            disp, codes = "exclude", ["no_query_hits"]
        if "conflict_opinion" in r["fixture"]:
            codes.append("fixture_conflict_opinion")
        counts[disp] += 1
        ledger.append({"rid": r["rid"], "origin": r["origin"], "title": r["title"],
                       "year": r["year"], "doi": r["doi"], "disposition": disp,
                       "reason_codes": codes, "matched_qids": qids,
                       "fixture": r["fixture"] or None})
    return ledger, counts


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def dump_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="查询族锻造炉：RQ→查询族→快照执行→轻量筛查")
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-variants-per-term", type=int, default=4)
    ap.add_argument("--max-variant-total", type=int, default=80)
    ap.add_argument("--max-queries", type=int, default=40)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    case, problems = read_case(args.case)
    if problems:
        write_blocked(args, case, problems)
        print(json.dumps({"ok": False, "blocked": problems}, ensure_ascii=False))
        sys.exit(2)

    records, files, failures = ingest(args.input_dir)
    dump_json(os.path.join(args.work, "ingest-report.json"),
              {"files": files, "records_total": len(records), "failures": failures})
    if not records:
        reasons = failures and ["全部快照文件解析失败"] or ["快照零记录（输入目录无可解析文献）"]
        write_blocked(args, case, reasons)
        print(json.dumps({"ok": False, "blocked": reasons}, ensure_ascii=False))
        sys.exit(2)
    dump_jsonl(os.path.join(args.work, "records.jsonl"), records)

    rq = case.get("research_question") or ""
    terms, term_report = build_term_base(rq)
    if not terms:
        reasons = ["research_question 无可用术语（拉丁词/CJK 切词/词表扩展均为空），无法锻造查询族"]
        write_blocked(args, case, reasons)
        print(json.dumps({"ok": False, "blocked": reasons}, ensure_ascii=False))
        sys.exit(2)
    terms, budget = apply_variants(terms, args.max_variants_per_term,
                                   args.max_variant_total)
    window = derive_window(rq)
    dump_json(os.path.join(args.work, "term-base.json"),
              {"research_question": rq, "year_window": window,
               "report": term_report, "terms": terms})

    queries, qreport = build_queries(terms, args.max_queries)
    dump_json(os.path.join(args.work, "query-families.json"),
              {"budget": budget, "query_budget": qreport, "queries": queries})

    hits, per_record = execute(queries, records)
    dump_jsonl(os.path.join(args.work, "hits.jsonl"), hits)
    qmap = {q["qid"]: q for q in queries}
    per_query = []
    for q in queries:
        qh = [h for h in hits if h["qid"] == q["qid"]]
        per_query.append({"qid": q["qid"], "family": q["family"], "op": q["op"],
                          "terms": [t["term"] for t in q["terms"]],
                          "hits": len(qh), "rids": [h["rid"] for h in qh]})
    dump_json(os.path.join(args.out, "query-execution.json"),
              {"queries": per_query, "total_hits": len(hits)})

    ledger, counts = screen(records, per_record, qmap, window)
    dump_jsonl(os.path.join(args.out, "screening-ledger.jsonl"), ledger)
    candidates = [{"rid": l["rid"], "origin": l["origin"], "title": l["title"],
                   "year": l["year"], "doi": l["doi"],
                   "matched_qids": l["matched_qids"]}
                  for l in ledger if l["disposition"] == "include"]
    dump_json(os.path.join(args.out, "candidates.json"),
              {"year_window": window, "counts": counts, "candidates": candidates})

    print(json.dumps({"ok": True, "records": len(records), "terms": len(terms),
                      "variants": budget["generated"],
                      "variants_truncated": budget["truncated"],
                      "queries": len(queries), "queries_truncated": qreport["truncated"],
                      "hits": len(hits), "candidates": len(candidates),
                      "failures": len(failures)}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
