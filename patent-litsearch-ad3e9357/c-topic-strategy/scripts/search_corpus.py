#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search_corpus.py — 检索式执行器（本地语料自动发现 + 专利/NPL 双轨执行）

- 自动发现本地语料（.json/.jsonl/.csv/.tsv/.txt/.md）；
- 按记录特征区分轨道：专利号/kind code/分类号 → 专利轨道；
  DOI/期刊/作者 → NPL 轨道；无法判定 → unclassified 并如实列出；
- 专利轨道：字段限定匹配（标题/摘要/权利要求/分类号/申请人），
  同族去重（family 字段 → 优先权号 → 规范化公开号），kind code 感知；
- NPL 轨道：标题/摘要关键词匹配 + DOI/标题规范化去重；
- 输出命中清单，每条带定位（文件 + JSON 路径/行号）与匹配词项明细。

用法：
  python3 search_corpus.py --query query.json --corpus DIR [DIR ...] --out hits.json
  --corpus 缺省为 /input /app/work . ；case.json/task.md 默认视为任务定义而非语料。

退出码：0 成功；1 参数/读取错误。仅依赖标准库。
"""
import argparse
import csv
import json
import os
import re
import sys

CORPUS_EXTS = {".json", ".jsonl", ".csv", ".tsv", ".txt", ".md"}
SKIP_BASENAMES = {"case.json", "task.md"}

PATENT_NUM_RE = re.compile(r"\b[A-Z]{2}\d{4,10}(?:[A-Z]\d?)?\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/\S+")
YEAR_RE = re.compile(r"(19|20)\d{2}")

PATENT_KEYS = {"publication_number", "pub_no", "patent_number", "kind_code", "kind",
               "priority_number", "priority", "ipc", "cpc", "classification",
               "classifications", "applicant", "assignee", "claims", "family_id",
               "family", "application_number", "filing_date"}
NPL_KEYS = {"doi", "journal", "authors", "author", "volume", "issue", "pages",
            "issn", "pmid", "publisher"}

TEXT_FIELDS_PATENT = ["title", "abstract", "claims", "claim", "description"]
CLASS_FIELDS = ["ipc", "cpc", "classification", "classifications"]
APPLICANT_FIELDS = ["applicant", "assignee", "applicant_name", "assignee_name"]
DATE_FIELDS = ["publication_date", "pub_date", "priority_date", "filing_date", "date", "year"]
NUMBER_FIELDS = ["publication_number", "pub_no", "patent_number", "priority_number",
                 "application_number", "publication"]
NPL_TEXT_FIELDS = ["title", "abstract", "_text"]
UNCLASS_TEXT_FIELDS = ["title", "abstract", "_text"]
FAMILY_FIELDS = ["family_id", "family", "family_number", "simple_family"]
PRIORITY_FIELDS = ["priority_number", "priority", "priority_no"]


# ---------- 语料发现与记录加载 ----------

def discover_files(dirs):
    seen, out = set(), []
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for root, _sub, files in os.walk(d):
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() in CORPUS_EXTS:
                    p = os.path.join(root, fn)
                    rp = os.path.realpath(p)
                    if rp not in seen:
                        seen.add(rp)
                        out.append(p)
    return out


def looks_like_artifact(obj):
    """跳过本管线自身产物/检索式文件，避免自匹配污染。"""
    if not isinstance(obj, dict):
        return False
    keys = set(obj)
    if {"blocks", "boolean"} <= keys:
        return True
    if {"topic", "blocks", "facets"} <= keys:
        return True
    if {"corpus", "hits", "dedup"} <= keys:
        return True
    if {"prisma"} <= keys:
        return True
    if {"case_id", "output_contract"} <= keys:
        return True
    if {"case_id", "status", "query"} <= keys:
        return True
    return False


def load_records(path):
    """返回 (records:[(rec, loc)], skipped_reason)。loc 为 JSON 路径/行号/row/file。"""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".json":
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
            if looks_like_artifact(obj):
                return [], "artifact(检索式/管线产物)"
            if isinstance(obj, list):
                return [(r, "$[%d]" % i) for i, r in enumerate(obj) if isinstance(r, dict)], None
            if isinstance(obj, dict):
                for key in ("records", "patents", "documents", "results", "data",
                            "items", "papers", "entries", "publications"):
                    if isinstance(obj.get(key), list):
                        recs = [(r, "$.%s[%d]" % (key, i))
                                for i, r in enumerate(obj[key]) if isinstance(r, dict)]
                        if recs:
                            return recs, None
                return [(obj, "$")], None
            return [], "unsupported-json"
        if ext == ".jsonl":
            recs = []
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(r, dict):
                        recs.append((r, "line %d" % i))
            return recs, None
        if ext in (".csv", ".tsv"):
            delim = "\t" if ext == ".tsv" else ","
            with open(path, encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f, delimiter=delim))
            return [(dict(r), "row %d" % (i + 2)) for i, r in enumerate(rows)], None
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        title = ""
        for line in text.splitlines():
            s = line.strip().lstrip("#").strip()
            if s:
                title = s[:120]
                break
        return [({"title": title, "_text": text}, "file")], None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error) as e:
        return [], "unparsed: %s" % e


# ---------- 轨道判定 ----------

def classify_track(rec):
    keys = {str(k).lower() for k in rec}
    pat = len(keys & PATENT_KEYS)
    npl = len(keys & NPL_KEYS)
    text = " ".join(str(v) for v in rec.values() if isinstance(v, (str, int, float)))[:20000]
    if PATENT_NUM_RE.search(text):
        pat += 2
    if DOI_RE.search(text):
        npl += 2
    if keys & {"claims", "claim"}:
        pat += 1
    if pat > npl and pat > 0:
        return "patent"
    if npl > pat and npl > 0:
        return "npl"
    return "unclassified"


# ---------- 匹配原语 ----------

def low_view(rec):
    return {str(k).lower(): v for k, v in rec.items()}


def get_text(rec_l, names):
    parts = []
    for n in names:
        v = rec_l.get(n)
        if v is None:
            continue
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
        else:
            parts.append(str(v))
    return "\n".join(parts)


def term_in(term, text):
    t = term.strip().strip('"').strip("“").strip("”").lower()
    return bool(t) and t in text.lower()


def norm_class(s):
    return re.sub(r"\s+", "", str(s)).upper()


def norm_number(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def strip_kind(n):
    return re.sub(r"[A-Z]\d?$", "", n) if re.search(r"\d[A-Z]\d?$", n) else n


def year_of(rec_l):
    for f in DATE_FIELDS:
        v = rec_l.get(f)
        if v is None:
            continue
        m = YEAR_RE.search(str(v))
        if m:
            return int(m.group(0))
    return None


def classification_match(rec_l, facet_classes):
    rec_classes = []
    for f in CLASS_FIELDS:
        v = rec_l.get(f)
        if isinstance(v, list):
            rec_classes.extend(str(x) for x in v)
        elif v:
            rec_classes.append(str(v))
    rec_norm = [norm_class(x) for x in rec_classes]
    matched = []
    for fc in facet_classes or []:
        nfc = norm_class(fc)
        for rn in rec_norm:
            if rn.startswith(nfc) or nfc.startswith(rn):
                matched.append(fc)
                break
    return matched


def applicant_match(rec_l, facet_apps):
    hay = get_text(rec_l, APPLICANT_FIELDS).lower()
    return [a for a in (facet_apps or []) if a.strip().lower() in hay]


def match_topic(rec, track, query):
    """关键词块匹配。返回 blocks_matched {块名: {字段: [词项]}}；NOT 命中返回 None（排除）。"""
    rec_l = low_view(rec)
    if track == "patent":
        fields = TEXT_FIELDS_PATENT + CLASS_FIELDS + APPLICANT_FIELDS
    elif track == "npl":
        fields = NPL_TEXT_FIELDS
    else:
        fields = UNCLASS_TEXT_FIELDS
    blocks_matched = {}
    for block in query.get("blocks", []):
        bname = block.get("name", "?")
        for t in block.get("terms", []):
            term = t["term"].strip()
            up = term.upper()
            neg = up.startswith("NOT ")
            core = term[4:].strip() if neg else term
            hit_fields = []
            for f in fields:
                txt = get_text(rec_l, [f])
                if txt and term_in(core, txt):
                    hit_fields.append(f)
            if neg:
                if hit_fields:
                    return None
                continue
            for f in hit_fields:
                lst = blocks_matched.setdefault(bname, {}).setdefault(f, [])
                if core not in lst:
                    lst.append(core)
    return blocks_matched


def candidate_numbers(rec):
    nums = set()
    rec_l = low_view(rec)
    for f in NUMBER_FIELDS:
        v = rec_l.get(f)
        if v:
            for tok in re.findall(r"[A-Za-z]{2}\d[\dA-Za-z]*", str(v)):
                nums.add(tok)
    text = json.dumps(rec, ensure_ascii=False)
    for m in PATENT_NUM_RE.finditer(text):
        nums.add(m.group(0))
    return nums


def number_match(rec, query_numbers):
    """号码精确匹配：规范化后比较，kind code 有无互相容忍（kind code 感知）。"""
    cands = {norm_number(x) for x in candidate_numbers(rec)}
    hits = []
    for q in query_numbers:
        nq = norm_number(q)
        for c in cands:
            if nq == c or strip_kind(nq) == strip_kind(c):
                hits.append({"query": q, "matched": c})
                break
    return hits


def family_key(rec):
    rec_l = low_view(rec)
    for f in FAMILY_FIELDS:
        v = rec_l.get(f)
        if v:
            return "FAM:" + str(v).strip().upper()
    for f in PRIORITY_FIELDS:
        v = rec_l.get(f)
        if v:
            return "PRI:" + norm_number(str(v))
    for f in NUMBER_FIELDS:
        v = rec_l.get(f)
        if v:
            return "PUB:" + strip_kind(norm_number(str(v)))
    return None


def npl_key(rec):
    rec_l = low_view(rec)
    v = rec_l.get("doi")
    if v:
        return "DOI:" + str(v).strip().lower()
    t = rec_l.get("title")
    if t:
        return "TTL:" + re.sub(r"[^a-z0-9一-鿿]", "", str(t).lower())
    return None


# ---------- 主流程 ----------

def run(corpus_dirs, query):
    files = discover_files(corpus_dirs)
    records, skipped = [], []
    for p in files:
        if os.path.basename(p).lower() in SKIP_BASENAMES:
            skipped.append({"file": p, "reason": "task-file(任务定义，不作语料)"})
            continue
        recs, reason = load_records(p)
        if reason:
            skipped.append({"file": p, "reason": reason})
        for rec, loc in recs:
            records.append({"file": p, "loc": loc, "rec": rec})
    for r in records:
        r["track"] = classify_track(r["rec"])

    mode = query.get("mode", "topic")
    facets = query.get("facets") or {}
    yr = facets.get("year_range")
    raw_hits = []
    for r in records:
        rec, rec_l = r["rec"], low_view(r["rec"])
        if mode == "number_lookup":
            qnums = [t["term"] for b in query.get("blocks", []) for t in b.get("terms", [])]
            nm = number_match(rec, qnums)
            if not nm:
                continue
            blocks_matched = {query["blocks"][0].get("name", "号码"):
                              {"number_fields": [h["matched"] for h in nm]}}
            matched_via, cls_m, app_m, year = "number_exact", [], [], year_of(rec_l)
        else:
            blocks_matched = match_topic(rec, r["track"], query)
            if blocks_matched is None:
                continue
            cls_m = classification_match(rec_l, facets.get("classification")) if r["track"] == "patent" else []
            app_m = applicant_match(rec_l, facets.get("applicant"))
            year = year_of(rec_l)
            if yr and year is not None and not (int(str(yr[0])) <= year <= int(str(yr[1]))):
                continue
            if facets.get("applicant") and not app_m:
                continue
            if not blocks_matched and not cls_m:
                continue
            matched_via = "keyword" if blocks_matched else "classification"
        snap = dict(rec)
        if "_text" in snap:
            snap["_text"] = snap["_text"][:2000]
        if r["track"] == "patent":
            dk = family_key(rec)
        elif r["track"] == "npl":
            dk = npl_key(rec)
        else:
            dk = None
        title = rec_l.get("title") or str(rec_l.get("_text", ""))[:80]
        ident = rec_l.get("publication_number") or rec_l.get("pub_no") or rec_l.get("doi") or ""
        raw_hits.append({
            "track": r["track"], "file": r["file"], "loc": r["loc"],
            "title": str(title), "identifier": str(ident), "year": year,
            "dedup_key": dk, "matched_via": matched_via,
            "blocks_matched": blocks_matched,
            "classification_matched": cls_m, "applicant_matched": app_m,
            "record": snap,
        })

    # 去重：专利按同族键，NPL 按 DOI/标题键；保留字段最丰富的一条
    groups = {}
    for h in raw_hits:
        key = h["dedup_key"] or ("SOLO:" + h["file"] + "#" + h["loc"])
        groups.setdefault(key, []).append(h)
    final, merged = [], []
    for key, g in groups.items():
        g_sorted = sorted(g, key=lambda h: -len(json.dumps(h["record"], ensure_ascii=False)))
        keep = dict(g_sorted[0])
        dropped = g_sorted[1:]
        keep["duplicates"] = [{"file": d["file"], "loc": d["loc"], "identifier": d["identifier"]}
                              for d in dropped]
        final.append(keep)
        if dropped:
            merged.append({"key": key,
                           "kept": {"file": keep["file"], "loc": keep["loc"]},
                           "dropped": keep["duplicates"]})

    hit_blocks = set()
    for h in raw_hits:
        hit_blocks.update(h["blocks_matched"].keys())
    zero_hit_blocks = [b.get("name", "?") for b in query.get("blocks", [])
                       if b.get("name", "?") not in hit_blocks]

    tracks = {"patent": 0, "npl": 0, "unclassified": 0}
    for r in records:
        tracks[r["track"]] += 1
    unclassified = [{"file": r["file"], "loc": r["loc"],
                     "title": str(low_view(r["rec"]).get("title", ""))[:120]}
                    for r in records if r["track"] == "unclassified"]

    return {
        "query_version": query.get("version"),
        "mode": mode,
        "corpus": {"dirs": corpus_dirs, "files": files,
                   "records_total": len(records), "tracks": tracks, "skipped": skipped},
        "hits": final,
        "dedup": {"merged": merged,
                  "duplicates_removed": sum(len(m["dropped"]) for m in merged)},
        "unclassified": unclassified,
        "zero_hit_blocks": zero_hit_blocks,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="检索式执行器（本地语料 + 双轨）")
    ap.add_argument("--query", required=True, help="build_query.py 生成的检索式 JSON")
    ap.add_argument("--corpus", nargs="*", default=None,
                    help="语料目录（缺省: /input /app/work .）")
    ap.add_argument("--out", help="命中清单 JSON 输出路径（缺省打印到 stdout）")
    args = ap.parse_args(argv)

    try:
        with open(args.query, encoding="utf-8") as f:
            query = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write("无法读取检索式: %s\n" % e)
        return 1
    dirs = args.corpus if args.corpus else ["/input", "/app/work", "."]
    result = run(dirs, query)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        sys.stderr.write("命中 %d 条（去重前 %d 条），语料 %d 条记录；结果已写入 %s\n"
                         % (len(result["hits"]),
                            len(result["hits"]) + result["dedup"]["duplicates_removed"],
                            result["corpus"]["records_total"], args.out))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
